"""BaseRepository のテスト"""
import pytest
from datetime import date
from unittest.mock import AsyncMock

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.repositories.base import BaseRepository


@pytest.fixture
def repo(session):
    return BaseRepository(session, Company)


async def test_get_by_id_found(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    result = await repo.get_by_id("US_AAPL")
    assert result is not None
    assert result.ticker == "AAPL"


async def test_get_by_id_not_found(repo):
    result = await repo.get_by_id("US_NONEXIST")
    assert result is None


def test_session_property_exposes_underlying_session(session):
    repo = BaseRepository(session, Company)
    assert repo.session is session


async def test_list_all(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    results = await repo.list_all()
    assert len(results) == 2


async def test_list_all_with_filter(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    results = await repo.list_all(market="NASDAQ")
    assert len(results) == 1
    assert results[0].id == "US_AAPL"


async def test_upsert_insert(repo):
    result = await repo.upsert(
        filters={"id": "US_AAPL"},
        data={
            "id": "US_AAPL", "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        },
    )
    assert result.id == "US_AAPL"


async def test_upsert_update(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    result = await repo.upsert(
        filters={"id": "US_AAPL"},
        data={"name": "Apple Inc."},
    )
    assert result.name == "Apple Inc."


async def test_upsert_idempotent(repo):
    await repo.upsert(
        filters={"id": "US_AAPL"},
        data={
            "id": "US_AAPL", "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        },
    )
    await repo.upsert(
        filters={"id": "US_AAPL"},
        data={
            "id": "US_AAPL", "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        },
    )
    results = await repo.list_all()
    assert len(results) == 1


async def test_delete_existing(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    result = await repo.delete("US_AAPL")
    assert result is True


async def test_delete_nonexistent(repo):
    result = await repo.delete("US_NONEXIST")
    assert result is False


async def test_count(repo, session):
    assert await repo.count() == 0
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    assert await repo.count() == 1


async def test_count_with_filter(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    assert await repo.count(market="NASDAQ") == 1
    assert await repo.count(market="TSE_PRIME") == 1


async def test_bulk_upsert_native_insert(session):
    """新規レコードが INSERT されること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 394e9,
    }]
    await repo._bulk_upsert_native(
        rows,
        index_elements=[
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ],
        update_columns=["currency", "revenue"],
    )
    count = await repo.count(company_id="US_AAPL")
    assert count == 1


async def test_bulk_upsert_native_update(session):
    """重複キーで既存レコードが UPDATE されること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=100.0,
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 394e9,
    }]
    await repo._bulk_upsert_native(
        rows,
        index_elements=[
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ],
        update_columns=["revenue"],
    )
    session.expire_all()
    from sqlalchemy import select
    result = await session.execute(
        select(FinancialData).where(FinancialData.company_id == "US_AAPL"),
    )
    row = result.scalar_one()
    assert row.revenue == 394e9


async def test_bulk_upsert_native_empty_rows(session):
    """空リストを渡しても例外なく no-op で終わること"""
    repo = BaseRepository(session, FinancialData)
    await repo._bulk_upsert_native(
        [], index_elements=["company_id"], update_columns=["revenue"],
    )
    assert await repo.count() == 0


async def test_bulk_upsert_native_empty_update_columns(session):
    """update_columns 空なら on_conflict_do_nothing で既存が保持されること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=100.0,
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 999.0,
    }]
    await repo._bulk_upsert_native(
        rows,
        index_elements=[
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ],
        update_columns=[],
    )
    session.expire_all()
    from sqlalchemy import select
    result = await session.execute(
        select(FinancialData).where(FinancialData.company_id == "US_AAPL"),
    )
    row = result.scalar_one()
    assert row.revenue == 100.0


async def test_bulk_upsert_native_chunks_large_insert(session):
    """SEC universe 規模の insert-only upsert が SQLite 変数上限を超えないこと。"""
    repo = BaseRepository(session, Company)
    rows = [
        {
            "id": f"US_T{i}",
            "ticker": f"T{i}",
            "name": f"Ticker {i}",
            "market": "Nasdaq",
            "accounting_standard": "US-GAAP",
            "cik": f"{i:010d}",
        }
        for i in range(6000)
    ]

    await repo._bulk_upsert_native(
        rows,
        index_elements=["id"],
        update_columns=[],
    )

    assert await repo.count() == 6000


async def test_bulk_upsert_by_natural_key_without_scope(session):
    """scope なし: natural_key_cols をそのまま index として扱う。"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 1.0,
    }]
    n = await repo._bulk_upsert_by_natural_key(
        rows,
        natural_key_cols=(
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ),
    )
    assert n == 1
    assert await repo.count(company_id="US_AAPL") == 1


async def test_bulk_upsert_by_natural_key_with_scope(session):
    """scope あり: scope_key/value を各 row に前置して保存する。"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    records = [{
        "accounting_standard": "US-GAAP", "currency": "USD",
        "period_type": "annual", "fiscal_year_end": date(2024, 9, 28),
        "revenue": 2.0,
    }]
    n = await repo._bulk_upsert_by_natural_key(
        records,
        natural_key_cols=(
            "period_type", "fiscal_year_end", "accounting_standard",
        ),
        scope_key="company_id",
        scope_value="US_AAPL",
    )
    assert n == 1
    assert await repo.count(company_id="US_AAPL") == 1


async def test_bulk_upsert_by_natural_key_empty_records(session):
    """空入力なら 0 を返して no-op。"""
    repo = BaseRepository(session, FinancialData)
    n = await repo._bulk_upsert_by_natural_key([], natural_key_cols=("company_id",))
    assert n == 0
    assert await repo.count() == 0


async def test_bulk_upsert_by_natural_key_no_update_columns(session):
    """natural_key が全 row キーを覆う場合は update_columns が空になる。"""
    repo = BaseRepository(session, FinancialData)
    repo._bulk_upsert_native = AsyncMock()  # type: ignore[method-assign]
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "fiscal_year_end": date(2024, 9, 28),
        "period_type": "annual",
    }]
    n = await repo._bulk_upsert_by_natural_key(
        rows,
        natural_key_cols=(
            "company_id", "accounting_standard", "fiscal_year_end", "period_type",
        ),
    )
    assert n == 1
    repo._bulk_upsert_native.assert_awaited_once_with(
        rows,
        index_elements=[
            "company_id", "accounting_standard", "fiscal_year_end", "period_type",
        ],
        update_columns=[],
    )
