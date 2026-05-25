from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.services.google_sheets_quotes import QuoteResult
from stock_analyze_system.services.quotes import QuoteService


async def _seed_company(
    session,
    company_id: str = "US_AAPL",
    ticker: str = "AAPL",
    market: str = "Nasdaq",
):
    session.add(
        Company(
            id=company_id,
            ticker=ticker,
            name=ticker,
            market=market,
            accounting_standard="US-GAAP",
        )
    )
    await session.flush()


def _quote_result(company_id: str, provider_symbol: str, price: float = 185.0):
    return QuoteResult(
        company_id=company_id,
        provider_symbol=provider_symbol,
        price=price,
        currency="USD",
        data_delay_minutes=20,
        status="ok",
        error_message=None,
        raw_value=str(price),
        fetched_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_persists_success(session):
    await _seed_company(session)
    sheets = AsyncMock()
    sheets.refresh_quotes.return_value = [_quote_result("US_AAPL", "NASDAQ:AAPL")]
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=sheets,
    )

    result = await svc.refresh_google_sheets_quotes(company_ids=["US_AAPL"])

    assert result.requested == 1
    assert result.submitted == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.statuses == {"ok": 1}
    quote = await svc.get_latest_price("US_AAPL")
    assert quote.price == 185.0
    assert quote.provider_symbol == "NASDAQ:AAPL"


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_records_unsupported_symbol(session):
    await _seed_company(
        session,
        company_id="US_UNKNOWN",
        ticker="UNK",
        market="UNKNOWN",
    )
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=None,
    )

    result = await svc.refresh_google_sheets_quotes(company_ids=["US_UNKNOWN"])

    assert result.requested == 1
    assert result.submitted == 0
    assert result.succeeded == 0
    assert result.failed == 1
    assert result.skipped == 1
    assert result.statuses == {"unsupported_symbol": 1}
    quote = await svc.get_latest_price("US_UNKNOWN")
    assert quote.status == "unsupported_symbol"
    assert quote.price is None
    assert quote.currency is None
    assert quote.error_message == "unsupported exchange/ticker: UNKNOWN/UNK"


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_clears_as_of_for_unsupported_symbol(session):
    await _seed_company(session, company_id="US_AAPL", ticker="AAPL", market="NASDAQ")
    company_repo = CompanyRepository(session)
    quote_repo = QuotePriceRepository(session)
    await quote_repo.upsert_latest(
        {
            "company_id": "US_AAPL",
            "provider": "google_sheets",
            "provider_symbol": "NASDAQ:AAPL",
            "price": 185.0,
            "currency": "USD",
            "status": "ok",
            "as_of": datetime(2026, 4, 29, tzinfo=timezone.utc),
            "fetched_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
        }
    )
    company = await company_repo.get_by_id("US_AAPL")
    company.market = "UNKNOWN"
    await session.flush()
    svc = QuoteService(
        company_repo=company_repo,
        quote_repo=quote_repo,
        google_sheets_client=None,
    )

    await svc.refresh_google_sheets_quotes(company_ids=["US_AAPL"])

    quote = await svc.get_latest_price("US_AAPL")
    assert quote.status == "unsupported_symbol"
    assert quote.price is None
    assert quote.as_of is None


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_preserves_explicit_company_order(session):
    await _seed_company(session, "US_MSFT", "MSFT", "NASDAQ")
    await _seed_company(session, "US_AAPL", "AAPL", "Nasdaq")
    sheets = AsyncMock()
    sheets.refresh_quotes.return_value = [
        _quote_result("US_MSFT", "NASDAQ:MSFT", 410.0),
        _quote_result("US_AAPL", "NASDAQ:AAPL", 185.0),
    ]
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=sheets,
    )

    await svc.refresh_google_sheets_quotes(company_ids=["US_MSFT", "US_AAPL"])

    requests = sheets.refresh_quotes.await_args.args[0]
    assert [request.company_id for request in requests] == ["US_MSFT", "US_AAPL"]


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_empty_company_ids_is_noop(session):
    await _seed_company(session, "US_AAPL", "AAPL", "NASDAQ")
    sheets = AsyncMock()
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=sheets,
    )

    result = await svc.refresh_google_sheets_quotes(company_ids=[])

    assert result.requested == 0
    assert result.submitted == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.skipped == 0
    assert result.statuses == {}
    sheets.refresh_quotes.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_counts_missing_explicit_company_ids(session):
    await _seed_company(session, "US_AAPL", "AAPL", "NASDAQ")
    sheets = AsyncMock()
    sheets.refresh_quotes.return_value = [_quote_result("US_AAPL", "NASDAQ:AAPL")]
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=sheets,
    )

    result = await svc.refresh_google_sheets_quotes(company_ids=["US_AAPL", "US_NOPE"])

    assert result.requested == 2
    assert result.submitted == 1
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.skipped == 1
    assert result.statuses == {"missing_company": 1, "ok": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("company_id", "ticker", "market", "provider_symbol"),
    [
        ("US_MSFT", "MSFT", "NASDAQ", "NASDAQ:MSFT"),
        ("US_AAPL", "AAPL", "Nasdaq", "NASDAQ:AAPL"),
        ("US_LNG", "LNG", "AMEX", "NYSEAMERICAN:LNG"),
    ],
)
async def test_refresh_google_sheets_quotes_builds_provider_symbols(
    session,
    company_id,
    ticker,
    market,
    provider_symbol,
):
    await _seed_company(session, company_id, ticker, market)
    sheets = AsyncMock()
    sheets.refresh_quotes.return_value = [_quote_result(company_id, provider_symbol)]
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=sheets,
    )

    await svc.refresh_google_sheets_quotes(company_ids=[company_id])

    requests = sheets.refresh_quotes.await_args.args[0]
    assert [request.provider_symbol for request in requests] == [provider_symbol]


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_requires_client_when_valid_requests_exist(
    session,
):
    await _seed_company(session, "US_AAPL", "AAPL", "NASDAQ")
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=None,
    )

    with pytest.raises(ValueError, match="Google Sheets quote client is not configured"):
        await svc.refresh_google_sheets_quotes(company_ids=["US_AAPL"])

    assert await svc.get_latest_price("US_AAPL") is None


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_does_not_persist_unsupported_before_client_validation(
    session,
):
    await _seed_company(session, "US_BAD", "BAD", "UNKNOWN")
    await _seed_company(session, "US_AAPL", "AAPL", "NASDAQ")
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=None,
    )

    with pytest.raises(ValueError, match="Google Sheets quote client is not configured"):
        await svc.refresh_google_sheets_quotes(company_ids=["US_BAD", "US_AAPL"])

    assert await svc.get_latest_price("US_BAD") is None
    assert await svc.get_latest_price("US_AAPL") is None


@pytest.mark.asyncio
async def test_status_counts(session):
    await _seed_company(session)
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=AsyncMock(),
    )
    await svc._quote_repo.upsert_latest(
        {
            "company_id": "US_AAPL",
            "provider": "google_sheets",
            "provider_symbol": "NASDAQ:AAPL",
            "price": 185.0,
            "currency": "USD",
            "status": "ok",
        }
    )

    assert await svc.status_counts(provider="google_sheets") == {"ok": 1}
