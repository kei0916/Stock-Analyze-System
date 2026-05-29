"""FilingSectionExtractor 全パターン検証 (B 修正前の前提確認).

ADR-004 移行後、worker `_run_job` から `IndexBuildError` が伝播しないことを
最終確認するため、`FilingSectionExtractor.extract()` が:

  1. DB に登録済みの全実フィリング (10-K / 10-Q / 20-F / 6-K) で正常終了するか
  2. 想定エッジのうち入力欠落 (storage_path 欠落 / raw HTML 欠落) は
     `ExtractionInputMissingError` として分類され、それ以外は unexpected raise
     にならないか

を網羅的に確認する。

実行:
    OPENAI_API_KEY=dummy .venv/bin/python scripts/verify_extractor_all_patterns.py \
        2>&1 | tee /tmp/extractor_verify.log
結果は data/extractor_verification.json に永続化。
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
import traceback
from dataclasses import dataclass
from typing import NamedTuple
from pathlib import Path

sys.path.insert(0, "src")

from stock_analyze_system.services.filing_section_extractor import (
    ExtractionInputMissingError,
    FilingSectionExtractor,
    is_structurally_empty,
)
from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES


_EXPECTED_INPUT_MISSING_LABELS = {
    "edge: storage_path=None",
    "edge: storage_path=''",
    "edge: storage_path nonexistent",
    "edge: storage_path exists, no raw/",
    "edge: raw/ empty",
    "edge: raw/ only PDF",
}

_KNOWN_MISSING_SECTIONS_BY_LABEL = {
    # See docs/extractor-pattern-verification-2026-05-17.md.
    "US_ABCL FY2025 10-K (filing_id=258)": ("risk_factors",),
    "US_TEM FY2025 10-K (filing_id=161)": tuple(ANALYSIS_TYPE_NAMES),
    "US_TEM FY2024 10-K (filing_id=162)": tuple(ANALYSIS_TYPE_NAMES),
}

_EXPECTED_EMPTY_SECTION_LABELS = {
    "edge: raw/ malformed HTML",
    "edge: raw/ empty HTML",
    "edge: unknown filing_type='8-K'",
    "edge: unknown filing_type='S-1'",
    "edge: filing_type=''",
}


@dataclass
class _FakeFiling:
    """FilingSectionExtractor が触る属性だけ持つ最小オブジェクト."""
    id: int
    filing_type: str
    storage_path: str | None


async def _probe(label: str, filing: _FakeFiling) -> dict:
    extractor = FilingSectionExtractor()
    try:
        sections = await extractor.extract(filing)
    except Exception as exc:  # noqa: BLE001
        expected_raise = (
            label in _EXPECTED_INPUT_MISSING_LABELS
            and isinstance(exc, ExtractionInputMissingError)
        )
        return {
            "label": label,
            "filing_type": filing.filing_type,
            "storage_path": filing.storage_path,
            "raised": f"{type(exc).__name__}: {exc}",
            "expected_raise": expected_raise,
            "unexpected_raise": not expected_raise,
            "traceback": traceback.format_exc(limit=3),
            "sections": None,
        }

    sizes = {k: len(sections.get(k, "")) for k in ANALYSIS_TYPE_NAMES}
    populated = {k for k, n in sizes.items() if n > 0}
    structural = {
        k for k in ANALYSIS_TYPE_NAMES
        if is_structurally_empty(filing.filing_type, k)
    }
    return {
        "label": label,
        "filing_type": filing.filing_type,
        "storage_path": filing.storage_path,
        "raised": None,
        "expected_raise": False,
        "unexpected_raise": False,
        "section_sizes": sizes,
        "populated": sorted(populated),
        "structurally_empty": sorted(structural),
        "missing_unexpectedly": sorted(
            (set(ANALYSIS_TYPE_NAMES) - populated) - structural
        ),
    }


def _enumerate_real_filings() -> list[tuple[str, _FakeFiling]]:
    """data/stock_analyze.db から storage_path 付きの 4 種 filing を全件取得."""
    conn = sqlite3.connect("data/stock_analyze.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, company_id, filing_type, fiscal_year, storage_path
          FROM filings
         WHERE storage_path IS NOT NULL
           AND filing_type IN ('10-K','10-Q','20-F','6-K')
         ORDER BY filing_type, company_id, fiscal_year DESC
    """).fetchall()
    return [
        (
            f"{r['company_id']} FY{r['fiscal_year']} {r['filing_type']} "
            f"(filing_id={r['id']})",
            _FakeFiling(
                id=r["id"], filing_type=r["filing_type"],
                storage_path=r["storage_path"],
            ),
        )
        for r in rows
    ]


