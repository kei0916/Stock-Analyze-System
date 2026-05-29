"""分析結果リポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.company_analysis import (
    PIPELINE_EXTRACTOR,
    CompanyAnalysis,
)
from stock_analyze_system.repositories.base import BaseRepository


class AnalysisRepository(BaseRepository[CompanyAnalysis]):
    """CompanyAnalysis ドメインリポジトリ.

    Domain reads (`get_analyses`, `get_by_type`, `list_recent_extractor`)
    filter by `pipeline = 'extractor'` so legacy rows (pipeline IS NULL) are
    not reused as if produced by the current pipeline. The inherited
    `BaseRepository.count(**filters)` / `list_all(**filters)` contract is
    intentionally preserved so callers can opt into legacy/cross-pipeline
    aggregates by passing explicit filters.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, CompanyAnalysis)

    async def get_analyses(
        self, company_id: str, filing_id: int,
    ) -> list[CompanyAnalysis]:
        stmt = select(CompanyAnalysis).where(
            CompanyAnalysis.company_id == company_id,
            CompanyAnalysis.filing_id == filing_id,
            CompanyAnalysis.pipeline == PIPELINE_EXTRACTOR,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_type(
        self, company_id: str, filing_id: int, analysis_type: str,
    ) -> CompanyAnalysis | None:
        stmt = select(CompanyAnalysis).where(
            CompanyAnalysis.company_id == company_id,
            CompanyAnalysis.filing_id == filing_id,
            CompanyAnalysis.analysis_type == analysis_type,
            CompanyAnalysis.pipeline == PIPELINE_EXTRACTOR,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent_extractor(
        self, limit: int = 5,
    ) -> list[CompanyAnalysis]:
        """最近作成された extractor pipeline 分析結果."""
        stmt = (
            select(CompanyAnalysis)
            .where(CompanyAnalysis.pipeline == PIPELINE_EXTRACTOR)
            .order_by(CompanyAnalysis.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
