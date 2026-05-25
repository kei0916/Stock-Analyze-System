"""company CLI のテスト"""
import argparse
from unittest.mock import MagicMock
import pytest
from stock_analyze_system.cli.company import handle
from tests.unit.cli.conftest import make_services as _make_services

class TestCompanyRegister:
    async def test_register_us(self, capsys):
        svc = _make_services()
        company = MagicMock(id="US_AAPL", name="Apple")
        svc.company_service.register_company.return_value = company
        args = argparse.Namespace(
            action="register", json=False, name="Apple", market="NASDAQ",
            ticker="AAPL", security_code=None, sector=None, cik=None, edinet_code=None,
        )
        await handle(args, svc)
        assert "US_AAPL" in capsys.readouterr().out

    async def test_register_json(self, capsys):
        svc = _make_services()
        company = MagicMock(id="US_AAPL", name="Apple", market="NASDAQ", ticker="AAPL", security_code=None)
        svc.company_service.register_company.return_value = company
        args = argparse.Namespace(
            action="register", json=True, name="Apple", market="NASDAQ",
            ticker="AAPL", security_code=None, sector=None, cik=None, edinet_code=None,
        )
        await handle(args, svc)
        assert '"US_AAPL"' in capsys.readouterr().out

class TestCompanySearch:
    async def test_search_results(self, capsys):
        svc = _make_services()
        c1 = MagicMock(id="US_AAPL", name="Apple", ticker="AAPL", market="NASDAQ")
        svc.company_service.search_companies.return_value = [c1]
        args = argparse.Namespace(action="search", json=False, query="Apple", limit=20)
        await handle(args, svc)
        assert "AAPL" in capsys.readouterr().out

    async def test_search_no_results(self, capsys):
        svc = _make_services()
        svc.company_service.search_companies.return_value = []
        args = argparse.Namespace(action="search", json=False, query="zzz", limit=20)
        await handle(args, svc)
        assert "No" in capsys.readouterr().out

class TestCompanyShow:
    async def test_show(self, capsys):
        svc = _make_services()
        company = MagicMock(
            id="US_AAPL", name="Apple", ticker="AAPL", market="NASDAQ",
            sector="Technology", accounting_standard="US-GAAP",
            security_code=None, cik="0000320193", edinet_code=None,
        )
        svc.company_service.get_company.return_value = company
        args = argparse.Namespace(action="show", json=False, company_id="US_AAPL")
        await handle(args, svc)
        assert "Apple" in capsys.readouterr().out

    async def test_show_not_found(self):
        svc = _make_services()
        svc.company_service.get_company.return_value = None
        args = argparse.Namespace(action="show", json=False, company_id="US_XXXX")
        with pytest.raises(SystemExit):
            await handle(args, svc)