def _synthetic_edge_cases() -> list[tuple[str, _FakeFiling]]:
    tmp = tempfile.mkdtemp(prefix="extractor_edge_")
    tmp_path = Path(tmp)

    # case: storage_path exists but no raw/ subdir
    empty_dir = tmp_path / "no_raw_subdir"
    empty_dir.mkdir()

    # case: raw/ exists but empty
    empty_raw = tmp_path / "empty_raw"
    (empty_raw / "raw").mkdir(parents=True)

    # case: raw/ has only non-HTML (PDF)
    pdf_only = tmp_path / "pdf_only"
    pdf_only_raw = pdf_only / "raw"
    pdf_only_raw.mkdir(parents=True)
    (pdf_only_raw / "doc.pdf").write_bytes(b"%PDF-1.4\n")

    # case: raw/ has a malformed .htm
    malformed = tmp_path / "malformed"
    malformed_raw = malformed / "raw"
    malformed_raw.mkdir(parents=True)
    (malformed_raw / "bad.htm").write_text(
        "<html><body><p>unterminated",  # missing end tags
        encoding="utf-8",
    )

    # case: raw/ has empty .htm
    empty_htm = tmp_path / "empty_htm"
    empty_htm_raw = empty_htm / "raw"
    empty_htm_raw.mkdir(parents=True)
    (empty_htm_raw / "blank.htm").write_text("", encoding="utf-8")

    cases: list[tuple[str, _FakeFiling]] = [
        (
            "edge: storage_path=None",
            _FakeFiling(id=-1, filing_type="10-K", storage_path=None),
        ),
        (
            "edge: storage_path=''",
            _FakeFiling(id=-2, filing_type="10-K", storage_path=""),
        ),
        (
            "edge: storage_path nonexistent",
            _FakeFiling(id=-3, filing_type="10-K",
                        storage_path="/nonexistent/path/abc"),
        ),
        (
            "edge: storage_path exists, no raw/",
            _FakeFiling(id=-4, filing_type="10-K",
                        storage_path=str(empty_dir)),
        ),
        (
            "edge: raw/ empty",
            _FakeFiling(id=-5, filing_type="10-K",
                        storage_path=str(empty_raw)),
        ),
        (
            "edge: raw/ only PDF",
            _FakeFiling(id=-6, filing_type="10-K",
                        storage_path=str(pdf_only)),
        ),
        (
            "edge: raw/ malformed HTML",
            _FakeFiling(id=-7, filing_type="10-K",
                        storage_path=str(malformed)),
        ),
        (
            "edge: raw/ empty HTML",
            _FakeFiling(id=-8, filing_type="10-K",
                        storage_path=str(empty_htm)),
        ),
        # Use one real 10-K HTML but with an unknown filing_type
        (
            "edge: unknown filing_type='8-K'",
            _FakeFiling(
                id=-9, filing_type="8-K",
                storage_path="data/filings/SEC/US_RXRX/2025/annual/"
                             "10-K/0001601830-26-000039",
            ),
        ),
        (
            "edge: unknown filing_type='S-1'",
            _FakeFiling(
                id=-10, filing_type="S-1",
                storage_path="data/filings/SEC/US_RXRX/2025/annual/"
                             "10-K/0001601830-26-000039",
            ),
        ),
        (
            "edge: filing_type=''",
            _FakeFiling(
                id=-11, filing_type="",
                storage_path="data/filings/SEC/US_RXRX/2025/annual/"
                             "10-K/0001601830-26-000039",
            ),
        ),
    ]
    return cases


class _MissingClassification(NamedTuple):
    known: list[dict]
    expected_empty: list[dict]
    unexpected: list[dict]


def _entry(label: str, missing: list[str]) -> dict:
    return {"label": label, "missing": missing}


def _labels(entries: list[dict]) -> list[str]:
    return [entry["label"] for entry in entries]


def _missing_results(results: list[dict]) -> list[dict]:
    return [
        result for result in results
        if result.get("raised") is None and result.get("missing_unexpectedly")
    ]


def _is_edge_result(result: dict) -> bool:
    return result["label"].startswith("edge:")


