"""taxonomy ランタイム関数のテスト"""
from stock_analyze_system.ingestion.xbrl.taxonomy import (
    detect_currency,
    detect_taxonomy,
    find_unit_data,
    pick_unit,
)


class TestDetectTaxonomy:
    def test_us_gaap_detected(self):
        facts = {"facts": {"us-gaap": {"Revenue": {}}, "ifrs-full": {}}}
        name, data, currency = detect_taxonomy(facts)
        assert name == "us-gaap"
        assert data == {"Revenue": {}}
        assert currency == "USD"

    def test_ifrs_when_more_facts(self):
        facts = {"facts": {"us-gaap": {"A": {}}, "ifrs-full": {"A": {}, "B": {}}}}
        name, data, currency = detect_taxonomy(facts)
        assert name == "ifrs-full"
        assert len(data) == 2

    def test_ifrs_only_no_us_gaap(self):
        facts = {"facts": {"ifrs-full": {"Revenue": {}}}}
        name, _, _ = detect_taxonomy(facts)
        assert name == "ifrs-full"

    def test_empty_facts(self):
        facts = {"facts": {}}
        name, data, currency = detect_taxonomy(facts)
        assert name == "us-gaap"
        assert data == {}
        assert currency == "USD"

    def test_no_facts_key(self):
        name, data, currency = detect_taxonomy({})
        assert name == "us-gaap"
        assert currency == "USD"

    def test_both_empty_returns_us_gaap(self):
        facts = {"facts": {"us-gaap": {}, "ifrs-full": {}}}
        name, _, currency = detect_taxonomy(facts)
        assert name == "us-gaap"
        assert currency == "USD"


class TestDetectCurrency:
    def test_non_usd_currency(self):
        facts = {"Revenue": {"units": {"EUR": [{}]}}}
        assert detect_currency(facts) == "EUR"

    def test_usd_currency(self):
        facts = {"Revenue": {"units": {"USD": [{}]}}}
        assert detect_currency(facts) == "USD"

    def test_skips_pure_and_shares(self):
        facts = {"Revenue": {"units": {"pure": [{}], "shares": [{}], "JPY": [{}]}}}
        assert detect_currency(facts) == "JPY"

    def test_skips_ratio_units(self):
        facts = {"Revenue": {"units": {"USD/shares": [{}], "GBP": [{}]}}}
        assert detect_currency(facts) == "GBP"

    def test_fallback_usd_when_empty(self):
        assert detect_currency({}) == "USD"

    def test_usd_when_only_usd_present(self):
        facts = {"Revenue": {"units": {"USD/shares": [{}], "USD": [{}]}}}
        assert detect_currency(facts) == "USD"

    def test_probe_tag_missing_continues(self):
        """Revenue がなくても Assets で検出"""
        facts = {"Assets": {"units": {"GBP": [{}]}}}
        assert detect_currency(facts) == "GBP"

    def test_probe_tag_without_units(self):
        facts = {"Revenue": {}}
        assert detect_currency(facts) == "USD"


class TestPickUnit:
    def test_eps(self):
        assert pick_unit("eps", "JPY") == "JPY/shares"

    def test_dps(self):
        assert pick_unit("dps", "USD") == "USD/shares"

    def test_shares_outstanding(self):
        assert pick_unit("shares_outstanding", "USD") == "USD/shares"

    def test_non_share_field(self):
        assert pick_unit("revenue", "EUR") == "EUR"

    def test_non_share_with_usd(self):
        assert pick_unit("total_assets", "USD") == "USD"


class TestFindUnitData:
    def test_exact_match(self):
        tag = {"units": {"JPY": [{"val": 1}]}}
        assert find_unit_data(tag, "JPY") == [{"val": 1}]

    def test_fallback_usd_shares_for_non_usd_shares(self):
        tag = {"units": {"USD/shares": [{"val": 2}]}}
        result = find_unit_data(tag, "JPY/shares")
        assert result == [{"val": 2}]

    def test_fallback_any_currency_shares(self):
        tag = {"units": {"EUR/shares": [{"val": 3}]}}
        result = find_unit_data(tag, "JPY/shares")
        assert result == [{"val": 3}]

    def test_fallback_pure_shares(self):
        tag = {"units": {"shares": [{"val": 4}]}}
        result = find_unit_data(tag, "JPY/shares")
        assert result == [{"val": 4}]

    def test_fallback_usd_for_non_usd_currency(self):
        tag = {"units": {"USD": [{"val": 5}]}}
        result = find_unit_data(tag, "EUR")
        assert result == [{"val": 5}]

    def test_last_resort_usd_shares(self):
        tag = {"units": {"USD/shares": [{"val": 6}]}}
        result = find_unit_data(tag, "USD")
        assert result == [{"val": 6}]

    def test_returns_none_when_no_match(self):
        tag = {"units": {}}
        assert find_unit_data(tag, "JPY") is None

    def test_no_units_key(self):
        assert find_unit_data({}, "USD") is None

    def test_usd_not_fallback_to_self(self):
        """USD要求でUSD以外しかない場合、USD/sharesにフォールバック"""
        tag = {"units": {"EUR": [{"val": 7}]}}
        # USD requested, EUR available, no USD/shares → None
        assert find_unit_data(tag, "USD") is None
