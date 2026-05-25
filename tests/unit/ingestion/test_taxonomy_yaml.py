"""タクソノミマッピングYAMLのバリデーションテスト"""

import yaml

from stock_analyze_system.config import _resolve_project_path


EXPECTED_FIELDS = {
    "revenue", "operating_income", "net_income", "total_assets", "equity",
    "current_assets", "current_liabilities", "total_debt", "cash", "inventory",
    "cogs", "operating_cf", "capex", "ebitda", "eps", "dps", "tax_expense",
    "income_before_tax", "shares_outstanding", "dividends_paid", "share_repurchases",
}


class TestUsGaapMapping:
    def test_loads_valid_yaml(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_has_all_fields(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field in EXPECTED_FIELDS:
            assert field in data, f"Missing field: {field}"

    def test_values_are_lists(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field, tags in data.items():
            assert isinstance(tags, list), f"{field} should be a list"

    def test_tags_have_namespace_prefix(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field, tags in data.items():
            for tag in tags:
                assert ":" in tag, f"{field} tag '{tag}' missing namespace prefix"


class TestIfrsMapping:
    def test_loads_valid_yaml(self):
        path = _resolve_project_path("config/ifrs_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_has_all_fields(self):
        path = _resolve_project_path("config/ifrs_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field in EXPECTED_FIELDS:
            assert field in data, f"Missing field: {field}"


class TestEdinetMapping:
    def test_loads_valid_yaml(self):
        path = _resolve_project_path("config/edinet_taxonomy_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_has_jp_gaap_and_ifrs_keys(self):
        path = _resolve_project_path("config/edinet_taxonomy_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field, standards in data.items():
            if isinstance(standards, dict) and len(standards) > 0:
                assert "jp_gaap" in standards or "ifrs" in standards, \
                    f"{field} must have jp_gaap or ifrs key"
