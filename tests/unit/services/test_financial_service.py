"""FinancialService のテスト"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.services.financial import FinancialService


def _make_fd(**kwargs):
    """FinancialData 風のモックオブジェクト"""
    fd = MagicMock()
    defaults = {
        "revenue": None, "operating_income": None, "net_income": None,
        "total_assets": None, "equity": None, "current_assets": None,
        "current_liabilities": None, "total_debt": None, "cash": None,
        "inventory": None, "cogs": None, "operating_cf": None,
        "capex": None, "fcf": None, "ebitda": None, "eps": None,
        "dps": None, "tax_expense": None, "income_before_tax": None,
        "shares_outstanding": None, "dividends_paid": None,
        "share_repurchases": None, "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28),
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(fd, k, v)
    return fd


class TestComputeMetrics:
    def test_basic_metrics(self):
        fd = _make_fd(
            revenue=100.0, operating_income=30.0, net_income=20.0,
            total_assets=500.0, equity=200.0,
        )
        svc = FinancialService(AsyncMock())
        result = svc.compute_metrics(fd)
        assert result["operating_margin"] == pytest.approx(0.3)
        assert result["net_margin"] == pytest.approx(0.2)
        assert result["roe"] == pytest.approx(0.1)

    def test_all_none_inputs(self):
        fd = _make_fd()
        svc = FinancialService(AsyncMock())
        result = svc.compute_metrics(fd)
        assert all(v is None for v in result.values())


class TestComputeTimeseriesMetrics:
    def test_annual_growth(self):
        """年次データの前年比成長率が計算されること"""
        fd_2024 = _make_fd(
            revenue=120.0, eps=6.0, fcf=30.0,
            fiscal_year_end=date(2024, 9, 28), period_type="annual",
        )
        fd_2023 = _make_fd(
            revenue=100.0, eps=5.0, fcf=25.0,
            fiscal_year_end=date(2023, 9, 28), period_type="annual",
        )
        svc = FinancialService(AsyncMock())
        results = svc.compute_timeseries_metrics([fd_2024, fd_2023])
        assert len(results) == 2
        assert results[0]["revenue_growth"] == pytest.approx(0.2)
        assert results[0]["eps_growth"] == pytest.approx(0.2)

    def test_quarterly_yoy(self):
        """四半期データの前年同期比が計算されること"""
        fd_q1_2024 = _make_fd(
            revenue=50.0, eps=2.5,
            fiscal_year_end=date(2024, 3, 31), period_type="quarterly",
        )
        fd_q1_2023 = _make_fd(
            revenue=40.0, eps=2.0,
            fiscal_year_end=date(2023, 3, 31), period_type="quarterly",
        )
        svc = FinancialService(AsyncMock())
        results = svc.compute_timeseries_metrics([fd_q1_2024, fd_q1_2023])
        assert results[0]["revenue_growth"] == pytest.approx(0.25)


class TestUpsertFinancialData:
    async def test_upsert_financial_data(self):
        """upsert_financial_data がリポジトリ経由で動作すること"""
        repo = AsyncMock()
        repo.upsert.return_value = MagicMock(id=1)
        svc = FinancialService(repo)
        await svc.upsert_financial_data("US_AAPL", {
            "accounting_standard": "US-GAAP", "currency": "USD",
            "period_type": "annual", "fiscal_year_end": date(2024, 9, 28),
            "revenue": 394e9,
        })
        repo.upsert.assert_called_once()
