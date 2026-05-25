"""共有数値フォーマットユーティリティ（CLI, Web 共通）"""
from __future__ import annotations

import math


def fmt_number(val: float | None, precision: int = 1) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    return f"{val:.{precision}f}"


def fmt_large(val: float | None, precision: int = 1) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    if abs(val) >= 1e12:
        return f"{val / 1e12:.{precision}f}T"
    if abs(val) >= 1e9:
        return f"{val / 1e9:.{precision}f}B"
    if abs(val) >= 1e6:
        return f"{val / 1e6:.{precision}f}M"
    return f"{val:,.0f}"
