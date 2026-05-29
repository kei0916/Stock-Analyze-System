"""filings CLI のテスト"""
import argparse
from datetime import date
from unittest.mock import MagicMock
import pytest
from stock_analyze_system.cli.filings import handle
from stock_analyze_system.services.filing_content import FetchSummary
from tests.unit.cli.conftest import make_services as _make_services

class TestFilingsList:
    async def test_list(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        f1 = MagicMock(id=1, filing_type="10-K", source="SEC", fiscal_year=2024,
                       period_end=date(2024, 9, 28), filed_at=date(2024, 11, 1))
        svc.filing_service.list_filings.return_value = [f1]
        args = argparse.Namespace(action="list", json=False, company_id="US_AAPL")
        await handle(args, svc)
        assert "10-K" in capsys.readouterr().out

    async def test_list_empty(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        svc.filing_service.list_filings.return_value = []
        args = argparse.Namespace(action="list", json=False, company_id="US_AAPL")
        await handle(args, svc)
        assert "No" in capsys.readouterr().out

    async def test_list_json(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        f1 = MagicMock(id=1, filing_type="10-K", source="SEC", fiscal_year=2024,
                       period_end=date(2024, 9, 28), filed_at=date(2024, 11, 1))
        svc.filing_service.list_filings.return_value = [f1]
        args = argparse.Namespace(action="list", json=True, company_id="US_AAPL")
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "10-K" in out
        assert "{" in out

class TestFilingsDownload:
    async def test_download_sec(self, capsys):
        svc = _make_services()
        company = MagicMock(id="US_AAPL", cik="0000320193", edinet_code=None)
        svc.company_service.get_company.return_value = company
        svc.filing_sync.update_from_sec.return_value = 3
        svc.filing_content_service.fetch_for_company.return_value = FetchSummary()
        args = argparse.Namespace(action="download", json=False, company_id="US_AAPL")
        await handle(args, svc)
        svc.filing_sync.update_from_sec.assert_called_once()
        assert "3" in capsys.readouterr().out

    async def test_download_edinet(self, capsys):
        svc = _make_services()
        company = MagicMock(id="JP_7203", cik=None, edinet_code="E02144")
        svc.company_service.get_company.return_value = company
        svc.filing_sync.update_from_edinet.return_value = 5
        svc.filing_content_service.fetch_for_company.return_value = FetchSummary()
        args = argparse.Namespace(action="download", json=False, company_id="JP_7203")
        await handle(args, svc)
        svc.filing_sync.update_from_edinet.assert_called_once()
        assert "5" in capsys.readouterr().out

    async def test_download_no_code(self):
        svc = _make_services()
        company = MagicMock(id="US_AAPL", cik=None, edinet_code=None)
        svc.company_service.get_company.return_value = company
        args = argparse.Namespace(action="download", json=False, company_id="US_AAPL")
        with pytest.raises(SystemExit):
            await handle(args, svc)

    async def test_no_action(self):
        svc = _make_services()
        args = argparse.Namespace(action=None, json=False)
        with pytest.raises(SystemExit):
            await handle(args, svc)


class TestDownloadFetchesContent:
    async def test_download_invokes_sync_then_fetch(self, capsys):
        svc = _make_services()
        company = MagicMock(id="US_AAPL", cik="0000320193", edinet_code=None)
        svc.company_service.get_company.return_value = company
        svc.filing_sync.update_from_sec.return_value = 3
        svc.filing_content_service.fetch_for_company.return_value = FetchSummary(
            fetched=2,
            skipped=1,
        )
        args = argparse.Namespace(action="download", json=False, company_id="US_AAPL")

        await handle(args, svc)

        svc.filing_sync.update_from_sec.assert_called_once_with(
            "US_AAPL", "0000320193",
        )
        svc.filing_content_service.fetch_for_company.assert_called_once_with("US_AAPL")
        out = capsys.readouterr().out
        assert "Synced 3" in out
        assert "Fetched content: 2 new" in out

    async def test_download_exits_non_zero_when_fetch_fails(self, capsys):
        svc = _make_services()
        company = MagicMock(id="US_AAPL", cik="0000320193", edinet_code=None)
        svc.company_service.get_company.return_value = company
        svc.filing_sync.update_from_sec.return_value = 1
        svc.filing_content_service.fetch_for_company.return_value = FetchSummary(
            fetched=0,
            skipped=0,
            failed=[(42, "not found")],
        )
        args = argparse.Namespace(action="download", json=False, company_id="US_AAPL")

        result = await handle(args, svc)

        assert result == 1
        err = capsys.readouterr().err
        assert "filing_id=42: not found" in err
