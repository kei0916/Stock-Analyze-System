"""検証レポート生成・保存"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from stock_analyze_system.shared.json_utils import json_dumps_ja

def save_verification_report(
    company_id: str, filing_id: int, tree: dict,
    verification_log: list, node_count: int,
    output_dir: Path = Path("data/logs/verification"),
) -> Path:
    """検証レポートをJSON保存しパスを返す"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report = {
        "company_id": company_id, "filing_id": filing_id,
        "doc_name": tree.get("doc_name", ""), "timestamp": timestamp,
        "node_count": node_count, "phases": [],
    }
    for phase in verification_log:
        phase_data = {
            "mode": phase["mode"], "accuracy": phase["accuracy"],
            "checked_count": phase["checked_count"],
            "correct_count": phase["correct_count"],
            "incorrect_count": phase["incorrect_count"], "items": [],
        }
        for item in phase.get("items", []):
            phase_data["items"].append({
                "title": item.get("title", ""), "page_number": item.get("page_number"),
                "answer": item.get("answer", ""), "thinking": item.get("thinking", ""),
                "page_text_snippet": item.get("page_text_snippet", ""),
            })
        report["phases"].append(phase_data)
    filename = f"{company_id}_{timestamp}.json"
    report_path = output_dir / filename
    report_path.write_text(json_dumps_ja(report, indent=2))
    return report_path
