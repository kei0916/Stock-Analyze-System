"""compute_valuation_from_financials の出力ゴールデンを生成。

使い方: uv run python scripts/generate_fixtures/gen_valuation_golden.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from stock_analyze_system.services.valuation import compute_valuation_from_financials

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests/fixtures/valuation/expected_valuation.json"


@dataclass
class _FD:
    """FinancialData stand-in"""
    eps: float | None
    net_income: float | None
    equity: float | None
    shares_outstanding: float | None
    total_debt: float | None
    cash: float | None
    ebitda: float | None
    revenue: float | None
    fcf: float | None


def main() -> None:
    fd = _FD(
        eps=6.16, net_income=96995000000.0,
        equity=62146000000.0, shares_outstanding=15800000000.0,
        total_debt=111088000000.0, cash=29965000000.0,
        ebitda=125820000000.0, revenue=383285000000.0,
        fcf=99584000000.0,
    )
    result = compute_valuation_from_financials(
        stock_price=150.0, fd=fd, currency="USD",
        val_date=date(2023, 9, 30), market_cap=None,
    )
    OUTPUT.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
