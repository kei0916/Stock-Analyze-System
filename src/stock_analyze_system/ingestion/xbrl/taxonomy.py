# src/stock_analyze_system/ingestion/xbrl/taxonomy.py
"""XBRL タクソノミ検出・マッピングロード"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

TAXONOMY_MAPPING_FILES: dict[str, str] = {
    "us-gaap": "config/us_gaap_mapping.yaml",
    "ifrs-full": "config/ifrs_mapping.yaml",
}

SHARE_FIELDS: set[str] = {"shares_outstanding", "eps", "dps"}

INSTANT_FIELDS: set[str] = {
    "total_assets", "equity", "current_assets", "current_liabilities",
    "total_debt", "cash", "inventory", "shares_outstanding",
}

CORE_FIELDS: set[str] = {
    "revenue", "operating_income", "net_income", "total_assets",
    "equity", "ebitda", "operating_cf", "eps",
}


def detect_taxonomy(facts_json: dict) -> tuple[str, dict, str]:
    """タクソノミと通貨を自動検出"""
    all_facts = facts_json.get("facts", {})
    us_gaap = all_facts.get("us-gaap", {})
    ifrs = all_facts.get("ifrs-full", {})

    if len(ifrs) > len(us_gaap):
        return "ifrs-full", ifrs, detect_currency(ifrs)
    elif us_gaap:
        return "us-gaap", us_gaap, "USD"
    elif ifrs:
        return "ifrs-full", ifrs, detect_currency(ifrs)
    return "us-gaap", {}, "USD"


def detect_currency(facts: dict) -> str:
    for probe_tag in ("Revenue", "Assets", "ProfitLoss"):
        tag_data = facts.get(probe_tag)
        if not tag_data:
            continue
        units = tag_data.get("units", {})
        for unit_key in units:
            if "/" in unit_key or unit_key in ("pure", "shares"):
                continue
            if unit_key != "USD":
                return unit_key
        if "USD" in units:
            return "USD"
    return "USD"


def pick_unit(field_name: str, currency: str) -> str:
    if field_name in SHARE_FIELDS:
        return f"{currency}/shares"
    return currency


def find_unit_data(tag_data: dict, unit: str) -> list[dict] | None:
    units = tag_data.get("units", {})
    if unit in units:
        return units[unit]
    if unit.endswith("/shares"):
        if "USD/shares" in units:
            return units["USD/shares"]
        for key in units:
            if key.endswith("/shares"):
                return units[key]
        if "shares" in units:
            return units["shares"]
    if unit != "USD" and "USD" in units:
        return units["USD"]
    if "USD/shares" in units:
        return units["USD/shares"]
    return None


def load_mapping(path: Path) -> dict[str, list[str]]:
    with open(path) as fh:
        raw: dict = yaml.safe_load(fh) or {}
    mapping: dict[str, list[str]] = {}
    for field, tags in raw.items():
        if isinstance(tags, list):
            mapping[field] = tags
    return mapping
