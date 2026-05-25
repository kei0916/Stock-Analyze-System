# tests/unit/repositories/test_price_history_repo.py
from datetime import date, timedelta

import pytest

from stock_analyze_system.repositories.price_history import PriceHistoryRepository, _CHUNK_SIZE
from stock_analyze_system.models.price_history import PriceHistory
from sqlalchemy import select

@pytest.mark.asyncio
async def test_upsert_many_creates_records(session):
    repo = PriceHistoryRepository(session)
    rows = [
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 5, 8), "close": 100.0},
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 5, 7), "close": 99.0},
    ]
    count = await repo.upsert_many(rows)
    assert count == 2
    
    result = await session.execute(select(PriceHistory).where(PriceHistory.company_id == "US_AAPL"))
    assert len(result.scalars().all()) == 2

@pytest.mark.asyncio
async def test_upsert_many_chunked(session):
    repo = PriceHistoryRepository(session)
    rows = [
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 1, 1) + timedelta(days=i), "close": float(i)}
        for i in range(_CHUNK_SIZE + 10)
    ]
    count = await repo.upsert_many(rows)
    assert count == _CHUNK_SIZE + 10


@pytest.mark.asyncio
async def test_get_company_stats(session):
    """統計情報の取得をテスト"""
    repo = PriceHistoryRepository(session)
    
    # テストデータ投入
    rows = [
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 1, 1), "close": 100.0},
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 1, 2), "close": 101.0},
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 1, 3), "close": 102.0},
        {"company_id": "US_MSFT", "ticker": "MSFT", "date": date(2021, 1, 1), "close": 200.0},
    ]
    await repo.upsert_many(rows)
    
    stats = await repo.get_company_stats()
    
    assert "US_AAPL" in stats
    assert stats["US_AAPL"]["rows"] == 3
    assert stats["US_AAPL"]["min_date"] == date(2021, 1, 1)
    assert stats["US_AAPL"]["max_date"] == date(2021, 1, 3)
    assert stats["US_AAPL"]["span_days"] == 2
    
    assert "US_MSFT" in stats
    assert stats["US_MSFT"]["rows"] == 1
    assert stats["US_MSFT"]["span_days"] == 0


@pytest.mark.asyncio
async def test_get_incomplete_companies_filters_new_listings(session):
    """新規上場（90日未満）は除外されることをテスト"""
    repo = PriceHistoryRepository(session)
    
    # US_NEW: 10行、30日スパン（新規上場 → 除外されるべき）
    # US_GAP: 50行、200日スパン（取得失敗 → 含まれるべき）
    # US_OK: 300行、365日スパン（完全 → 除外されるべき）
    rows = []
    for i in range(10):
        rows.append({"company_id": "US_NEW", "ticker": "NEW", "date": date(2021, 1, 1) + timedelta(days=i), "close": float(i)})
    for i in range(50):
        rows.append({"company_id": "US_GAP", "ticker": "GAP", "date": date(2021, 1, 1) + timedelta(days=i*4), "close": float(i)})
    for i in range(300):
        rows.append({"company_id": "US_OK", "ticker": "OK", "date": date(2021, 1, 1) + timedelta(days=i), "close": float(i)})
    
    await repo.upsert_many(rows)
    
    incomplete = await repo.get_incomplete_companies(min_span_days=90, min_rows=250)
    
    assert "US_NEW" not in incomplete  # 新規上場は除外
    assert "US_GAP" in incomplete      # 取得失敗は含む
    assert "US_OK" not in incomplete   # 完全データは除外


@pytest.mark.asyncio
async def test_get_incomplete_companies_boundary_values(session):
    """境界値テスト: span=89/90, rows=249/250"""
    repo = PriceHistoryRepository(session)
    
    # US_B1: span=89日, rows=50 → 新規上場（span < 90 → 除外）
    # US_B2: span=90日, rows=50 → 取得失敗（span >= 90 かつ rows < 250 → 含む）
    # US_B3: span=90日, rows=250 → 完全データ（span >= 90 かつ rows >= 250 → 除外）
    rows = []
    for i in range(50):
        rows.append({"company_id": "US_B1", "ticker": "B1", "date": date(2021, 1, 1) + timedelta(days=i), "close": float(i)})
    for i in range(50):
        rows.append({"company_id": "US_B2", "ticker": "B2", "date": date(2021, 1, 1) + timedelta(days=i), "close": float(i)})
    rows.append({"company_id": "US_B2", "ticker": "B2", "date": date(2021, 1, 1) + timedelta(days=90), "close": 90.0})
    for i in range(250):
        rows.append({"company_id": "US_B3", "ticker": "B3", "date": date(2021, 1, 1) + timedelta(days=i), "close": float(i)})
    
    await repo.upsert_many(rows)
    
    incomplete = await repo.get_incomplete_companies(min_span_days=90, min_rows=250)
    
    assert "US_B1" not in incomplete  # span=89 < 90 → 新規上場
    assert "US_B2" in incomplete      # span=90 >= 90, rows=249 < 250 → 取得失敗
    assert "US_B3" not in incomplete  # span=90 >= 90, rows=250 >= 250 → 完全
