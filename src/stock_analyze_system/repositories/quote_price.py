"""Quote price cache repository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.quote_price import QuotePrice
from stock_analyze_system.repositories.base import BaseRepository


def _to_utc_naive(value: Any) -> Any:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class QuotePriceRepository(BaseRepository[QuotePrice]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, QuotePrice)

    async def upsert_latest(self, data: dict[str, Any]) -> QuotePrice:
        normalized = dict(data)
        for key in ("as_of", "fetched_at"):
            if key in normalized:
                normalized[key] = _to_utc_naive(normalized[key])

        filters = {
            "company_id": normalized["company_id"],
            "provider": normalized.get("provider", "google_sheets"),
        }
        remainder = {k: v for k, v in normalized.items() if k not in filters}
        return await self.upsert(filters, remainder)

    async def get_latest(
        self,
        company_id: str,
        provider: str = "google_sheets",
    ) -> QuotePrice | None:
        stmt = select(QuotePrice).where(
            QuotePrice.company_id == company_id,
            QuotePrice.provider == provider,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_many(
        self,
        company_ids: list[str],
        provider: str = "google_sheets",
    ) -> dict[str, QuotePrice]:
        if not company_ids:
            return {}
        stmt = select(QuotePrice).where(
            QuotePrice.company_id.in_(company_ids),
            QuotePrice.provider == provider,
        )
        result = await self._session.execute(stmt)
        return {row.company_id: row for row in result.scalars().all()}

    async def count_by_status(self, provider: str = "google_sheets") -> dict[str, int]:
        stmt = (
            select(QuotePrice.status, func.count())
            .where(QuotePrice.provider == provider)
            .group_by(QuotePrice.status)
            .order_by(QuotePrice.status)
        )
        result = await self._session.execute(stmt)
        return {status: count for status, count in result.all()}

    async def list_failed(
        self,
        provider: str = "google_sheets",
        limit: int = 100,
    ) -> list[QuotePrice]:
        stmt = (
            select(QuotePrice)
            .where(
                QuotePrice.provider == provider,
                QuotePrice.status != "ok",
            )
            .order_by(QuotePrice.company_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(
        self,
        limit: int = 5,
        provider: str = "google_sheets",
    ) -> list[QuotePrice]:
        stmt = (
            select(QuotePrice)
            .where(QuotePrice.provider == provider)
            .order_by(QuotePrice.fetched_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_fetched_at(
        self,
        provider: str = "google_sheets",
    ) -> datetime | None:
        stmt = (
            select(func.max(QuotePrice.fetched_at))
            .where(QuotePrice.provider == provider)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_stale(
        self,
        provider: str = "google_sheets",
        max_age_hours: int = 24,
        limit: int | None = None,
    ) -> list[QuotePrice]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        ).replace(tzinfo=None)
        stmt = (
            select(QuotePrice)
            .where(
                QuotePrice.provider == provider,
                QuotePrice.fetched_at < cutoff,
            )
            .order_by(QuotePrice.fetched_at)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
