# src/stock_analyze_system/ingestion/xbrl/period_filter.py
"""XBRL 期間フィルタリング・日付マージ ユーティリティ"""
from __future__ import annotations

import logging
from datetime import date as date_type

from stock_analyze_system.models.enums import PeriodType

logger = logging.getLogger(__name__)

ANNUAL_MIN_DAYS = 300
QUARTERLY_MAX_DAYS = 120
DURATION_UNKNOWN = 99999


def days_between(start_date: str, end_date: str) -> int:
    try:
        return (date_type.fromisoformat(end_date)
                - date_type.fromisoformat(start_date)).days
    except ValueError:
        return DURATION_UNKNOWN


def duration_ok(days: int, mode: str) -> bool:
    if mode == PeriodType.ANNUAL:
        return days >= ANNUAL_MIN_DAYS
    if mode == PeriodType.QUARTERLY:
        return days <= QUARTERLY_MAX_DAYS
    return True


def merge_near_dates(
    all_dates: set[str],
    field_data: dict[str, dict[str, float]],
    mapping: dict[str, list[str]],
) -> set[str]:
    """+-3日以内の日付をマージ（値破棄時にログ出力）"""
    sorted_dates = sorted(all_dates)
    if len(sorted_dates) < 2:
        return all_dates

    clusters: list[list[str]] = [[sorted_dates[0]]]
    for d in sorted_dates[1:]:
        prev = clusters[-1][-1]
        if days_between(prev, d) <= 3:
            clusters[-1].append(d)
        else:
            clusters.append([d])

    canonical: set[str] = set()
    for cluster in clusters:
        if len(cluster) == 1:
            canonical.add(cluster[0])
            continue

        best_date = cluster[0]
        best_count = 0
        for d in cluster:
            count = sum(
                1 for fn in mapping if field_data.get(fn, {}).get(d) is not None
            )
            if count > best_count:
                best_count = count
                best_date = d

        canonical.add(best_date)
        for other in cluster:
            if other == best_date:
                continue
            for fn in mapping:
                fd = field_data.get(fn, {})
                if other in fd:
                    if fd.get(best_date) is None:
                        fd[best_date] = fd[other]
                    else:
                        logger.debug(
                            "Discarding value for %s at %s (keeping %s value)",
                            fn, other, best_date,
                        )
                    del fd[other]

    return canonical
