"""LLM分析参照サービス (RAG生成系とは別の読み取りビュー)"""
from __future__ import annotations

from stock_analyze_system.models.company_analysis import (
    PIPELINE_EXTRACTOR,
    CompanyAnalysis,
)
from stock_analyze_system.repositories.analysis import AnalysisRepository


class AnalysisService:
    def __init__(self, analysis_repo: AnalysisRepository):
        self._repo = analysis_repo

    async def list_recent(self, limit: int = 5) -> list[CompanyAnalysis]:
        """extractor pipeline の最新分析結果のみ返す."""
        return await self._repo.list_recent_extractor(limit=limit)

    async def count_extractor(self) -> int:
        """extractor pipeline 件数を返す (legacy pipeline 行は含まない)."""
        return await self._repo.count(pipeline=PIPELINE_EXTRACTOR)

    async def count_all_pipelines(self) -> int:
        """legacy も含めた CompanyAnalysis 総行数を返す."""
        return await self._repo.count()
