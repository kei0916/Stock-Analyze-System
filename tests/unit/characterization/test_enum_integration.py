"""FilingType/PeriodType/AccountingStandard の文字列互換性を固定するテスト。

将来 StrEnum から別形式に変更された場合、argparse/DB/JSON/dict/set での
相互運用が壊れないか検知する。
"""
from __future__ import annotations

import argparse
import json

import pytest

from stock_analyze_system.cli.helpers import add_filing_type_argument
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.enums import (
    AccountingStandard,
    FilingType,
    PeriodType,
)
from stock_analyze_system.models.filing import Filing


@pytest.mark.characterization
class TestFilingTypeStringCompat:
    def test_enum_equals_plain_string(self):
        assert FilingType.TEN_K == "10-K"
        assert "10-K" == FilingType.TEN_K
        assert FilingType.TWENTY_F == "20-F"
        assert FilingType.TEN_Q == "10-Q"
        assert FilingType.SIX_K == "6-K"

    def test_enum_in_string_tuple(self):
        assert FilingType.TEN_K in ("10-K", "20-F")

    def test_string_in_enum_set(self):
        filed_forms = {FilingType.TEN_K, FilingType.TWENTY_F}
        assert "10-K" in filed_forms

    def test_dict_key_interchange(self):
        d = {FilingType.TEN_K: "annual_report"}
        assert d["10-K"] == "annual_report"

    def test_json_serializes_as_plain_string(self):
        data = {"type": FilingType.TEN_K}
        assert json.dumps(data) == '{"type": "10-K"}'


@pytest.mark.characterization
class TestFilingTypeArgparseIntegration:
    def _parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        return parser

    def test_default_is_ten_k(self):
        args = self._parser().parse_args([])
        assert args.filing_type == FilingType.TEN_K
        assert args.filing_type == "10-K"

    def test_accepts_all_valid_values(self):
        for value in ("10-K", "10-Q", "20-F", "6-K"):
            args = self._parser().parse_args(["--filing-type", value])
            assert args.filing_type == value

    def test_rejects_invalid_value(self):
        with pytest.raises(SystemExit):
            self._parser().parse_args(["--filing-type", "INVALID_FORM"])


@pytest.mark.characterization
class TestPeriodType:
    def test_string_equivalence(self):
        assert PeriodType.ANNUAL == "annual"
        assert PeriodType.QUARTERLY == "quarterly"

    def test_in_tuple_comparison(self):
        assert PeriodType.ANNUAL in ("annual", "quarterly")

    def test_json_serialization(self):
        assert json.dumps({"p": PeriodType.ANNUAL}) == '{"p": "annual"}'


@pytest.mark.characterization
class TestAccountingStandard:
    def test_values(self):
        assert AccountingStandard.US_GAAP == "US-GAAP"
        assert AccountingStandard.IFRS == "IFRS"
        assert AccountingStandard.JP_GAAP == "JP-GAAP"

    def test_string_comparison_bidirectional(self):
        assert "US-GAAP" == AccountingStandard.US_GAAP


@pytest.mark.characterization
class TestFilingTypeDatabaseRoundtrip:
    async def test_saved_as_plain_string_and_readable_both_ways(self, session):
        """FilingType を DB に保存し、str としても enum としても比較できる"""
        company = Company(
            id="US_TEST", ticker="TEST", name="Test Corp",
            market="NASDAQ", accounting_standard="US-GAAP",
        )
        session.add(company)
        await session.flush()

        filing = Filing(
            company_id="US_TEST", source="sec",
            filing_type=FilingType.TEN_K, period_type=PeriodType.ANNUAL,
            fiscal_year=2024, accession_no="test-0001",
        )
        session.add(filing)
        await session.flush()
        filing_id = filing.id

        session.expire_all()
        loaded = await session.get(Filing, filing_id)
        assert loaded.filing_type == "10-K"
        assert loaded.filing_type == FilingType.TEN_K
