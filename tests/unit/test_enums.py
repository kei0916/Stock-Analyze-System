"""Enum定義のテスト"""
from stock_analyze_system.models.enums import (
    AccountingStandard, FilingSource, FilingType, PeriodType,
)


class TestFilingType:
    def test_values(self):
        assert FilingType.TEN_K == "10-K"
        assert FilingType.TEN_Q == "10-Q"
        assert FilingType.TWENTY_F == "20-F"
        assert FilingType.SIX_K == "6-K"
        assert FilingType.ANNUAL_REPORT == "annual_report"
        assert FilingType.QUARTERLY_REPORT == "quarterly_report"

    def test_str_comparison(self):
        assert FilingType.TEN_K == "10-K"
        assert "10-K" == FilingType.TEN_K

    def test_list_for_choices(self):
        choices = list(FilingType)
        assert len(choices) == 6


class TestPeriodType:
    def test_values(self):
        assert PeriodType.ANNUAL == "annual"
        assert PeriodType.QUARTERLY == "quarterly"


class TestAccountingStandard:
    def test_values(self):
        assert AccountingStandard.US_GAAP == "US-GAAP"
        assert AccountingStandard.IFRS == "IFRS"
        assert AccountingStandard.JP_GAAP == "JP-GAAP"


class TestFilingSource:
    def test_values(self):
        assert FilingSource.SEC == "SEC"
        assert FilingSource.EDINET == "EDINET"
