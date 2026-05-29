"""DBモデル基盤のテスト"""
import pytest

from stock_analyze_system.models.base import get_session
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.models.document_index import DocumentIndex
from datetime import date


async def test_get_session_commit(async_engine):
    """セッションが正常にコミットされること"""
    async with get_session(async_engine) as session:
        assert session is not None


async def test_get_session_rollback_on_error(async_engine):
    """例外時にロールバックされること"""
    with pytest.raises(ValueError):
        async with get_session(async_engine) as _session:
            raise ValueError("test error")


async def test_company_crud(session):
    company = Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP", cik="0000320193",
    )
    session.add(company)
    await session.flush()
    result = await session.get(Company, "US_AAPL")
    assert result is not None
    assert result.ticker == "AAPL"


async def test_jp_company(session):
    company = Company(
        id="JP_7203", security_code="7203", name="Toyota Motor Corporation",
        name_ja="トヨタ自動車株式会社", market="TSE_PRIME",
        accounting_standard="IFRS", edinet_code="E02144",
    )
    session.add(company)
    await session.flush()
    result = await session.get(Company, "JP_7203")
    assert result.name_ja == "トヨタ自動車株式会社"


async def test_financial_data_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    fd = FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=394328000000,
    )
    session.add(fd)
    await session.flush()
    assert fd.id is not None
    assert fd.revenue == 394328000000


async def test_financial_data_unique_constraint(session):
    from sqlalchemy.exc import IntegrityError
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    fd1 = FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual", fiscal_year_end=date(2024, 9, 28),
    )
    fd2 = FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual", fiscal_year_end=date(2024, 9, 28),
    )
    session.add(fd1)
    await session.flush()
    session.add(fd2)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_valuation_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    v = Valuation(
        company_id="US_AAPL", currency="USD", date=date(2024, 1, 1),
        stock_price=185.0, per=28.5,
    )
    session.add(v)
    await session.flush()
    assert v.id is not None


async def test_filing_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    )
    session.add(f)
    await session.flush()
    assert f.id is not None


async def test_document_index_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    )
    session.add(f)
    await session.flush()
    di = DocumentIndex(
        filing_id=f.id, company_id="US_AAPL",
        index_json='{"nodes": []}', model_name="ollama/gptoss20b:q8",
        page_count=142, node_count=47,
    )
    session.add(di)
    await session.flush()
    assert di.id is not None


async def test_watchlist_cascade(session):
    wl = Watchlist(name="My Watchlist")
    session.add(wl)
    await session.flush()
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    item = WatchlistItem(watchlist_id=wl.id, company_id="US_AAPL")
    session.add(item)
    await session.flush()
    assert item.id is not None
