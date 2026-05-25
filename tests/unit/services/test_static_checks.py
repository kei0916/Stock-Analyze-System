"""Static guards for queue/worker regressions."""
from __future__ import annotations

from stock_analyze_system.services.pageindex import compat


def test_st01_pageindex_async_helpers_are_available():
    assert compat._HAS_PAGEINDEX_ASYNC_HELPERS is True, (
        "PageIndex async helpers must be importable; falling back to sync "
        "page_index() would reintroduce the asyncio.run() deadlock."
    )
