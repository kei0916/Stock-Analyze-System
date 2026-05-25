# tests/unit/ingestion/test_sec_xbrl_parser.py
"""SEC XBRL パーサーのテスト (10-K/10-Q/20-F/6-K)"""
import pytest
import yaml
from unittest.mock import patch

SAMPLE_US_GAAP_FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01", "end": "2023-09-30",
                            "val": 383285000000, "form": "10-K",
                            "fy": 2023, "fp": "FY",
                        },
                        {
                            "start": "2023-10-01", "end": "2024-09-28",
                            "val": 391035000000, "form": "10-K",
                            "fy": 2024, "fp": "FY",
                        },
                        {
                            "end": "2024-06-29", "val": 85777000000,
                            "form": "10-Q", "fy": 2024, "fp": "Q3",
                        },
                    ],
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income (Loss)",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01", "end": "2023-09-30",
                            "val": 96995000000, "form": "10-K",
                            "fy": 2023, "fp": "FY",
                        },
                        {
                            "start": "2023-10-01", "end": "2024-09-28",
                            "val": 93736000000, "form": "10-K",
                            "fy": 2024, "fp": "FY",
                        },
                    ],
                },
            },
            "EarningsPerShareDiluted": {
                "label": "Earnings Per Share, Diluted",
                "units": {
                    "USD/shares": [
                        {
                            "start": "2022-10-01", "end": "2023-09-30",
                            "val": 6.16, "form": "10-K",
                            "fy": 2023, "fp": "FY",
                        },
                    ],
                },
            },
        },
    },
}

SAMPLE_IFRS_FACTS = {
    "cik": 1046179,
    "entityName": "Taiwan Semiconductor Manufacturing Co Ltd",
    "facts": {
        "ifrs-full": {
            "Revenue": {
                "label": "Revenue",
                "units": {
                    "TWD": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 2263891200000, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                        {
                            "start": "2023-01-01", "end": "2023-12-31",
                            "val": 2161735800000, "form": "20-F",
                            "fy": 2023, "fp": "FY",
                        },
                    ],
                    "USD": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 75882500000, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                    ],
                },
            },
            "ProfitLoss": {
                "label": "Profit (loss)",
                "units": {
                    "TWD": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 1016530200000, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                        {
                            "start": "2023-04-01", "end": "2023-06-30",
                            "val": 300000000000, "form": "6-K",
                            "fy": 2023, "fp": None,
                        },
                    ],
                },
            },
            "Assets": {
                "label": "Assets",
                "units": {
                    "TWD": [
                        {
                            "end": "2022-12-31", "val": 5765188300000,
                            "form": "20-F", "fy": 2022, "fp": "FY",
                        },
                    ],
                },
            },
            "DilutedEarningsLossPerShare": {
                "label": "Diluted EPS",
                "units": {
                    "TWD/shares": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 39.2, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                    ],
                },
            },
        },
    },
}


@pytest.fixture
def us_gaap_mapping(tmp_path):
    mapping = {
        "revenue": ["us-gaap:Revenues", "us-gaap:SalesRevenueNet"],
        "net_income": ["us-gaap:NetIncomeLoss"],
        "eps": ["us-gaap:EarningsPerShareDiluted"],
        "total_assets": [],
    }
    p = tmp_path / "us_gaap_mapping.yaml"
    p.write_text(yaml.dump(mapping))
    return p


@pytest.fixture
def ifrs_mapping(tmp_path):
    mapping = {
        "revenue": ["ifrs-full:Revenue"],
        "net_income": ["ifrs-full:ProfitLoss"],
        "eps": ["ifrs-full:DilutedEarningsLossPerShare"],
        "total_assets": ["ifrs-full:Assets"],
    }
    p = tmp_path / "ifrs_mapping.yaml"
    p.write_text(yaml.dump(mapping))
    return p


@pytest.fixture
def parser(us_gaap_mapping, ifrs_mapping):
    from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser
    from stock_analyze_system.ingestion.xbrl.taxonomy import TAXONOMY_MAPPING_FILES
    with patch.dict(TAXONOMY_MAPPING_FILES, {
        "us-gaap": str(us_gaap_mapping),
        "ifrs-full": str(ifrs_mapping),
    }):
        return SecXbrlParser()


