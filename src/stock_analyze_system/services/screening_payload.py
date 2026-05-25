"""Screening cache payload normalization."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from numbers import Number
from typing import Any

from sqlalchemy import Date

from stock_analyze_system.models.screening import ScreeningCache


FIELD_ALIASES: dict[str, str] = {
    "per": "trailing_per",
}

EXCLUDED_CACHE_FIELDS = {"company_id", "updated_at"}


def _cache_fields() -> set[str]:
    return {
        col.name
        for col in ScreeningCache.__table__.columns
        if col.name not in EXCLUDED_CACHE_FIELDS
    }


def _date_fields() -> set[str]:
    return {
        col.name
        for col in ScreeningCache.__table__.columns
        if isinstance(col.type, Date)
    }


def _is_non_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, Number):
        return False
    try:
        return not math.isfinite(value)
    except (TypeError, ValueError):
        return False


def _normalize_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00"),
            ).date()
        except ValueError:
            return None
    return None


def normalize_screening_cache_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return a DB-safe ScreeningCache update payload from external data."""
    cache_fields = _cache_fields()
    date_fields = _date_fields()
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        field = FIELD_ALIASES.get(key, key)
        if field not in cache_fields:
            continue
        if field in date_fields:
            normalized[field] = _normalize_date(value)
        elif _is_non_finite_number(value):
            normalized[field] = None
        else:
            normalized[field] = value
    return normalized
