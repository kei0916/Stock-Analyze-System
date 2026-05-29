from datetime import datetime, timedelta, timezone

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.quote_price import QuotePriceRepository


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
async def test_upsert_latest_quote_updates_same_provider(session):
    await _seed_company(session)
    repo = QuotePriceRepository(session)

    first = await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
        "fetched_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
    })
    second = await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 186.0,
        "currency": "USD",
        "status": "ok",
        "fetched_at": datetime(2026, 4, 30, tzinfo=timezone.utc),
    })

    assert first.id == second.id
    latest = await repo.get_latest("US_AAPL", provider="google_sheets")
    assert latest.price == 186.0


@pytest.mark.asyncio
async def test_upsert_latest_normalizes_aware_datetimes_to_utc_naive(session):
    await _seed_company(session)
    repo = QuotePriceRepository(session)
    japan_time = timezone(timedelta(hours=9))

    await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
        "as_of": datetime(2026, 4, 29, 9, 0, tzinfo=japan_time),
        "fetched_at": datetime(2026, 4, 29, 9, 0, tzinfo=japan_time),
    })

    latest = await repo.get_latest("US_AAPL", provider="google_sheets")

    assert latest.as_of == datetime(2026, 4, 29, 0, 0)
    assert latest.fetched_at == datetime(2026, 4, 29, 0, 0)


@pytest.mark.asyncio
async def test_status_counts_and_failed_listing(session):
    await _seed_company(session, "US_AAPL", "AAPL")
    await _seed_company(session, "US_BAD", "BAD")
    repo = QuotePriceRepository(session)

    await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
    })
    await repo.upsert_latest({
        "company_id": "US_BAD",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:BAD",
        "price": None,
        "currency": None,
        "status": "formula_error",
        "error_message": "#N/A",
    })

    counts = await repo.count_by_status(provider="google_sheets")
    failed = await repo.list_failed(provider="google_sheets", limit=10)

    assert counts == {"formula_error": 1, "ok": 1}
    assert [row.company_id for row in failed] == ["US_BAD"]


@pytest.mark.asyncio
async def test_list_stale(session):
    await _seed_company(session)
    repo = QuotePriceRepository(session)
    old = datetime.now(timezone.utc) - timedelta(hours=30)

    await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
        "fetched_at": old,
    })

    stale = await repo.list_stale(provider="google_sheets", max_age_hours=24, limit=10)
    assert [row.company_id for row in stale] == ["US_AAPL"]
