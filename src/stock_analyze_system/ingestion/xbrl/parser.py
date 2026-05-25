# src/stock_analyze_system/ingestion/xbrl/parser.py
"""SEC XBRL Company Facts パーサー"""
from __future__ import annotations

import logging

from stock_analyze_system.config import _resolve_project_path
from stock_analyze_system.models.enums import FilingType, PeriodType
from stock_analyze_system.ingestion.xbrl.taxonomy import (
    TAXONOMY_MAPPING_FILES,
    INSTANT_FIELDS,
    CORE_FIELDS,
    detect_taxonomy,
    pick_unit,
    find_unit_data,
    load_mapping,
)
from stock_analyze_system.ingestion.xbrl.period_filter import (
    DURATION_UNKNOWN,
    days_between,
    duration_ok,
    merge_near_dates,
)

logger = logging.getLogger(__name__)

_FORM_MAP: dict[PeriodType, list[dict[str, str | None]]] = {
    PeriodType.ANNUAL: [
        {"form": FilingType.TEN_K, "fp": "FY"},
        {"form": FilingType.TWENTY_F, "fp": "FY"},
    ],
    PeriodType.QUARTERLY: [
        {"form": FilingType.TEN_Q, "fp": None},
        {"form": FilingType.SIX_K, "fp": None},
        {"form": FilingType.TEN_K, "fp": None},
        {"form": FilingType.TWENTY_F, "fp": None},
    ],
}


class SecXbrlParser:
    """XBRL Company Facts -> 正規化財務レコード"""

    def __init__(self) -> None:
        self._mappings: dict[str, dict[str, list[str]]] = {}
        for taxonomy, rel_path in TAXONOMY_MAPPING_FILES.items():
            path = _resolve_project_path(rel_path)
            if path.exists():
                self._mappings[taxonomy] = load_mapping(path)
            else:
                logger.warning("Mapping file not found: %s", path)

    def parse_company_facts(
        self, facts_json: dict, period_type: str = "annual",
    ) -> list[dict]:
        """Company Facts JSONから財務レコードを抽出"""
        filter_specs = _FORM_MAP.get(period_type)
        if filter_specs is None:
            raise ValueError(f"Unknown period_type '{period_type}'")

        taxonomy, facts_subtree, currency = detect_taxonomy(facts_json)
        mapping = self._mappings.get(taxonomy, {})
        if not mapping:
            return []

        forms = [spec["form"] for spec in filter_specs]
        fp_filter = filter_specs[0]["fp"]

        all_dates: set[str] = set()
        field_data: dict[str, dict[str, float]] = {}

        for field_name, tag_candidates in mapping.items():
            if not tag_candidates:
                field_data[field_name] = {}
                continue
            unit = pick_unit(field_name, currency)
            is_instant = field_name in INSTANT_FIELDS
            duration_filter = period_type if not is_instant else None
            resolved = self.resolve_tag(
                facts_subtree, tag_candidates, unit, forms,
                fp_filter=fp_filter,
                duration_filter=duration_filter,
            )
            field_data[field_name] = resolved
            all_dates.update(resolved.keys())

        canonical_dates = merge_near_dates(all_dates, field_data, mapping)

        records: list[dict] = []
        for dt in sorted(canonical_dates):
            record: dict[str, object] = {"fiscal_year_end": dt, "currency": currency}
            has_core = False
            for field_name in mapping:
                val = field_data[field_name].get(dt)
                record[field_name] = val
                if val is not None and field_name in CORE_FIELDS:
                    has_core = True
            if has_core:
                records.append(record)

        return records

    def resolve_tag(
        self, facts: dict, tag_candidates: list[str], unit: str,
        forms: list[str], fp_filter: str | None = None,
        duration_filter: str | None = None,
    ) -> dict[str, float]:
        """タグ候補を優先順に試行し、日付->値のマップを返す"""
        merged: dict[str, float] = {}
        merged_days: dict[str, int] = {}

        for candidate in tag_candidates:
            tag_name = candidate.split(":")[-1] if ":" in candidate else candidate
            tag_data = facts.get(tag_name)
            if tag_data is None:
                continue

            unit_data = find_unit_data(tag_data, unit)
            if not unit_data:
                continue

            for entry in unit_data:
                entry_form = entry.get("form")
                if entry_form not in forms:
                    continue
                if fp_filter and entry.get("fp") != fp_filter:
                    continue
                if (fp_filter != "FY"
                        and entry_form in (FilingType.TEN_K, FilingType.TWENTY_F)
                        and entry.get("fp") == "FY"):
                    continue

                end_date: str = entry.get("end", "")
                start_date: str = entry.get("start", "")
                days = (days_between(start_date, end_date)
                        if start_date and end_date else DURATION_UNKNOWN)

                if duration_filter and start_date and end_date:
                    if not duration_ok(days, duration_filter):
                        continue

                val = entry.get("val")
                if end_date and val is not None:
                    prev_days = merged_days.get(end_date, DURATION_UNKNOWN)
                    if end_date not in merged or days < prev_days:
                        merged[end_date] = float(val)
                        merged_days[end_date] = days

        return merged