class TestTenK:
    def test_parse_annual(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        assert len(results) >= 2
        fy2023 = next(r for r in results if r["fiscal_year_end"] == "2023-09-30")
        assert fy2023["revenue"] == 383285000000
        assert fy2023["net_income"] == 96995000000
        assert fy2023["currency"] == "USD"

    def test_eps_from_usd_shares(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        fy2023 = next(r for r in results if r["fiscal_year_end"] == "2023-09-30")
        assert fy2023["eps"] == 6.16

    def test_excludes_quarterly_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2024-06-29" not in dates


class TestTenQ:
    def test_parse_quarterly(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="quarterly")
        assert any(r["fiscal_year_end"] == "2024-06-29" for r in results)

    def test_excludes_annual_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="quarterly")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2023-09-30" not in dates


class TestTwentyF:
    def test_parse_annual_ifrs(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        assert len(results) >= 1
        fy2022 = next(r for r in results if r["fiscal_year_end"] == "2022-12-31")
        assert fy2022["revenue"] == 2263891200000
        assert fy2022["currency"] == "TWD"

    def test_total_assets_instant(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        fy2022 = next(r for r in results if r["fiscal_year_end"] == "2022-12-31")
        assert fy2022["total_assets"] == 5765188300000

    def test_eps_twd_per_share(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        fy2022 = next(r for r in results if r["fiscal_year_end"] == "2022-12-31")
        assert fy2022["eps"] == 39.2

    def test_excludes_6k_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2023-06-30" not in dates


class TestSixK:
    def test_parse_interim(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="quarterly")
        assert any(r["fiscal_year_end"] == "2023-06-30" for r in results)

    def test_excludes_20f_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="quarterly")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2022-12-31" not in dates


class TestTaxonomyDetection:
    def test_detects_us_gaap(self, parser):
        from stock_analyze_system.ingestion.xbrl.taxonomy import detect_taxonomy
        taxonomy, _, currency = detect_taxonomy(SAMPLE_US_GAAP_FACTS)
        assert taxonomy == "us-gaap"
        assert currency == "USD"

    def test_detects_ifrs(self, parser):
        from stock_analyze_system.ingestion.xbrl.taxonomy import detect_taxonomy
        taxonomy, _, currency = detect_taxonomy(SAMPLE_IFRS_FACTS)
        assert taxonomy == "ifrs-full"
        assert currency == "TWD"

    def test_empty_facts(self, parser):
        results = parser.parse_company_facts({"facts": {}}, period_type="annual")
        assert results == []


class TestFallbackTag:
    def test_fallback_to_second_tag(self, us_gaap_mapping, ifrs_mapping):
        from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser
        from stock_analyze_system.ingestion.xbrl.taxonomy import TAXONOMY_MAPPING_FILES
        mapping = {"revenue": ["us-gaap:NonExistentTag", "us-gaap:Revenues"]}
        custom = us_gaap_mapping.parent / "custom.yaml"
        custom.write_text(yaml.dump(mapping))
        with patch.dict(TAXONOMY_MAPPING_FILES, {
            "us-gaap": str(custom),
            "ifrs-full": str(ifrs_mapping),
        }):
            p = SecXbrlParser()
        results = p.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        assert len(results) >= 1
        assert results[0]["revenue"] is not None

    def test_empty_us_gaap(self, parser):
        results = parser.parse_company_facts(
            {"facts": {"us-gaap": {}}}, period_type="annual",
        )
        assert results == []


class TestDurationFiltering:
    def test_quarterly_rejects_ytd_entry(self, parser):
        facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"start": "2023-01-01", "end": "2023-06-30", "val": 5000,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                    ],
                },
            },
        }
        result = parser.resolve_tag(
            facts, ["Revenues"], "USD", ["10-Q"],
            duration_filter="quarterly",
        )
        assert "2023-06-30" not in result

    def test_quarterly_accepts_standalone_entry(self, parser):
        facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"start": "2023-04-01", "end": "2023-06-30", "val": 2500,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                    ],
                },
            },
        }
        result = parser.resolve_tag(
            facts, ["Revenues"], "USD", ["10-Q"],
            duration_filter="quarterly",
        )
        assert result.get("2023-06-30") == 2500.0

    def test_quarterly_prefers_shortest_duration(self, parser):
        facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"start": "2023-04-01", "end": "2023-06-30", "val": 5000,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                        {"start": "2023-05-17", "end": "2023-06-30", "val": 2000,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                    ],
                },
            },
        }
        result = parser.resolve_tag(
            facts, ["Revenues"], "USD", ["10-Q"],
            duration_filter="quarterly",
        )
        assert result.get("2023-06-30") == 2000.0
