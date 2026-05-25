"""financial CLI のテスト"""
import argparse
from datetime import date
from unittest.mock import MagicMock

import pytest

from stock_analyze_system.cli.financial import _fmt_metric, handle
from tests.unit.cli.conftest import make_services as _make_services

class TestFinancialShow:
    async def test_show_timeseries(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        fd = MagicMock(
            fiscal_year_end=date(2024, 9, 28), period_type="annual",
            revenue=394e9, operating_income=120e9, net_income=97e9, eps=6.42, ebitda=130e9,
        )
        svc.financial_service.get_timeseries.return_value = [fd]
        args = argparse.Namespace(action="show", json=False, company_id="US_AAPL", period="annual", years=5)
        await handle(args, svc)
        assert "2024-09-28" in capsys.readouterr().out

    async def test_show_no_data(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        svc.financial_service.get_timeseries.return_value = []
        args = argparse.Namespace(action="show", json=False, company_id="US_AAPL", period="annual", years=5)
        await handle(args, svc)
        assert "No" in capsys.readouterr().out

class TestFinancialMetrics:
    async def test_metrics(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        fd = MagicMock(fiscal_year_end=date(2024, 9, 28), period_type="annual")
        svc.financial_service.get_timeseries.return_value = [fd]
        svc.financial_service.compute_timeseries_metrics = MagicMock(return_value=[{
            "fiscal_year_end": date(2024, 9, 28), "period_type": "annual",
            "operating_margin": 0.304, "net_margin": 0.246, "roe": 1.564,
            "revenue_growth": 0.05, "eps_growth": 0.08,
        }])
        args = argparse.Namespace(action="metrics", json=False, company_id="US_AAPL", period="annual", years=5)
        await handle(args, svc)
        assert "2024-09-28" in capsys.readouterr().out


class TestFinancialCliErrorPaths:
    def test_fmt_metric_none(self):
        assert _fmt_metric("roe", None) == "N/A"

    def test_fmt_metric_non_pct(self):
        assert _fmt_metric("revenue", 1234.5).strip() != ""

    async def test_no_action_exits(self, capsys):
        svc = _make_services()
        args = argparse.Namespace(json=False)
        with pytest.raises(SystemExit):
            await handle(args, svc)
        assert "Usage" in capsys.readouterr().out

    async def test_show_json(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        fd = MagicMock(
            fiscal_year_end=date(2024, 9, 28), period_type="annual",
            revenue=394e9, operating_income=120e9, net_income=97e9,
            eps=6.42, ebitda=130e9,
        )
        svc.financial_service.get_timeseries.return_value = [fd]
        args = argparse.Namespace(
            action="show", json=True, company_id="US_AAPL",
            period="annual", years=5,
        )
        await handle(args, svc)
        assert '"Period End"' in capsys.readouterr().out

    async def test_metrics_no_data(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        svc.financial_service.get_timeseries.return_value = []
        args = argparse.Namespace(
            action="metrics", json=False, company_id="US_AAPL",
            period="annual", years=5,
        )
        await handle(args, svc)
        assert "No financial data" in capsys.readouterr().out

    async def test_metrics_json(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        fd = MagicMock(fiscal_year_end=date(2024, 9, 28), period_type="annual")
        svc.financial_service.get_timeseries.return_value = [fd]
        svc.financial_service.compute_timeseries_metrics = MagicMock(return_value=[{
            "fiscal_year_end": date(2024, 9, 28),
            "operating_margin": 0.3, "net_margin": 0.2,
            "roe": 1.5, "revenue_growth": 0.05, "eps_growth": 0.08,
        }])
        args = argparse.Namespace(
            action="metrics", json=True, company_id="US_AAPL",
            period="annual", years=5,
        )
        await handle(args, svc)
        assert '"fiscal_year_end"' in capsys.readouterr().out
