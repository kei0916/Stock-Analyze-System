"""FinancialRepository のテスト"""
from datetime import date

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.repositories.financial import FinancialRepository


async def test_get_timeseries(session):
    """時系列データを fiscal_year_end 降順で取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    for yr in (2022, 2023, 2024):
        session.add(FinancialData(
            company_id="US_AAPL", accounting_standard="US-GAAP",
            currency="USD", period_type="annual",
            fiscal_year_end=date(yr, 9, 28), revenue=float(yr * 1e9),
        ))
    await session.flush()
    repo = FinancialRepository(session)
    results = await repo.get_timeseries("US_AAPL", "annual", years=5)
    assert len(results) == 3
    assert results[0].fiscal_year_end > results[1].fiscal_year_end


async def test_get_latest(session):
    """最新レコードを1件取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2023, 9, 28), revenue=383e9,
    ))
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=394e9,
    ))
    await session.flush()
    repo = FinancialRepository(session)
    result = await repo.get_latest("US_AAPL", "annual")
    assert result is not None
    assert result.fiscal_year_end == date(2024, 9, 28)


async def test_get_latest_none(session):
    """データなしの場合 None を返すこと"""
    repo = FinancialRepository(session)
    result = await repo.get_latest("US_NONEXIST", "annual")
    assert result is None


async def test_bulk_upsert(session):
    """一括 upsert で新規挿入と更新が動作すること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FinancialRepository(session)
    records = [
        {
            "accounting_standard": "US-GAAP", "currency": "USD",
            "period_type": "annual", "fiscal_year_end": date(2024, 9, 28),
            "revenue": 394e9,
        },
    ]
    count = await repo.bulk_upsert("US_AAPL", records)
    assert count == 1
    # 再実行で更新されること
    records[0]["revenue"] = 400e9
    count = await repo.bulk_upsert("US_AAPL", records)
    assert count == 1
    result = await repo.get_latest("US_AAPL", "annual")
    assert result.revenue == 400e9
