# tests/unit/cli/test_formatters.py
"""CLI formatters のテスト"""
import json

from stock_analyze_system.cli.formatters import (
    fmt_large,
    fmt_number,
    format_json,
    format_table,
)


class TestFmtNumber:
    def test_normal(self):
        assert fmt_number(3.14159, precision=2) == "3.14"

    def test_none(self):
        assert fmt_number(None) == "N/A"

    def test_zero(self):
        assert fmt_number(0.0) == "0.00"


class TestFmtLarge:
    def test_billion(self):
        result = fmt_large(2_500_000_000.0)
        assert "B" in result

    def test_million(self):
        result = fmt_large(45_000_000.0)
        assert "M" in result

    def test_thousand(self):
        result = fmt_large(8_500.0)
        assert "K" in result

    def test_small(self):
        result = fmt_large(500.0)
        assert result == "500.00"

    def test_none(self):
        assert fmt_large(None) == "N/A"


class TestFormatTable:
    def test_basic(self):
        data = [{"Name": "Apple", "Price": 185.0}]
        result = format_table(data)
        assert "Apple" in result
        assert "185" in result

    def test_empty(self):
        result = format_table([])
        assert "No data" in result

    def test_custom_headers(self):
        data = [{"a": 1, "b": 2, "c": 3}]
        result = format_table(data, headers=["a", "b"])
        assert "1" in result


class TestFormatJson:
    def test_dict(self):
        result = format_json({"key": "value"})
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_list(self):
        result = format_json([1, 2, 3])
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_non_serializable(self):
        from datetime import date
        result = format_json({"d": date(2024, 1, 1)})
        parsed = json.loads(result)
        assert "2024-01-01" in parsed["d"]
