# tests/integration/test_stooq_download.py
from datetime import date

import httpx
import pytest

from stock_analyze_system.ingestion.stooq import StooqError, StooqPriceClient


@pytest.mark.asyncio
async def test_stooq_client_fetch_aapl_real():
    """Real network test — requires valid API key."""
    import os

    api_key = os.getenv("STOOQ_API_KEY")
    if not api_key:
        pytest.skip("STOOQ_API_KEY not set")

    client = StooqPriceClient(api_key=api_key, rate=1.0)
    try:
        try:
            rows = await client.fetch_history("AAPL", years=1)
        except (StooqError, httpx.HTTPError) as exc:
            pytest.skip(f"Stooq real network/API unavailable: {exc}")
        assert len(rows) > 200  # ~1 year of trading days
        assert all(r["ticker"] == "AAPL" for r in rows)
        assert all(isinstance(r["date"], date) for r in rows)
        # Verify ascending order (oldest first)
        for i in range(1, len(rows)):
            assert rows[i]["date"] >= rows[i - 1]["date"]
    finally:
        await client.close()
