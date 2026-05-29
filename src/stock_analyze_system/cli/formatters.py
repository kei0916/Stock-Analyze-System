"""CLI出力フォーマッタ"""
from __future__ import annotations

from typing import Any

from tabulate import tabulate

from stock_analyze_system.shared.json_utils import json_dumps_ja


def fmt_number(value: float | None, precision: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{precision}f}"


def fmt_large(value: float | None, precision: int = 2) -> str:
    if value is None:
        return "N/A"
    abs_val = abs(value)
    if abs_val >= 1e9:
        return f"{value / 1e9:.{precision}f}B"
    if abs_val >= 1e6:
        return f"{value / 1e6:.{precision}f}M"
    if abs_val >= 1e3:
        return f"{value / 1e3:.{precision}f}K"
    return f"{value:.{precision}f}"


def format_table(data: list[dict], headers: list[str] | None = None) -> str:
    if not data:
        return "No data available."
    if headers is None:
        headers = list(data[0].keys())
    rows = [[str(row.get(h, "")) for h in headers] for row in data]
    return tabulate(rows, headers=headers, tablefmt="simple", disable_numparse=True)


def format_json(data: Any) -> str:
    return json_dumps_ja(data, indent=2, default=str)
