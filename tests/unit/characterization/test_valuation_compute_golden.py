"""compute_valuation_from_financials の計算結果を固定するゴールデンテスト。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from stock_analyze_system.services.valuation import compute_valuation_from_financials

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/valuation"


@dataclass
class _FD:
    eps: float | None = None
    net_income: float | None = None
    equity: float | None = None
    shares_outstanding: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    ebitda: float | None = None
    revenue: float | None = None
    fcf: float | None = None


def _apple_fd() -> _FD:
    return _FD(
        eps=6.16, net_income=96995000000.0,
        equity=62146000000.0, shares_outstanding=15800000000.0,
        total_debt=111088000000.0, cash=29965000000.0,
        ebitda=125820000000.0, revenue=383285000000.0,
        fcf=99584000000.0,
    )


@pytest.mark.characterization
class TestComputeValuationGolden:
    def test_full_valuation_matches_golden(self):
        expected = json.loads((FIXTURES / "expected_valuation.json").read_text())
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=_apple_fd(), currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        result_norm = json.loads(json.dumps(result, default=str))
        assert result_norm == expected

    def test_none_stock_price_returns_empty_metrics(self):
        result = compute_valuation_from_financials(
            stock_price=None, fd=_apple_fd(), currency="JPY",
            val_date=date(2024, 3, 31), market_cap=1000.0,
        )
        assert result["currency"] == "JPY"
        assert result["date"] == date(2024, 3, 31)
        assert result["market_cap"] == 1000.0
        assert result["stock_price"] is None
        for key in ("per", "pbr", "ev_ebitda", "psr", "fcf_yield"):
            assert result[key] is None, f"{key} should be None"

    def test_zero_shares_outstanding_gives_none_pbr(self):
        fd = _apple_fd()
        fd.shares_outstanding = 0
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        assert result["pbr"] is None

    def test_missing_equity_gives_none_pbr(self):
        fd = _apple_fd()
        fd.equity = None
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        assert result["pbr"] is None

    def test_missing_shares_gives_none_effective_mcap_metrics(self):
        fd = _apple_fd()
        fd.shares_outstanding = None
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        assert result["ev_ebitda"] is None
        assert result["psr"] is None
        assert result["fcf_yield"] is None

    def test_explicit_market_cap_overrides_shares_calculation(self):
        fd = _apple_fd()
        explicit_mcap = 2_500_000_000_000.0
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=explicit_mcap,
        )
        assert result["market_cap"] == explicit_mcap
