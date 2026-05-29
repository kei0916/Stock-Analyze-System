"""タイムゾーン付き UTC ヘルパー."""
from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    """タイムゾーン付きの現在時刻 (UTC) を返す。"""
    return datetime.now(timezone.utc)
