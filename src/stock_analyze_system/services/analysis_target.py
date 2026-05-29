"""分析対象サービス"""
from __future__ import annotations

import logging

from stock_analyze_system.exceptions import NotFoundError
from stock_analyze_system.repositories.target import TargetRepository

logger = logging.getLogger(__name__)


class AnalysisTargetService:
    """分析対象銘柄の管理サービス"""

    def __init__(self, target_repo: TargetRepository):
        self._repo = target_repo

    async def add_target(
        self, company_id: str, source: str = "manual", criteria: str | None = None,
    ):
        """ターゲットを追加（既存はスキップ）"""
        existing = await self._repo.find_by_company(company_id)
        if existing is not None:
            return existing
        return await self._repo.upsert(
            {"company_id": company_id},
            {"source": source, "criteria": criteria},
        )

    async def remove_target(self, company_id: str) -> None:
        """ターゲットを削除"""
        target = await self._repo.find_by_company(company_id)
        if target is None:
            raise NotFoundError(f"Target for {company_id} not found")
        await self._repo.delete(target.id)

    async def list_targets(self):
        return await self._repo.list_targets()

    async def add_from_screening(self, company_ids: list[str]) -> int:
        """スクリーニング結果からターゲットを一括追加"""
        records = [
            {"company_id": cid, "source": "screening"}
            for cid in company_ids
        ]
        return await self._repo.bulk_add(records)
