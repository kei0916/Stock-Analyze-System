"""FilingService のテスト"""
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

from stock_analyze_system.services.filing import FilingService


class TestFilingService:
    async def test_upsert_filing(self):
        repo = AsyncMock()
        repo.upsert.return_value = AsyncMock(id=1)
        svc = FilingService(repo)
        await svc.upsert_filing("US_AAPL", {
            "source": "SEC", "filing_type": "10-K",
            "period_type": "annual", "fiscal_year": 2024,
            "accession_no": "0000320193-24-000123",
        })
        repo.upsert.assert_called_once()

    async def test_get_latest_filing(self):
        repo = AsyncMock()
        repo.get_latest_filing.return_value = AsyncMock(fiscal_year=2024)
        svc = FilingService(repo)
        await svc.get_latest_filing("US_AAPL", "10-K")
        repo.get_latest_filing.assert_called_once_with("US_AAPL", "10-K")

    async def test_list_filings_defaults_to_no_limit(self):
        repo = AsyncMock()
        repo.list_filings.return_value = [AsyncMock(), AsyncMock()]
        svc = FilingService(repo)
        results = await svc.list_filings("US_AAPL")
        assert len(results) == 2
        repo.list_filings.assert_called_once_with("US_AAPL", limit=None)

    async def test_list_filings_passes_explicit_limit(self):
        repo = AsyncMock()
        repo.list_filings.return_value = [AsyncMock()]
        svc = FilingService(repo)
        results = await svc.list_filings("US_AAPL", limit=20)
        assert len(results) == 1
        repo.list_filings.assert_called_once_with("US_AAPL", limit=20)

    def test_get_storage_path(self):
        path = FilingService.get_storage_path(
            "data/filings", "SEC", "US_AAPL", 2024, "annual", "10-K", "acc123",
        )
        assert path == Path("data/filings/SEC/US_AAPL/2024/annual/10-K/acc123")

    def test_compute_content_hash(self):
        content = b"test content"
        result = FilingService.compute_content_hash(content)
        assert result == hashlib.sha256(content).hexdigest()
