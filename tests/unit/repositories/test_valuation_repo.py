"""ValuationRepository のテスト"""
from datetime import date

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.repositories.valuation import ValuationRepository


async def test_get_history(session):
    """履歴を date 降順で取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    for month in (1, 2, 3):
        session.add(Valuation(
            company_id="US_AAPL", currency="USD",
            date=date(2026, month, 1), stock_price=180.0 + month,
        ))
    await session.flush()
    repo = ValuationRepository(session)
    results = await repo.get_history("US_AAPL", years=1)
    assert len(results) == 3
    assert results[0].date > results[1].date


async def test_get_latest(session):
    """最新バリュエーションを取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Valuation(
        company_id="US_AAPL", currency="USD",
        date=date(2024, 1, 1), stock_price=185.0, per=28.5,
    ))
    session.add(Valuation(
        company_id="US_AAPL", currency="USD",
        date=date(2024, 6, 1), stock_price=210.0, per=32.0,
    ))
    await session.flush()
    repo = ValuationRepository(session)
    result = await repo.get_latest("US_AAPL")
    assert result is not None
    assert result.date == date(2024, 6, 1)


async def test_bulk_upsert(session):
    """一括 upsert が動作すること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ValuationRepository(session)
    records = [
        {"currency": "USD", "date": date(2024, 1, 1), "stock_price": 185.0},
        {"currency": "USD", "date": date(2024, 2, 1), "stock_price": 190.0},
    ]
    count = await repo.bulk_upsert("US_AAPL", records)
    assert count == 2
