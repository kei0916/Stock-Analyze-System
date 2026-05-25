"""共有財務ユーティリティ（ingestion, services 共通）"""
from __future__ import annotations


def derive_fcf(record: dict) -> None:
    """FCF を operating_cf - abs(capex) で安全に導出する

    record に fcf が既に存在する場合は上書きしない。
    operating_cf または capex が None の場合は何もしない。
    """
    if record.get("fcf") is not None:
        return
    op_cf = record.get("operating_cf")
    capex = record.get("capex")
    if op_cf is not None and capex is not None:
        record["fcf"] = op_cf - abs(capex)
