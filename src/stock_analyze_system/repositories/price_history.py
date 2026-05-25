# src/stock_analyze_system/repositories/price_history.py
from __future__ import annotations

import logging
from datetime import date as date_type

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.price_history import PriceHistory
from stock_analyze_system.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# SQLite bind parameter limit is 999; 100 rows × ~7 params = 700 < 999
_CHUNK_SIZE = 100


class PriceHistoryRepository(BaseRepository[PriceHistory]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PriceHistory)

    async def upsert_many(self, rows: list[dict]) -> int:
        """Bulk upsert price history rows with SQLite bind param chunking.
        
        Returns inserted/updated count.
        """
        if not rows:
            return 0
        
        total = 0
        for i in range(0, len(rows), _CHUNK_SIZE):
            chunk = rows[i:i + _CHUNK_SIZE]
            stmt = sqlite_insert(PriceHistory).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["company_id", "date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "ticker": stmt.excluded.ticker,
                    "source": stmt.excluded.source,
                },
            )
            result = await self._session.execute(stmt)
            total += result.rowcount
        
        return total

    async def get_history(
        self, company_id: str, start_date: date_type | None = None, end_date: date_type | None = None,
    ) -> list[PriceHistory]:
        from sqlalchemy import select
        
        stmt = select(PriceHistory).where(PriceHistory.company_id == company_id)
        if start_date:
            stmt = stmt.where(PriceHistory.date >= start_date)
        if end_date:
            stmt = stmt.where(PriceHistory.date <= end_date)
        stmt = stmt.order_by(PriceHistory.date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def exists_for_company(self, company_id: str) -> bool:
        """Check if price_history has any rows for a company."""
        from sqlalchemy import select, exists
        
        stmt = select(exists().where(PriceHistory.company_id == company_id))
        result = await self._session.execute(stmt)
        return result.scalar()

    async def get_company_stats(self) -> dict[str, dict]:
        """Return price history statistics for each company.
        
        Returns:
            {
                "US_AAPL": {
                    "rows": 2513,
                    "min_date": date(2016, 5, 11),
                    "max_date": date(2026, 5, 8),
                    "span_days": 3649,
                },
                ...
            }
        """
        from sqlalchemy import func, select
        
        stmt = (
            select(
                PriceHistory.company_id,
                func.count().label("row_count"),
                func.min(PriceHistory.date).label("min_date"),
                func.max(PriceHistory.date).label("max_date"),
            )
            .group_by(PriceHistory.company_id)
        )
        result = await self._session.execute(stmt)
        
        stats = {}
        for row in result.all():
            company_id, row_count, min_date, max_date = row
            span_days = (max_date - min_date).days if min_date and max_date else 0
            stats[company_id] = {
                "rows": row_count,
                "min_date": min_date,
                "max_date": max_date,
                "span_days": span_days,
            }
        return stats

    async def get_incomplete_companies(
        self, 
        min_span_days: int = 90,
        min_rows: int = 250,
    ) -> dict[str, dict]:
        """Return companies with likely data gaps (excluding new listings).
        
        New listings (span_days < min_span_days) are excluded.
        Data gaps (span_days >= min_span_days and rows < min_rows) are returned.
        
        Args:
            min_span_days: Threshold to consider a company as new listing
            min_rows: Threshold to consider data as complete
        
        Returns:
            {"US_MDLN": {"rows": 98, "min_date": date(...), "max_date": date(...), "span_days": 142}, ...}
        """
        stats = await self.get_company_stats()
        incomplete = {
            cid: stat for cid, stat in stats.items()
            if stat["span_days"] >= min_span_days and stat["rows"] < min_rows
        }
        return incomplete
