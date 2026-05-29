"""FilingSyncService.update_from_sec の手動ベンチマーク (mock SEC)。"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.filing import FilingRepository
from stock_analyze_system.services.filing_sync import FilingSyncService


@pytest.mark.benchmark
@pytest.mark.parametrize("n", [100])
async def test_filing_sync_wallclock(session, n):
    session.add(Company(
        id="US_BENCH", ticker="BENCH", name="Bench",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    sec_client = AsyncMock()
    sec_client.list_filings.return_value = [
        {
            "accessionNumber": f"A-{i:06d}",
            "form": "10-K",
            "reportDate": "2024-09-28",
            "filingDate": "2024-10-15",
        }
        for i in range(n)
    ]
    edinet_client = AsyncMock()
    service = FilingSyncService(repo, sec_client, edinet_client)

    t0 = time.perf_counter()
    added = await service.update_from_sec("US_BENCH", "0000320193")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\nFilingSyncService.update_from_sec N={n}: {elapsed_ms:.1f} ms")
    assert added == n
