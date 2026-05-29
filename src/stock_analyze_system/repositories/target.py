"""分析対象リポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.analysis_target import AnalysisTarget
from stock_analyze_system.repositories.base import BaseRepository


class TargetRepository(BaseRepository[AnalysisTarget]):
    """AnalysisTarget ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AnalysisTarget)

    async def list_targets(self) -> list[AnalysisTarget]:
        """全ターゲット一覧"""
        return await self.list_all()

    async def find_by_company(self, company_id: str) -> AnalysisTarget | None:
        """企業ID で検索"""
        stmt = select(AnalysisTarget).where(
            AnalysisTarget.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_add(self, records: list[dict]) -> int:
        """一括追加（既存はスキップ）。戻り値は実際に追加された件数。

        SQLite native UPSERT (ON CONFLICT DO NOTHING) + RETURNING で
        1 query にまとめる (旧実装は事前 SELECT + INSERT の 2 query)。
        intra-batch の重複 company_id も自動でスキップされる。

        Args:
            records: 各 dict は少なくとも `company_id` キーを含む必要がある。

        Returns:
            実際に新規挿入された行数。
        """
        if not records:
            return 0
        stmt = (
            sqlite_insert(AnalysisTarget)
            .values(records)
            .on_conflict_do_nothing(index_elements=["company_id"])
            .returning(AnalysisTarget.company_id)
        )
        result = await self._session.execute(stmt)
        inserted = result.scalars().all()
        await self._session.flush()
        return len(inserted)
