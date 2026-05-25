"""AnalysisTargetService のテスト"""
from unittest.mock import AsyncMock, MagicMock

from stock_analyze_system.services.analysis_target import AnalysisTargetService


class TestAnalysisTargetService:
    async def test_add_target(self):
        repo = AsyncMock()
        repo.find_by_company.return_value = None
        svc = AnalysisTargetService(repo)
        await svc.add_target("US_AAPL", source="manual")

    async def test_remove_target(self):
        repo = AsyncMock()
        target = MagicMock(id=1)
        repo.find_by_company.return_value = target
        repo.delete.return_value = True
        svc = AnalysisTargetService(repo)
        await svc.remove_target("US_AAPL")
        repo.delete.assert_called_once_with(1)

    async def test_list_targets(self):
        repo = AsyncMock()
        repo.list_targets.return_value = [MagicMock(), MagicMock()]
        svc = AnalysisTargetService(repo)
        results = await svc.list_targets()
        assert len(results) == 2

    async def test_add_from_screening(self):
        repo = AsyncMock()
        repo.bulk_add.return_value = 3
        svc = AnalysisTargetService(repo)
        count = await svc.add_from_screening(["US_AAPL", "US_MSFT", "US_GOOG"])
        assert count == 3
