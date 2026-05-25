"""共有フォーマッタのテスト"""
import pytest
from stock_analyze_system.shared.formatters import fmt_number, fmt_large


class TestFmtNumber:
    @pytest.mark.parametrize("val, precision, expected", [
        (1.234, 1, "1.2"),
        (1.256, 2, "1.26"),
        (0.0, 1, "0.0"),
        (-5.5, 1, "-5.5"),
        (None, 1, "N/A"),
    ])
    def test_fmt_number(self, val, precision, expected):
        assert fmt_number(val, precision) == expected


class TestFmtLarge:
    @pytest.mark.parametrize("val, expected", [
        (1.5e12, "1.5T"),
        (2.3e9, "2.3B"),
        (45.6e6, "45.6M"),
        (999999, "999,999"),
        (0, "0"),
        (-2.5e9, "-2.5B"),
        (None, "N/A"),
    ])
    def test_fmt_large(self, val, expected):
        assert fmt_large(val) == expected
