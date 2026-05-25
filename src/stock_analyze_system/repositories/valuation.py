"""バリュエーションリポジトリ"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.repositories.base import BaseRepository


class ValuationRepository(BaseRepository[Valuation]):
    """Valuation ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Valuation)

    async def get_history(
        self, company_id: str, years: int = 10,
    ) -> list[Valuation]:
        """履歴を date 降順で取得"""
        cutoff = date.today() - timedelta(days=years * 365)
        stmt = (
            select(Valuation)
            .where(
                Valuation.company_id == company_id,
                Valuation.date >= cutoff,
            )
            .order_by(Valuation.date.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self, company_id: str) -> Valuation | None:
        """最新バリュエーションを取得"""
        stmt = (
            select(Valuation)
            .where(Valuation.company_id == company_id)
            .order_by(Valuation.date.desc())
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
            ("date",),
            scope_key="company_id",
            scope_value=company_id,
        )
