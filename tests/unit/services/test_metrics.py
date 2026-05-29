"""metrics 純粋関数のテスト"""
import pytest

from stock_analyze_system.services import metrics


class TestSafeDiv:
    def test_normal(self):
        assert metrics._safe_div(10.0, 2.0) == 5.0

    def test_none_numerator(self):
        assert metrics._safe_div(None, 2.0) is None

    def test_none_denominator(self):
        assert metrics._safe_div(10.0, None) is None

    def test_zero_denominator(self):
        assert metrics._safe_div(10.0, 0.0) is None

    def test_negative_denom_allowed(self):
        assert metrics._safe_div(10.0, -2.0) == -5.0

    def test_negative_denom_rejected(self):
        assert metrics._safe_div(10.0, -2.0, require_positive_denom=True) is None


class TestProfitability:
    def test_operating_margin(self):
        assert metrics.operating_margin(30.0, 100.0) == pytest.approx(0.3)

    def test_operating_margin_none(self):
        assert metrics.operating_margin(None, 100.0) is None

    def test_net_margin(self):
        assert metrics.net_margin(20.0, 100.0) == pytest.approx(0.2)

    def test_roe(self):
        assert metrics.roe(10.0, 50.0) == pytest.approx(0.2)

    def test_roa(self):
        assert metrics.roa(10.0, 200.0) == pytest.approx(0.05)

    def test_roic(self):
        result = metrics.roic(
            operating_income=100.0, tax_expense=25.0,
            income_before_tax=100.0, total_debt=200.0,
            equity=300.0, cash=50.0,
        )
        assert result == pytest.approx(75.0 / 450.0)

    def test_roic_negative_income_before_tax(self):
        assert metrics.roic(100.0, 25.0, -10.0, 200.0, 300.0, 50.0) is None

    def test_roic_zero_invested_capital(self):
        assert metrics.roic(100.0, 25.0, 100.0, 0.0, 50.0, 50.0) is None


class TestEfficiency:
    def test_asset_turnover(self):
        assert metrics.asset_turnover(200.0, 400.0) == pytest.approx(0.5)

    def test_inventory_turnover(self):
        assert metrics.inventory_turnover(150.0, 50.0) == pytest.approx(3.0)


class TestStability:
    def test_equity_ratio(self):
        assert metrics.equity_ratio(100.0, 400.0) == pytest.approx(0.25)

    def test_current_ratio(self):
        assert metrics.current_ratio(150.0, 100.0) == pytest.approx(1.5)

    def test_de_ratio(self):
        assert metrics.de_ratio(200.0, 400.0) == pytest.approx(0.5)


class TestGrowth:
    def test_revenue_growth(self):
        assert metrics.revenue_growth(110.0, 100.0) == pytest.approx(0.1)

    def test_revenue_growth_zero_previous(self):
        assert metrics.revenue_growth(110.0, 0.0) is None

    def test_revenue_growth_negative_previous(self):
        assert metrics.revenue_growth(110.0, -10.0) is None

    def test_eps_growth(self):
        assert metrics.eps_growth(5.5, 5.0) == pytest.approx(0.1)

    def test_eps_growth_negative_previous(self):
        assert metrics.eps_growth(5.5, -5.0) is None

    def test_fcf_growth(self):
        assert metrics.fcf_growth(22.0, 20.0) == pytest.approx(0.1)


class TestShareholderReturn:
    def test_dividend_payout_primary(self):
        result = metrics.dividend_payout_ratio(dividends_paid=-50.0, net_income=100.0)
        assert result == pytest.approx(0.5)

    def test_dividend_payout_fallback(self):
        result = metrics.dividend_payout_ratio(dps=2.0, eps=4.0)
        assert result == pytest.approx(0.5)

    def test_total_payout_ratio(self):
        result = metrics.total_payout_ratio(-30.0, -20.0, 100.0)
        assert result == pytest.approx(0.5)


class TestValuation:
    def test_per_primary(self):
        assert metrics.per(stock_price=100.0, eps=5.0) == pytest.approx(20.0)

    def test_per_fallback(self):
        assert metrics.per(market_cap=1000.0, net_income=50.0) == pytest.approx(20.0)

    def test_per_negative_eps(self):
        assert metrics.per(stock_price=100.0, eps=-5.0) is None

    def test_pbr(self):
        assert metrics.pbr(1000.0, 500.0) == pytest.approx(2.0)

    def test_ev_ebitda(self):
        result = metrics.ev_ebitda(
            market_cap=1000.0, total_debt=200.0, cash=100.0, ebitda=110.0,
        )
        assert result == pytest.approx((1000 + 200 - 100) / 110)

    def test_ev_ebitda_negative_ebitda(self):
        assert metrics.ev_ebitda(1000.0, 200.0, 100.0, -10.0) is None

    def test_psr(self):
        assert metrics.psr(1000.0, 500.0) == pytest.approx(2.0)


class TestUtilities:
    def test_is_anomaly_true(self):
        assert metrics.is_anomaly(140.0, 100.0, threshold=0.3) is True

    def test_is_anomaly_false(self):
        assert metrics.is_anomaly(110.0, 100.0, threshold=0.3) is False

    def test_is_anomaly_none(self):
        assert metrics.is_anomaly(None, 100.0) is None
