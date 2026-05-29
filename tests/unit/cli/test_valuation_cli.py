"""valuation CLI のテスト (Bug #16 修正含む)"""
import argparse
from datetime import date
from unittest.mock import MagicMock
import pytest
from stock_analyze_system.cli.valuation import handle, register_parser
from tests.unit.cli.conftest import make_services as _make_services

class TestBug16DeviationInHelp:
    def test_deviation_subcommand_registered(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args(["valuation", "deviation", "US_AAPL", "US_MSFT"])
        assert args.action == "deviation"

    def test_no_manual_usage_string(self):
        import inspect
        from stock_analyze_system.cli import valuation
        source = inspect.getsource(valuation)
        assert "Usage: stock-analyze valuation {" not in source

class TestValuationShow:
    async def test_show(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        v = MagicMock(date=date(2024, 6, 1), stock_price=210.0, market_cap=3.2e12,
                      per=32.0, pbr=48.0, ev_ebitda=25.0, psr=8.0, fcf_yield=0.035)
        svc.valuation_service.get_history.return_value = [v]
        args = argparse.Namespace(action="show", json=False, company_id="US_AAPL", years=5)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "2024-06-01" in out and "32.00" in out

class TestValuationCompare:
    async def test_compare(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.compare_valuations.return_value = [
            {"company_id": "US_AAPL", "per": 32.0, "pbr": 48.0, "ev_ebitda": 25.0, "psr": 8.0,
             "date": date(2024, 6, 1), "stock_price": 210.0},
            {"company_id": "US_MSFT", "per": 35.0, "pbr": 13.0, "ev_ebitda": 22.0, "psr": 12.0,
             "date": date(2024, 6, 1), "stock_price": 430.0},
        ]
        args = argparse.Namespace(action="compare", json=False, company_ids=["US_AAPL", "US_MSFT"])
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "US_AAPL" in out and "US_MSFT" in out

class TestValuationRange:
    async def test_range(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.get_history.return_value = [MagicMock()]
        svc.valuation_service.compute_per_range = MagicMock(return_value={"high": 40.0, "median": 28.0, "low": 18.0})
        args = argparse.Namespace(action="range", json=False, company_id="US_AAPL")
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "40.00" in out and "28.00" in out and "18.00" in out

class TestValuationDeviation:
    async def test_deviation(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.compare_valuations.return_value = [
            {"company_id": "US_AAPL", "per": 32.0},
            {"company_id": "US_MSFT", "per": 35.0},
        ]
        svc.valuation_service.compute_group_deviation = MagicMock(return_value=[
            {"company_id": "US_AAPL", "per": 32.0, "per_zscore": -0.71,
             "pbr": None, "pbr_zscore": None, "ev_ebitda": None, "ev_ebitda_zscore": None,
             "psr": None, "psr_zscore": None},
            {"company_id": "US_MSFT", "per": 35.0, "per_zscore": 0.71,
             "pbr": None, "pbr_zscore": None, "ev_ebitda": None, "ev_ebitda_zscore": None,
             "psr": None, "psr_zscore": None},
        ])
        args = argparse.Namespace(action="deviation", json=False, company_ids=["US_AAPL", "US_MSFT"])
        await handle(args, svc)
        assert "US_AAPL" in capsys.readouterr().out

    async def test_deviation_too_few(self):
        svc = _make_services()
        args = argparse.Namespace(action="deviation", json=False, company_ids=["US_AAPL"])
        with pytest.raises(SystemExit):
            await handle(args, svc)


class TestValuationCliErrorPaths:
    async def test_no_action_exits(self):
        svc = _make_services()
        args = argparse.Namespace(json=False)
        with pytest.raises(SystemExit):
            await handle(args, svc)

    async def test_show_no_data(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        svc.valuation_service.get_history.return_value = []
        args = argparse.Namespace(action="show", json=False, company_id="US_AAPL", years=5)
        await handle(args, svc)
        assert "No valuation data" in capsys.readouterr().out

    async def test_show_json(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        v = MagicMock(date=date(2024, 6, 1), stock_price=210.0, market_cap=3.2e12,
                      per=32.0, pbr=48.0, ev_ebitda=25.0, psr=8.0, fcf_yield=0.035)
        svc.valuation_service.get_history.return_value = [v]
        args = argparse.Namespace(action="show", json=True, company_id="US_AAPL", years=5)
        await handle(args, svc)
        assert '"PER"' in capsys.readouterr().out

    async def test_compare_json(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.compare_valuations.return_value = [
            {"company_id": "US_AAPL", "per": 32.0},
        ]
        args = argparse.Namespace(action="compare", json=True, company_ids=["US_AAPL"])
        await handle(args, svc)
        assert '"company_id"' in capsys.readouterr().out

    async def test_range_no_data(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.get_history.return_value = []
        args = argparse.Namespace(action="range", json=False, company_id="US_AAPL")
        await handle(args, svc)
        assert "No valuation data" in capsys.readouterr().out

    async def test_range_no_per(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.get_history.return_value = [MagicMock()]
        svc.valuation_service.compute_per_range = MagicMock(
            return_value={"high": None, "median": None, "low": None},
        )
        args = argparse.Namespace(action="range", json=False, company_id="US_AAPL")
        await handle(args, svc)
        assert "No PER data" in capsys.readouterr().out

    async def test_range_json(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.get_history.return_value = [MagicMock()]
        svc.valuation_service.compute_per_range = MagicMock(
            return_value={"high": 40.0, "median": 28.0, "low": 18.0},
        )
        args = argparse.Namespace(action="range", json=True, company_id="US_AAPL")
        await handle(args, svc)
        assert '"high": 40.0' in capsys.readouterr().out

    async def test_deviation_json(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock()
        svc.valuation_service.compare_valuations.return_value = [
            {"company_id": "US_AAPL", "per": 32.0},
            {"company_id": "US_MSFT", "per": 35.0},
        ]
        svc.valuation_service.compute_group_deviation = MagicMock(return_value=[
            {"company_id": "US_AAPL", "per": 32.0, "per_zscore": -0.71},
            {"company_id": "US_MSFT", "per": 35.0, "per_zscore": 0.71},
        ])
        args = argparse.Namespace(
            action="deviation", json=True,
            company_ids=["US_AAPL", "US_MSFT"],
        )
        await handle(args, svc)
        assert '"per_zscore"' in capsys.readouterr().out
