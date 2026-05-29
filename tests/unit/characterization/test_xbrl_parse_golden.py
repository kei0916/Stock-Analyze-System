"""SEC XBRL パーサーの出力を固定するゴールデンテスト。

将来パーサーがリファクタされた場合でも入出力が一致することを保証する。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser
from stock_analyze_system.ingestion.xbrl.period_filter import (
    ANNUAL_MIN_DAYS,
    QUARTERLY_MAX_DAYS,
    duration_ok,
)
from stock_analyze_system.ingestion.xbrl.taxonomy import detect_taxonomy

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/xbrl"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.characterization
class TestSecXbrlParserGolden:
    def test_annual_parse_matches_golden(self):
        facts = _load("sample_sec_10k.json")
        expected = _load("expected_parse_result.json")
        parser = SecXbrlParser()
        result = parser.parse_company_facts(facts, period_type="annual")
        result_normalized = json.loads(json.dumps(result, default=str))
        assert result_normalized == expected["annual"]

    def test_quarterly_parse_matches_golden(self):
        facts = _load("sample_sec_10k.json")
        expected = _load("expected_parse_result.json")
        parser = SecXbrlParser()
        result = parser.parse_company_facts(facts, period_type="quarterly")
        result_normalized = json.loads(json.dumps(result, default=str))
        assert result_normalized == expected["quarterly"]


@pytest.mark.characterization
class TestPeriodFilterBoundaries:
    def test_duration_ok_annual_exactly_min_days(self):
        assert duration_ok(ANNUAL_MIN_DAYS, "annual") is True

    def test_duration_ok_annual_below_min(self):
        assert duration_ok(ANNUAL_MIN_DAYS - 1, "annual") is False

    def test_duration_ok_quarterly_exactly_max(self):
        assert duration_ok(QUARTERLY_MAX_DAYS, "quarterly") is True

    def test_duration_ok_quarterly_above_max(self):
        assert duration_ok(QUARTERLY_MAX_DAYS + 1, "quarterly") is False


@pytest.mark.characterization
class TestTaxonomyDetection:
    def test_detect_us_gaap(self):
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": []}}}}}
        taxonomy, _subtree, currency = detect_taxonomy(facts)
        assert taxonomy == "us-gaap"
        assert currency == "USD"

    def test_detect_ifrs(self):
        facts = {
            "facts": {
                "ifrs-full": {
                    "Revenue": {"units": {"EUR": [{"val": 1}]}},
                    "Assets": {"units": {"EUR": [{"val": 1}]}},
                }
            }
        }
        taxonomy, _subtree, currency = detect_taxonomy(facts)
        assert taxonomy == "ifrs-full"
        assert currency == "EUR"
