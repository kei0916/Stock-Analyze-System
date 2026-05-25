"""SEC XBRL パース結果のゴールデン fixture を生成するスクリプト。

使い方:
    uv run python scripts/generate_fixtures/gen_xbrl_golden.py

現行実装の出力を tests/fixtures/xbrl/expected_parse_result.json に保存する。
実装変更時は手動で再実行し、差分を PR レビュー対象にすること。
"""
from __future__ import annotations

import json
from pathlib import Path

from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "tests/fixtures/xbrl/sample_sec_10k.json"
OUTPUT = ROOT / "tests/fixtures/xbrl/expected_parse_result.json"


def main() -> None:
    facts = json.loads(INPUT.read_text())
    parser = SecXbrlParser()
    annual = parser.parse_company_facts(facts, period_type="annual")
    quarterly = parser.parse_company_facts(facts, period_type="quarterly")
    result = {"annual": annual, "quarterly": quarterly}
    OUTPUT.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(f"Wrote {OUTPUT} ({len(annual)} annual, {len(quarterly)} quarterly records)")


if __name__ == "__main__":
    main()
