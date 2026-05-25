"""検証レポート JSON スキーマを固定するテスト。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_analyze_system.services.verification_report import save_verification_report

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/reports"

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


def _build_report(tmp_path: Path) -> dict:
    path = save_verification_report(
        company_id="US_AAPL", filing_id=42,
        tree=FIXED_TREE, verification_log=FIXED_LOG,
        node_count=123, output_dir=tmp_path,
    )
    return json.loads(path.read_text())


@pytest.mark.characterization
class TestVerificationReportSchema:
    def test_top_level_keys(self, tmp_path):
        data = _build_report(tmp_path)
        assert set(data.keys()) == {
            "company_id", "filing_id", "doc_name",
            "timestamp", "node_count", "phases",
        }
        assert isinstance(data["company_id"], str)
        assert isinstance(data["filing_id"], int)
        assert isinstance(data["node_count"], int)
        assert isinstance(data["phases"], list)

    def test_phase_schema(self, tmp_path):
        data = _build_report(tmp_path)
        phase = data["phases"][0]
        assert set(phase.keys()) == {
            "mode", "accuracy", "checked_count",
            "correct_count", "incorrect_count", "items",
        }
        assert isinstance(phase["items"], list)

    def test_item_schema(self, tmp_path):
        data = _build_report(tmp_path)
        item = data["phases"][0]["items"][0]
        assert set(item.keys()) == {
            "title", "page_number", "answer",
            "thinking", "page_text_snippet",
        }

    def test_matches_golden_snapshot(self, tmp_path):
        data = _build_report(tmp_path)
        expected = json.loads((FIXTURES / "expected_verification.json").read_text())
        data["timestamp"] = "REDACTED"
        assert data == expected

    def test_unicode_not_escaped(self, tmp_path):
        path = save_verification_report(
            company_id="JP_X", filing_id=1,
            tree={"doc_name": "10-K"}, verification_log=FIXED_LOG,
            node_count=1, output_dir=tmp_path,
        )
        raw = path.read_text()
        assert "売上高" in raw
        assert "\\u58f2" not in raw

    def test_two_phases_preserved(self, tmp_path):
        data = _build_report(tmp_path)
        assert len(data["phases"]) == 2
        assert data["phases"][0]["mode"] == "sampling"
        assert data["phases"][1]["mode"] == "full"
