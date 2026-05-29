from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.quote_price import QuotePrice


async def _seed_company(session, company_id="US_AAPL", ticker="AAPL"):
    session.add(Company(
        id=company_id,
        ticker=ticker,
        name=ticker,
        market="Nasdaq",
        accounting_standard="US-GAAP",
    ))
    await session.flush()


@pytest.mark.asyncio
async def test_quote_price_unique_company_provider(session):
    await _seed_company(session)
    session.add(QuotePrice(
        company_id="US_AAPL",
        provider="google_sheets",
        provider_symbol="NASDAQ:AAPL",
        price=185.0,
        currency="USD",
        data_delay_minutes=20,
        as_of=datetime(2026, 4, 29, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        status="ok",
        raw_value="185",
    ))
    await session.flush()

    session.add(QuotePrice(
        company_id="US_AAPL",
        provider="google_sheets",
        provider_symbol="NASDAQ:AAPL",
        price=186.0,
        currency="USD",
        status="ok",
    ))

    with pytest.raises(IntegrityError):
        await session.flush()
