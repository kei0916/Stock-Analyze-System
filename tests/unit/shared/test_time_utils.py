"""shared.time_utils 単体テスト"""
from __future__ import annotations

from datetime import datetime, timezone

from stock_analyze_system.shared.time_utils import now_utc


def test_now_utc_returns_aware_utc_datetime():
    n = now_utc()
    assert isinstance(n, datetime)
    assert n.tzinfo is not None
    assert n.utcoffset() == timezone.utc.utcoffset(n)
