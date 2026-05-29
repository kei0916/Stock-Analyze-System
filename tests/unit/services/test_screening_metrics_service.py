"""ScreeningMetricsService unit tests."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.models.quote_price import QuotePrice
from stock_analyze_system.services.screening_metrics import (
    RefreshMetricsResult,
    ScreeningMetricsService,
)


def _svc():
    return ScreeningMetricsService(
        company_repo=MagicMock(),
        financial_repo=MagicMock(),
        quote_repo=MagicMock(),
        screening_repo=MagicMock(),
    )


@pytest.mark.asyncio
async def test_refresh_creates_cache_from_financials_and_quotes():
    company = Company(
        id="US_AAPL",
        ticker="AAPL",
        name="Apple Inc.",
        market="Nasdaq",
        sector="Technology",
        accounting_standard="US-GAAP",
    )
    financial = FinancialData(
        id=1,
        company_id="US_AAPL",
        accounting_standard="US-GAAP",
        currency="USD",
        period_type="annual",
        fiscal_year_end=date(2024, 9, 28),
        revenue=394_000_000_000.0,
        operating_income=120_000_000_000.0,
        net_income=94_000_000_000.0,
        equity=100_000_000_000.0,
        total_debt=100_000_000_000.0,
        cash=50_000_000_000.0,
        fcf=111_000_000_000.0,
        ebitda=130_000_000_000.0,
        eps=6.0,
        dps=0.9,
        shares_outstanding=15_000_000_000.0,
    )
    quote = QuotePrice(
        id=1,
        company_id="US_AAPL",
        provider="google_sheets",
        price=185.0,
        status="ok",
    )

    svc = _svc()
    svc._company_repo.list_all = AsyncMock(return_value=[company])
    svc._financial_repo.get_latest = AsyncMock(return_value=financial)
    svc._quote_repo.get_latest_many = AsyncMock(return_value={"US_AAPL": quote})
    svc._screening_repo.upsert_cache = AsyncMock()
    svc._screening_repo._session.commit = AsyncMock()
    svc._screening_repo._session.rollback = AsyncMock()

    result = await svc.refresh_from_sec_google()

    assert isinstance(result, RefreshMetricsResult)
    assert result.eligible == 1
    assert result.processed == 1
    assert result.succeeded == 1
    assert result.skipped_no_financials == 0
    assert result.skipped_no_quote == 0
    assert result.failed == 0

    svc._screening_repo.upsert_cache.assert_awaited_once()
    call_args = svc._screening_repo.upsert_cache.await_args
    assert call_args.args[0] == "US_AAPL"
    payload = call_args.args[1]

    assert payload["stock_price"] == 185.0
    assert payload["market_cap"] == pytest.approx(185.0 * 15_000_000_000.0)
    assert payload["trailing_per"] == pytest.approx(185.0 / 6.0)
    assert payload["eps"] == 6.0
    assert payload["pbr"] == pytest.approx(185.0 / (100_000_000_000.0 / 15_000_000_000.0))
    assert payload["psr"] == pytest.approx(185.0 / (394_000_000_000.0 / 15_000_000_000.0))
    assert payload["ev_ebitda"] == pytest.approx(
        (185.0 * 15_000_000_000.0 + 100_000_000_000.0 - 50_000_000_000.0) / 130_000_000_000.0
    )
    assert payload["de_ratio"] == pytest.approx(100_000_000_000.0 / 100_000_000_000.0)
    assert payload["roe"] == pytest.approx(94_000_000_000.0 / 100_000_000_000.0)
    assert payload["operating_margin"] == pytest.approx(120_000_000_000.0 / 394_000_000_000.0)
    assert payload["net_margin"] == pytest.approx(94_000_000_000.0 / 394_000_000_000.0)
    assert payload["fcf_yield"] == pytest.approx(
        111_000_000_000.0 / (185.0 * 15_000_000_000.0)
    )
    assert payload["dividend_yield"] == pytest.approx(0.9 / 185.0)
    assert payload["sector"] == "Technology"

    svc._screening_repo._session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_skips_when_no_financials():
    company = Company(
        id="US_AAPL",
        ticker="AAPL",
        name="Apple Inc.",
        market="Nasdaq",
        sector="Technology",
        accounting_standard="US-GAAP",
    )

    svc = _svc()
    svc._company_repo.list_all = AsyncMock(return_value=[company])
    svc._financial_repo.get_latest = AsyncMock(return_value=None)
    svc._quote_repo.get_latest_many = AsyncMock(return_value={})
    svc._screening_repo.upsert_cache = AsyncMock()
    svc._screening_repo._session.commit = AsyncMock()
    svc._screening_repo._session.rollback = AsyncMock()

    result = await svc.refresh_from_sec_google()

    assert result.succeeded == 0
    assert result.skipped_no_financials == 1
    assert result.skipped_no_quote == 0
    svc._screening_repo.upsert_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_skips_when_quote_not_ok():
    company = Company(
        id="US_AAPL",
        ticker="AAPL",
        name="Apple Inc.",
        market="Nasdaq",
        sector="Technology",
        accounting_standard="US-GAAP",
    )
    financial = FinancialData(
        id=1,
        company_id="US_AAPL",
        accounting_standard="US-GAAP",
        currency="USD",
        period_type="annual",
        fiscal_year_end=date(2024, 9, 28),
        revenue=394_000_000_000.0,
        operating_income=120_000_000_000.0,
        net_income=94_000_000_000.0,
        equity=100_000_000_000.0,
        total_debt=100_000_000_000.0,
        cash=50_000_000_000.0,
        fcf=111_000_000_000.0,
        ebitda=130_000_000_000.0,
        eps=6.0,
        dps=0.9,
        shares_outstanding=15_000_000_000.0,
    )
    quote = QuotePrice(
        id=1,
        company_id="US_AAPL",
        provider="google_sheets",
        price=None,
        status="formula_error",
    )

    svc = _svc()
    svc._company_repo.list_all = AsyncMock(return_value=[company])
    svc._financial_repo.get_latest = AsyncMock(return_value=financial)
    svc._quote_repo.get_latest_many = AsyncMock(return_value={"US_AAPL": quote})
    svc._screening_repo.upsert_cache = AsyncMock()
    svc._screening_repo._session.commit = AsyncMock()
    svc._screening_repo._session.rollback = AsyncMock()

    result = await svc.refresh_from_sec_google()

    assert result.succeeded == 0
    assert result.skipped_no_financials == 0
    assert result.skipped_no_quote == 1
    svc._screening_repo.upsert_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_runs_universe_refresher_before_listing_companies():
    calls = []
    company = Company(
        id="US_AAPL",
        ticker="AAPL",
        name="Apple Inc.",
        market="Nasdaq",
        sector="Technology",
        accounting_standard="US-GAAP",
    )

    async def refresh_universe():
        calls.append("universe")

    async def list_all():
        calls.append("list_all")
        return [company]

    svc = ScreeningMetricsService(
        company_repo=MagicMock(),
        financial_repo=MagicMock(),
        quote_repo=MagicMock(),
        screening_repo=MagicMock(),
        universe_refresher=refresh_universe,
    )
    svc._company_repo.list_all = AsyncMock(side_effect=list_all)
    svc._financial_repo.get_latest = AsyncMock(return_value=None)
    svc._quote_repo.get_latest_many = AsyncMock(return_value={})
    svc._screening_repo.upsert_cache = AsyncMock()
    svc._screening_repo._session.commit = AsyncMock()
    svc._screening_repo._session.rollback = AsyncMock()

    result = await svc.refresh_from_sec_google()

    assert calls == ["universe", "list_all"]
    assert result.eligible == 1
