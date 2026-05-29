"""bulk_upsert の手動ベンチマーク。通常 pytest では除外され、
`uv run pytest -m benchmark tests/benchmarks/ -s` で明示実行する。"""
from __future__ import annotations

import time
from datetime import date

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.repositories.valuation import ValuationRepository


@pytest.mark.benchmark
@pytest.mark.parametrize("n", [50, 500])
async def test_financial_bulk_upsert_wallclock(session, n):
    session.add(Company(
        id="US_BENCH", ticker="BENCH", name="Bench",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FinancialRepository(session)
    records = [
        {
            "accounting_standard": "US-GAAP",
            "currency": "USD",
            "period_type": "annual",
            "fiscal_year_end": date(1000 + i, 12, 31),
            "revenue": float(i * 1e7),
            "net_income": float(i * 1e6),
        }
        for i in range(n)
    ]

    t0 = time.perf_counter()
    count = await repo.bulk_upsert("US_BENCH", records)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\nFinancialRepository.bulk_upsert N={n}: {elapsed_ms:.1f} ms")
    assert count == n


@pytest.mark.benchmark
@pytest.mark.parametrize("n", [50])
async def test_valuation_bulk_upsert_wallclock(session, n):
    from datetime import timedelta
    session.add(Company(
        id="US_BENCH", ticker="BENCH", name="Bench",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ValuationRepository(session)
    base = date(2000, 1, 1)
    records = [
        {"currency": "USD", "date": base + timedelta(days=i), "per": float(i)}
        for i in range(n)
    ]

    t0 = time.perf_counter()
    count = await repo.bulk_upsert("US_BENCH", records)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\nValuationRepository.bulk_upsert N={n}: {elapsed_ms:.1f} ms")
    assert count == n
