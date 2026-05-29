"""save_verification_report の出力 JSON ゴールデンを生成。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stock_analyze_system.services.verification_report import save_verification_report

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests/fixtures/reports/expected_verification.json"

FIXED_TREE = {"doc_name": "10-K_2024_TEST"}
FIXED_LOG = [
    {
        "mode": "sampling",
        "accuracy": 0.95,
        "checked_count": 20,
        "correct_count": 19,
        "incorrect_count": 1,
        "items": [
            {
                "title": "売上高",
                "page_number": 42,
                "answer": "correct",
                "thinking": "matched financial statement",
                "page_text_snippet": "売上高は前年比...",
            }
        ],
    },
    {
        "mode": "full",
        "accuracy": 1.0,
        "checked_count": 100,
        "correct_count": 100,
        "incorrect_count": 0,
        "items": [],
    },
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = save_verification_report(
            company_id="US_AAPL", filing_id=42,
            tree=FIXED_TREE, verification_log=FIXED_LOG,
            node_count=123, output_dir=Path(tmp),
        )
        data = json.loads(path.read_text())
    data["timestamp"] = "REDACTED"
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