def _classify_missing_sections(results: list[dict]) -> _MissingClassification:
    known_missing: list[dict] = []
    expected_empty: list[dict] = []
    unexpected_missing: list[dict] = []
    expected_full_empty = set(ANALYSIS_TYPE_NAMES)

    for result in _missing_results(results):
        label = result["label"]
        missing = list(result["missing_unexpectedly"])

        if label in _EXPECTED_EMPTY_SECTION_LABELS:
            target = (
                expected_empty
                if set(missing) == expected_full_empty
                else unexpected_missing
            )
            target.append(_entry(label, missing))
            continue

        known = set(_KNOWN_MISSING_SECTIONS_BY_LABEL.get(label, ()))
        known_sections = [name for name in missing if name in known]
        unexpected_sections = [name for name in missing if name not in known]
        if known_sections:
            known_missing.append(_entry(label, known_sections))
        if unexpected_sections:
            unexpected_missing.append(_entry(label, unexpected_sections))

    return _MissingClassification(
        known=known_missing,
        expected_empty=expected_empty,
        unexpected=unexpected_missing,
    )


def _result_prefix(result: dict) -> str:
    if result.get("raised"):
        return "EXPECTED-RAISE" if result.get("expected_raise") else "RAISED"

    if not result.get("missing_unexpectedly"):
        return "OK"

    classification = _classify_missing_sections([result])
    if classification.unexpected:
        return "MISSING"
    if classification.expected_empty:
        return "EXPECTED-EMPTY"
    if classification.known:
        return "KNOWN-MISSING"
    return "OK"


def _summarise(results: list[dict]) -> dict:
    raised = [r for r in results if r.get("raised")]
    expected_raises = [r for r in raised if r.get("expected_raise")]
    unexpected_raises = [r for r in raised if r.get("unexpected_raise")]
    classification = _classify_missing_sections(results)
    unexpected_missing_label_set = set(_labels(classification.unexpected))
    real = [r for r in results if not _is_edge_result(r)]
    edge = [r for r in results if _is_edge_result(r)]

    return {
        "total": len(results),
        "raised_count": len(raised),
        "expected_input_missing_count": len(expected_raises),
        "unexpected_raised_count": len(unexpected_raises),
        "known_unexpected_missing_count": len(classification.known),
        "expected_empty_edge_count": len(classification.expected_empty),
        "unexpected_missing_count": len(classification.unexpected),
        "raised_labels": [r["label"] for r in raised],
        "expected_input_missing_labels": [r["label"] for r in expected_raises],
        "unexpected_raised_labels": [r["label"] for r in unexpected_raises],
        "known_unexpected_missing_labels": _labels(classification.known),
        "known_unexpected_missing_entries": classification.known,
        "expected_empty_edge_labels": _labels(classification.expected_empty),
        "expected_empty_edge_entries": classification.expected_empty,
        "unexpected_missing_labels": _labels(classification.unexpected),
        "unexpected_missing_entries": classification.unexpected,
        "real_count": len(real),
        "edge_count": len(edge),
        "real_failures": [
            r["label"] for r in real
            if r.get("unexpected_raise")
            or r["label"] in unexpected_missing_label_set
        ],
        "all_missing_sections": [
            _entry(r["label"], list(r.get("missing_unexpectedly") or []))
            for r in _missing_results(results)
        ],
    }


def _exit_code(summary: dict) -> int:
    if summary["unexpected_raised_count"] or summary["unexpected_missing_count"]:
        return 1
    return 0


async def main() -> int:
    targets: list[tuple[str, _FakeFiling]] = []
    targets.extend(_enumerate_real_filings())
    targets.extend(_synthetic_edge_cases())

    real_count = sum(
        1 for label, _ in targets if not label.startswith("edge:")
    )
    edge_count = sum(
        1 for label, _ in targets if label.startswith("edge:")
    )
    print(
        f"[start] {len(targets)} cases ({real_count} real + {edge_count} edge)"
    )

    results: list[dict] = []
    for label, filing in targets:
        result = await _probe(label, filing)
        results.append(result)
        prefix = _result_prefix(result)
        if result.get("raised"):
            print(f"[{prefix}] {label}: {result['raised']}")
        else:
            sizes = result["section_sizes"]
            short = " ".join(f"{k[:3]}={sizes[k]}" for k in ANALYSIS_TYPE_NAMES)
            missing = result.get("missing_unexpectedly") or []
            tail = f" missing={missing}" if missing else ""
            print(f"[{prefix}] {label}: {short}{tail}")

    summary = _summarise(results)
    out_path = Path("data/extractor_verification.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"summary": summary, "results": results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print()
    print("=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[output] {out_path}")
    return _exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
