"""財務データリポジトリ"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.financial_data import FINANCIAL_NATURAL_KEY, FinancialData
from stock_analyze_system.repositories.base import BaseRepository


class FinancialRepository(BaseRepository[FinancialData]):
    """FinancialData ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, FinancialData)

    async def get_timeseries(
        self, company_id: str, period_type: str, years: int = 10,
    ) -> list[FinancialData]:
        """時系列データを fiscal_year_end 降順で取得"""
        cutoff = date.today() - timedelta(days=years * 365)
        stmt = (
            select(FinancialData)
            .where(
                FinancialData.company_id == company_id,
                FinancialData.period_type == period_type,
                FinancialData.fiscal_year_end >= cutoff,
            )
            .order_by(FinancialData.fiscal_year_end.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(
        self, company_id: str, period_type: str,
    ) -> FinancialData | None:
        """最新レコードを1件取得"""
        stmt = (
            select(FinancialData)
            .where(
                FinancialData.company_id == company_id,
                FinancialData.period_type == period_type,
            )
            .order_by(FinancialData.fiscal_year_end.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_upsert(
        self, company_id: str, records: list[dict],
    ) -> int:
        """一括 upsert。戻り値は処理レコード数。"""
        return await self._bulk_upsert_by_natural_key(
            records,
            FINANCIAL_NATURAL_KEY,
            scope_key="company_id",
            scope_value=company_id,
        )
