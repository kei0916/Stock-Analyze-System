# Maintainability Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve codebase maintainability through bottom-up refactoring: enums, layer fixes, file splits, dedup, and config cleanup.

**Architecture:** Bottom-up approach (models → services → CLI). Each task produces a green test suite before committing. Backward-compatible re-exports maintain existing import paths during transitions.

**Tech Stack:** Python 3.10+, SQLAlchemy 2.0, pytest, argparse

**Spec:** `docs/superpowers/specs/2026-03-29-maintainability-refactoring-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `src/stock_analyze_system/models/enums.py` | FilingType, PeriodType, AccountingStandard enums |
| `src/stock_analyze_system/services/verification_report.py` | 検証レポート生成・保存 |
| `src/stock_analyze_system/cli/container.py` | ServiceContainer + setup_services() |
| `src/stock_analyze_system/ingestion/xbrl/__init__.py` | Re-export SecXbrlParser (互換維持) |
| `src/stock_analyze_system/ingestion/xbrl/parser.py` | XBRL parse orchestration |
| `src/stock_analyze_system/ingestion/xbrl/taxonomy.py` | タクソノミマッピング解決 |
| `src/stock_analyze_system/ingestion/xbrl/period_filter.py` | 期間フィルタリング + 日付マージ |

### Modified Files
| File | Change |
|------|--------|
| `src/stock_analyze_system/models/__init__.py` | Add enums import |
| `src/stock_analyze_system/ingestion/sec_edgar.py` | Use FilingType enum |
| `src/stock_analyze_system/services/filing_sync.py` | Use FilingType enum |
| `src/stock_analyze_system/services/financial_sync.py` | Use enums, rename constant |
| `src/stock_analyze_system/services/job.py` | Extract compute_valuation, use enums |
| `src/stock_analyze_system/services/valuation.py` | Absorb compute_valuation_from_financials |
| `src/stock_analyze_system/services/pageindex_service.py` | Add public count_nodes() |
| `src/stock_analyze_system/cli/helpers.py` | Slim down to validators + new helpers |
| `src/stock_analyze_system/cli/rag.py` | Use enums, shared helpers, remove report logic |
| `src/stock_analyze_system/cli/financial.py` | Use PeriodType enum |
| `tests/unit/cli/conftest.py` | Update import path |
| `tests/unit/cli/test_helpers.py` | Update import path |
| `tests/unit/cli/test_rag_cli.py` | Update for filing_type enum |
| `tests/unit/services/test_job_service.py` | Update import path for compute_valuation |

### Deleted Files
| File | Reason |
|------|--------|
| `src/stock_analyze_system/ingestion/sec_xbrl_parser.py` | Replaced by `ingestion/xbrl/` package |

---

## Task 1: Create FilingType, PeriodType, AccountingStandard enums

**Files:**
- Create: `src/stock_analyze_system/models/enums.py`
- Test: `tests/unit/test_enums.py`

- [ ] **Step 1: Write test for enums**

```python
# tests/unit/test_enums.py
"""Enum定義のテスト"""
from stock_analyze_system.models.enums import (
    FilingType, PeriodType, AccountingStandard,
)


class TestFilingType:
    def test_values(self):
        assert FilingType.TEN_K == "10-K"
        assert FilingType.TEN_Q == "10-Q"
        assert FilingType.TWENTY_F == "20-F"
        assert FilingType.SIX_K == "6-K"

    def test_str_comparison(self):
        assert FilingType.TEN_K == "10-K"
        assert "10-K" == FilingType.TEN_K

    def test_list_for_choices(self):
        choices = list(FilingType)
        assert len(choices) == 4


class TestPeriodType:
    def test_values(self):
        assert PeriodType.ANNUAL == "annual"
        assert PeriodType.QUARTERLY == "quarterly"


class TestAccountingStandard:
    def test_values(self):
        assert AccountingStandard.US_GAAP == "US-GAAP"
        assert AccountingStandard.IFRS == "IFRS"
        assert AccountingStandard.JP_GAAP == "JP-GAAP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_enums.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_analyze_system.models.enums'`

- [ ] **Step 3: Implement enums**

```python
# src/stock_analyze_system/models/enums.py
"""共通Enum定義"""
from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:  # Python 3.10
    from enum import Enum
    class StrEnum(str, Enum):
        pass


class FilingType(StrEnum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    TWENTY_F = "20-F"
    SIX_K = "6-K"


class PeriodType(StrEnum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"


class AccountingStandard(StrEnum):
    """Companyモデルに格納される会計基準値。

    XBRLタクソノミキー("us-gaap", "ifrs-full")とは異なる。
    タクソノミキーは ingestion/xbrl/taxonomy.py でローカル定数として管理。
    """
    US_GAAP = "US-GAAP"
    IFRS = "IFRS"
    JP_GAAP = "JP-GAAP"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_enums.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/models/enums.py tests/unit/test_enums.py
git commit -m "feat: add FilingType, PeriodType, AccountingStandard enums"
```

---

## Task 2: Replace magic strings with enums across source files

**Note:** `sec_xbrl_parser.py` の enum 置換は Task 7 (ファイル分割) で行う。ここでは分割対象外のファイルのみ変更する。

**Files:**
- Modify: `src/stock_analyze_system/ingestion/sec_edgar.py` (filing type list)
- Modify: `src/stock_analyze_system/services/filing_sync.py:53` (filing type comparison)
- Modify: `src/stock_analyze_system/services/financial_sync.py:45` (period type default)
- Modify: `src/stock_analyze_system/services/financial.py:46,50,82` (period type strings)
- Modify: `src/stock_analyze_system/services/job.py:142,174` (period type strings)
- Modify: `src/stock_analyze_system/cli/rag.py:41` (filing type default)
- Modify: `src/stock_analyze_system/cli/financial.py` (period type choices)
- Modify: `src/stock_analyze_system/models/__init__.py` (add enums re-export)

**注意: `filing_sync.py:107-108` の EDINET 固有文字列 (`"annual_report"`, `"quarterly_report"`) は FilingType enum の対象外。これらは EDINET API 固有の値であり `PeriodType` とは異なる。`period_type` の `"annual"` / `"quarterly"` (line 53, 107) のみ enum 化する。**

**注意: `ingestion/fmp.py:63` の `"annual"` は外部 API パラメータのため enum 化しない（API が文字列を期待）。**

- [ ] **Step 1: Add enums re-export to `models/__init__.py`**

Add to `src/stock_analyze_system/models/__init__.py`:
```python
from stock_analyze_system.models.enums import FilingType, PeriodType, AccountingStandard
```

- [ ] **Step 2: Replace in `sec_edgar.py` — form type list**

Find the filing type list (around line 67) and replace string literals with `FilingType` members.

- [ ] **Step 3: Replace in `filing_sync.py` — filing type comparisons**

Line 53: replace `form in ("10-K", "20-F")` with `form in (FilingType.TEN_K, FilingType.TWENTY_F)`.
Line 107: replace `period_type = "annual"` with `period_type = PeriodType.ANNUAL` and `"quarterly"` with `PeriodType.QUARTERLY`.

- [ ] **Step 4: Replace in `financial_sync.py` — period type defaults**

Line 45: replace `("annual",)` with `(PeriodType.ANNUAL,)`.

- [ ] **Step 5: Replace in `services/financial.py` — period type strings**

Lines 46, 50, 82: replace `"annual"`, `"quarterly"` with `PeriodType.ANNUAL`, `PeriodType.QUARTERLY`.

- [ ] **Step 6: Replace in `job.py` — period type references**

Line 142: replace `("annual", "quarterly")` with `(PeriodType.ANNUAL, PeriodType.QUARTERLY)`.
Line 174: replace `"annual"` with `PeriodType.ANNUAL`.

- [ ] **Step 7: Replace in `cli/rag.py:41` — filing-type argument default**

Change `default="10-K"` to `default=FilingType.TEN_K`.

- [ ] **Step 8: Replace in `cli/financial.py` — period choices**

Change `choices=["annual", "quarterly"]` to `choices=list(PeriodType)`.

- [ ] **Step 9: Run full test suite**

Run: `pytest tests/ -v`
Expected: All existing tests PASS (StrEnum values compare equal to plain strings)

- [ ] **Step 10: Commit**

```bash
git add -u
git commit -m "refactor: replace magic strings with FilingType/PeriodType enums"
```

---

## Task 3: Add public `count_nodes()` to PageIndexService

**Files:**
- Modify: `src/stock_analyze_system/services/pageindex_service.py:72`
- Test: `tests/unit/services/test_pageindex_service.py`

- [ ] **Step 1: Write test for count_nodes public API**

```python
# tests/unit/services/test_pageindex_service.py
"""PageIndexService のテスト"""
from stock_analyze_system.services.pageindex_service import PageIndexService


class TestCountNodes:
    def test_flat_tree(self):
        tree = {"title": "root", "children": [
            {"title": "ch1", "children": []},
            {"title": "ch2", "children": []},
        ]}
        assert PageIndexService.count_nodes(tree) == 3

    def test_nested_tree(self):
        tree = {"title": "root", "children": [
            {"title": "ch1", "children": [
                {"title": "ch1a", "children": []},
            ]},
        ]}
        assert PageIndexService.count_nodes(tree) == 3

    def test_single_node(self):
        tree = {"title": "root", "children": []}
        assert PageIndexService.count_nodes(tree) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_pageindex_service.py -v`
Expected: FAIL — `AttributeError: type object 'PageIndexService' has no attribute 'count_nodes'`

- [ ] **Step 3: Add count_nodes to PageIndexService**

In `pageindex_service.py`, add after line ~70 (inside the class):
```python
    @staticmethod
    def count_nodes(tree: dict) -> int:
        """ツリーのノード数を返す"""
        return _count_nodes(tree)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_pageindex_service.py -v`
Expected: PASS

- [ ] **Step 5: Update `cli/rag.py` to use public API**

Replace ALL occurrences (2箇所: --all ループ内 and 単一企業パス):
```python
# Before (function top)
from stock_analyze_system.services.pageindex_service import _count_nodes

# After
from stock_analyze_system.services.pageindex_service import PageIndexService
```

Both `_count_nodes(tree)` calls → `PageIndexService.count_nodes(tree)`.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/services/pageindex_service.py \
        src/stock_analyze_system/cli/rag.py \
        tests/unit/services/test_pageindex_service.py
git commit -m "refactor: expose PageIndexService.count_nodes(), remove private import from CLI"
```

---

## Task 4: Move verification report to service layer

**Files:**
- Create: `src/stock_analyze_system/services/verification_report.py`
- Modify: `src/stock_analyze_system/cli/rag.py:132-173` (remove _save_verification_report)
- Test: `tests/unit/services/test_verification_report.py`

- [ ] **Step 1: Write test for verification report service**

```python
# tests/unit/services/test_verification_report.py
"""検証レポートサービスのテスト"""
import json
from pathlib import Path

from stock_analyze_system.services.verification_report import save_verification_report


class TestSaveVerificationReport:
    def test_creates_report_file(self, tmp_path):
        tree = {"doc_name": "10-K_2024"}
        verification_log = [{
            "mode": "sampling",
            "accuracy": 0.95,
            "checked_count": 20,
            "correct_count": 19,
            "incorrect_count": 1,
            "items": [{
                "title": "Revenue",
                "page_number": 42,
                "answer": "correct",
                "thinking": "matched",
                "page_text_snippet": "Revenue was...",
            }],
        }]
        result_path = save_verification_report(
            company_id="US_AAPL", filing_id=1,
            tree=tree, verification_log=verification_log,
            node_count=10, output_dir=tmp_path,
        )
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert data["company_id"] == "US_AAPL"
        assert data["node_count"] == 10
        assert len(data["phases"]) == 1
        assert data["phases"][0]["accuracy"] == 0.95

    def test_report_filename_format(self, tmp_path):
        tree = {"doc_name": "10-K"}
        result_path = save_verification_report(
            company_id="US_AAPL", filing_id=1,
            tree=tree, verification_log=[{
                "mode": "test", "accuracy": 1.0,
                "checked_count": 1, "correct_count": 1, "incorrect_count": 0,
                "items": [],
            }],
            node_count=5, output_dir=tmp_path,
        )
        assert result_path.name.startswith("US_AAPL_")
        assert result_path.suffix == ".json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_verification_report.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement verification report service**

Extract `_save_verification_report` from `cli/rag.py:134-181` into:

```python
# src/stock_analyze_system/services/verification_report.py
"""検証レポート生成・保存"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def save_verification_report(
    company_id: str,
    filing_id: int,
    tree: dict,
    verification_log: list,
    node_count: int,
    output_dir: Path = Path("data/logs/verification"),
) -> Path:
    """検証レポートをJSON保存しパスを返す"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = {
        "company_id": company_id,
        "filing_id": filing_id,
        "doc_name": tree.get("doc_name", ""),
        "timestamp": timestamp,
        "node_count": node_count,
        "phases": [],
    }

    for phase in verification_log:
        phase_data = {
            "mode": phase["mode"],
            "accuracy": phase["accuracy"],
            "checked_count": phase["checked_count"],
            "correct_count": phase["correct_count"],
            "incorrect_count": phase["incorrect_count"],
            "items": [],
        }
        for item in phase.get("items", []):
            phase_data["items"].append({
                "title": item.get("title", ""),
                "page_number": item.get("page_number"),
                "answer": item.get("answer", ""),
                "thinking": item.get("thinking", ""),
                "page_text_snippet": item.get("page_text_snippet", ""),
            })
        report["phases"].append(phase_data)

    filename = f"{company_id}_{timestamp}.json"
    report_path = output_dir / filename
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_verification_report.py -v`
Expected: PASS

- [ ] **Step 5: Update `cli/rag.py` to use service function**

Remove `_save_verification_report` definition (lines 134-181). Replace call site:
```python
from stock_analyze_system.services.verification_report import save_verification_report

# In _handle_index, replace:
#   _save_verification_report(company.id, filing.id, tree, verification_log, node_count)
# With:
    report_path = save_verification_report(
        company.id, filing.id, tree, verification_log, node_count,
    )
    print(f"Verification report saved: {report_path}")
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/services/verification_report.py \
        src/stock_analyze_system/cli/rag.py \
        tests/unit/services/test_verification_report.py
git commit -m "refactor: move verification report generation to service layer"
```

---

## Task 5: Split `cli/helpers.py` into container.py + helpers.py

**Files:**
- Create: `src/stock_analyze_system/cli/container.py`
- Modify: `src/stock_analyze_system/cli/helpers.py`
- Modify: `tests/unit/cli/conftest.py:4`
- Modify: `tests/unit/cli/test_helpers.py:7-12`

- [ ] **Step 1: Create `cli/container.py` with ServiceContainer + setup_services**

Move `ServiceContainer` dataclass (lines 13-25) and `setup_services()` (lines 28-112) from `helpers.py` to `container.py`. Keep the same imports.

```python
# src/stock_analyze_system/cli/container.py
"""DIコンテナ: サービス組み立て"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.config import AppConfig


@dataclass
class ServiceContainer:
    company_service: Any
    financial_service: Any
    valuation_service: Any
    filing_service: Any
    watchlist_service: Any
    target_service: Any
    job_service: Any
    financial_sync: Any
    filing_sync: Any
    screening_service: Any = None
    rag_service: Any = None


async def setup_services(session: AsyncSession, config: AppConfig) -> ServiceContainer:
    # ... (exact content from helpers.py lines 29-112)
```

- [ ] **Step 2: Update `cli/helpers.py` — keep only validators, re-export for compatibility**

```python
# src/stock_analyze_system/cli/helpers.py
"""CLI共通ヘルパー: リソース検証"""
from __future__ import annotations

import sys
from typing import Any

# Re-export for backward compatibility
from stock_analyze_system.cli.container import ServiceContainer, setup_services  # noqa: F401


async def require_company(company_service: Any, company_id: str) -> Any:
    company = await company_service.get_company(company_id)
    if company is None:
        print(f"Company '{company_id}' not found.", file=sys.stderr)
        sys.exit(1)
    return company


async def require_latest_filing(filing_service: Any, company_id: str, filing_type: str) -> Any:
    filing = await filing_service.get_latest_filing(company_id, filing_type)
    if filing is None:
        print(f"No '{filing_type}' filings found for '{company_id}'.", file=sys.stderr)
        sys.exit(1)
    return filing
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS (re-exports maintain compatibility, no test changes needed yet)

- [ ] **Step 4: Update test imports to use new canonical paths**

In `tests/unit/cli/conftest.py:4`:
```python
from stock_analyze_system.cli.container import ServiceContainer
```

In `tests/unit/cli/test_helpers.py:7-12`:
```python
from stock_analyze_system.cli.container import ServiceContainer, setup_services
from stock_analyze_system.cli.helpers import require_company, require_latest_filing
```

- [ ] **Step 5: Run full test suite again**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/cli/container.py \
        src/stock_analyze_system/cli/helpers.py \
        tests/unit/cli/conftest.py \
        tests/unit/cli/test_helpers.py
git commit -m "refactor: split cli/helpers.py into container.py (DI) + helpers.py (validators)"
```

---

## Task 6: Move `compute_valuation_from_financials` to ValuationService

**Files:**
- Modify: `src/stock_analyze_system/services/valuation.py` (absorb function)
- Modify: `src/stock_analyze_system/services/job.py` (remove function, import from valuation)
- Modify: `tests/unit/services/test_job_service.py:8-11` (update import)

- [ ] **Step 1: Move function to `services/valuation.py`**

Add `compute_valuation_from_financials()` (currently `job.py:36-102`) to bottom of `valuation.py`, along with the `from stock_analyze_system.services import metrics` import.

- [ ] **Step 2: Update `job.py` to import from valuation**

Replace:
```python
# Remove the function definition (lines 36-102) and add import:
from stock_analyze_system.services.valuation import compute_valuation_from_financials
```

Also move `SyncResult` and `DailyUpdateResult` to stay in `job.py` (they are orchestration concepts).

- [ ] **Step 3: Update test import**

In `tests/unit/services/test_job_service.py:8-11`:
```python
from stock_analyze_system.services.job import JobService, SyncResult
from stock_analyze_system.services.valuation import compute_valuation_from_financials
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/valuation.py \
        src/stock_analyze_system/services/job.py \
        tests/unit/services/test_job_service.py
git commit -m "refactor: move compute_valuation_from_financials to ValuationService module"
```

---

## Task 7: Split `sec_xbrl_parser.py` into `ingestion/xbrl/` package

**Note:** Task 2 で `sec_xbrl_parser.py` の enum 置換をスキップしたので、分割時に enum を適用する。`_FORM_MAP` のキーを `PeriodType`、値を `FilingType` に、`resolve_tag()` 内の `entry_form in ("10-K", "20-F")` (line 135) も `FilingType` に置換する。`_duration_ok` 内の `"annual"` / `"quarterly"` 比較は `PeriodType` と StrEnum の文字列互換性で動作する。

**Files:**
- Create: `src/stock_analyze_system/ingestion/xbrl/__init__.py`
- Create: `src/stock_analyze_system/ingestion/xbrl/parser.py`
- Create: `src/stock_analyze_system/ingestion/xbrl/taxonomy.py`
- Create: `src/stock_analyze_system/ingestion/xbrl/period_filter.py`
- Delete: `src/stock_analyze_system/ingestion/sec_xbrl_parser.py`

- [ ] **Step 1: Create `ingestion/xbrl/period_filter.py`**

Extract from `sec_xbrl_parser.py`:
- Constants: `_ANNUAL_MIN_DAYS` → `ANNUAL_MIN_DAYS`, `_QUARTERLY_MAX_DAYS` → `QUARTERLY_MAX_DAYS`, `_DURATION_UNKNOWN` → `DURATION_UNKNOWN` (lines 24-26)
- Methods: `_days_between()` (lines 213-218), `_duration_ok()` (lines 221-226)
- Method: `_merge_near_dates()` (lines 160-210)

```python
# src/stock_analyze_system/ingestion/xbrl/period_filter.py
"""期間フィルタリング・日付マージ"""
from __future__ import annotations

from datetime import date as date_type
from typing import Final

ANNUAL_MIN_DAYS: Final[int] = 300
"""年次レポートの最小期間日数"""

QUARTERLY_MAX_DAYS: Final[int] = 120
"""四半期レポートの最大期間日数"""

DURATION_UNKNOWN: Final[int] = 99999


def days_between(start: str, end: str) -> int:
    # ... exact logic from sec_xbrl_parser.py lines 213-218


def duration_ok(days: int, period_type: str) -> bool:
    # ... exact logic from lines 221-226, using ANNUAL_MIN_DAYS/QUARTERLY_MAX_DAYS


def merge_near_dates(records: list[dict], ...) -> list[dict]:
    # ... exact logic from lines 160-210
```

- [ ] **Step 2: Create `ingestion/xbrl/taxonomy.py`**

Extract from `sec_xbrl_parser.py`:
- Constants: `_TAXONOMY_MAPPING_FILES` (lines 41-44), `_SHARE_FIELDS`, `_INSTANT_FIELDS`, `_CORE_FIELDS` (lines 15-23)
- Methods: `_detect_taxonomy()` (lines 228-240), `_load_mapping()` (lines 281-288)

```python
# src/stock_analyze_system/ingestion/xbrl/taxonomy.py
"""タクソノミマッピング解決"""
from __future__ import annotations

# XBRLタクソノミキー（AccountingStandard enumの値とは異なる）
TAXONOMY_MAPPING_FILES: dict[str, str] = {
    "us-gaap": "config/us_gaap_mapping.yaml",
    "ifrs-full": "config/ifrs_mapping.yaml",
}
# ... field sets, detect/load functions
```

- [ ] **Step 3: Create `ingestion/xbrl/parser.py`**

Move `SecXbrlParser` class, importing from `period_filter` and `taxonomy`:

```python
# src/stock_analyze_system/ingestion/xbrl/parser.py
"""SEC XBRL Company Facts パーサー"""
from __future__ import annotations

from stock_analyze_system.ingestion.xbrl.taxonomy import (
    SHARE_FIELDS, INSTANT_FIELDS, CORE_FIELDS,
    TAXONOMY_MAPPING_FILES, detect_taxonomy, load_mapping,
)
from stock_analyze_system.ingestion.xbrl.period_filter import (
    DURATION_UNKNOWN, days_between, duration_ok, merge_near_dates,
)
from stock_analyze_system.models.enums import FilingType, PeriodType

# ... _FORM_MAP using enums ...
# ... SecXbrlParser class calling imported helpers ...
```

- [ ] **Step 4: Create `ingestion/xbrl/__init__.py` for backward compatibility**

```python
# src/stock_analyze_system/ingestion/xbrl/__init__.py
"""XBRL parsing package — re-exports for backward compatibility."""
from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser

__all__ = ["SecXbrlParser"]
```

- [ ] **Step 5: Delete `ingestion/sec_xbrl_parser.py`**

```bash
git rm src/stock_analyze_system/ingestion/sec_xbrl_parser.py
```

- [ ] **Step 6: Update `financial_sync.py` import**

Change:
```python
# Before
from stock_analyze_system.ingestion.sec_xbrl_parser import SecXbrlParser
# After
from stock_analyze_system.ingestion.xbrl import SecXbrlParser
```

- [ ] **Step 7: Update test imports (必須)**

`tests/unit/ingestion/test_sec_xbrl_parser.py` は旧パス `stock_analyze_system.ingestion.sec_xbrl_parser` からimportしている。ファイル削除後はこのパスは存在しない。テストのimportを更新:

```python
# Before
from stock_analyze_system.ingestion.sec_xbrl_parser import SecXbrlParser
# After
from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser
```

- [ ] **Step 8: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/stock_analyze_system/ingestion/xbrl/ \
        src/stock_analyze_system/services/financial_sync.py \
        tests/unit/ingestion/test_sec_xbrl_parser.py
git rm src/stock_analyze_system/ingestion/sec_xbrl_parser.py
git commit -m "refactor: split sec_xbrl_parser.py into ingestion/xbrl/ package"
```

---

## Task 8: Add shared CLI helpers (add_filing_type_argument, require_company_and_filing)

**Files:**
- Modify: `src/stock_analyze_system/cli/helpers.py`
- Test: `tests/unit/cli/test_helpers.py`

- [ ] **Step 1: Write tests for new helpers**

Add to `tests/unit/cli/test_helpers.py`:

```python
import argparse
from stock_analyze_system.cli.helpers import add_filing_type_argument, require_company_and_filing
from stock_analyze_system.models.enums import FilingType


class TestAddFilingTypeArgument:
    def test_adds_argument_with_default(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        args = parser.parse_args([])
        assert args.filing_type == FilingType.TEN_K

    def test_accepts_valid_type(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        args = parser.parse_args(["--filing-type", "20-F"])
        assert args.filing_type == FilingType.TWENTY_F

    def test_rejects_invalid_type(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--filing-type", "INVALID"])


class TestRequireCompanyAndFiling:
    async def test_returns_both(self):
        company = MagicMock(id="US_AAPL")
        filing = MagicMock(id=1)
        services = make_services()
        services.company_service.get_company.return_value = company
        services.filing_service.get_latest_filing.return_value = filing

        c, f = await require_company_and_filing(services, "US_AAPL", FilingType.TEN_K)
        assert c.id == "US_AAPL"
        assert f.id == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/cli/test_helpers.py::TestAddFilingTypeArgument -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement helpers**

Add to `src/stock_analyze_system/cli/helpers.py`:

```python
import argparse
from stock_analyze_system.models.enums import FilingType


def add_filing_type_argument(parser: argparse.ArgumentParser) -> None:
    """--filing-type 引数を追加する"""
    parser.add_argument(
        "--filing-type", default=FilingType.TEN_K,
        type=FilingType, choices=list(FilingType),
        help="ファイリングタイプ (デフォルト: 10-K)",
    )


async def require_company_and_filing(
    services, company_id: str, filing_type
):
    """企業とファイリングを取得。見つからなければ sys.exit(1)"""
    company = await require_company(services.company_service, company_id)
    filing = await require_latest_filing(services.filing_service, company.id, filing_type)
    return company, filing
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/cli/test_helpers.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/cli/helpers.py tests/unit/cli/test_helpers.py
git commit -m "feat: add shared add_filing_type_argument and require_company_and_filing helpers"
```

---

## Task 9: Consolidate deferred imports in `cli/rag.py`

**Files:**
- Modify: `src/stock_analyze_system/cli/rag.py`

- [ ] **Step 1: Move all deferred imports to handler function tops**

Each handler (`_handle_index`, `_handle_analyze`, `_handle_ask`, `_handle_show`) has scattered deferred imports. Consolidate each handler's imports to a single block at the function top.

Example for `_handle_analyze`:
```python
async def _handle_analyze(rag, services, args) -> None:
    from stock_analyze_system.cli.helpers import require_company_and_filing
    # ... all imports here, then logic below
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/stock_analyze_system/cli/rag.py
git commit -m "refactor: consolidate deferred imports in rag.py handlers"
```

---

## Task 10: Wire shared helpers into `cli/rag.py` (deduplicate)

**Files:**
- Modify: `src/stock_analyze_system/cli/rag.py`

- [ ] **Step 1: Update `register_parser` — use `add_filing_type_argument` on 4 subparsers**

```python
from stock_analyze_system.cli.helpers import add_filing_type_argument

# In register_parser(), replace p_index's --filing-type line with:
add_filing_type_argument(p_index)

# Add to p_analyze, p_ask, p_show:
add_filing_type_argument(p_analyze)
add_filing_type_argument(p_ask)
add_filing_type_argument(p_show)
```

- [ ] **Step 2: Update handlers to use `require_company_and_filing`**

In `_handle_analyze`, `_handle_ask`, `_handle_show`: replace the 2-line company+filing pattern:
```python
from stock_analyze_system.cli.helpers import require_company_and_filing

# Before (in each handler):
company = await require_company(services.company_service, args.company_id)
filing = await require_latest_filing(services.filing_service, company.id, "10-K")

# After:
company, filing = await require_company_and_filing(services, args.company_id, args.filing_type)
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/cli/rag.py
git commit -m "refactor: deduplicate rag.py handlers using shared helpers"
```

---

## Task 11: Rename magic number constants and add PageIndex enabled check

**Files:**
- Modify: `src/stock_analyze_system/ingestion/xbrl/period_filter.py` (already done in Task 7)
- Modify: `src/stock_analyze_system/services/financial_sync.py:20`
- Modify: `src/stock_analyze_system/cli/container.py`

- [ ] **Step 1: Rename `_DATE_MATCH_TOLERANCE` in `financial_sync.py`**

```python
# Before (line 20):
_DATE_MATCH_TOLERANCE = 15

# After:
from typing import Final
DATE_MATCH_TOLERANCE_DAYS: Final[int] = 15
"""期末日マッチングの許容誤差（日数）"""
```

Update all references within `financial_sync.py` from `_DATE_MATCH_TOLERANCE` to `DATE_MATCH_TOLERANCE_DAYS`.

- [ ] **Step 2: Add PageIndex enabled check in `container.py`**

In `setup_services()`, wrap RAG service creation:
```python
    # RAG services
    rag_service = None
    if config.pageindex.enabled:
        doc_index_repo = DocumentIndexRepository(session)
        analysis_repo = AnalysisRepository(session)
        llm_client = LlmClient(config.llm)
        pdf_converter = PdfConverter()
        pageindex_service = PageIndexService(
            doc_index_repo=doc_index_repo,
            pdf_converter=pdf_converter,
            llm_client=llm_client,
            config=config.pageindex,
        )
        rag_service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            filing_repo=filing_repo,
            llm_client=llm_client,
        )
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/services/financial_sync.py \
        src/stock_analyze_system/cli/container.py
git commit -m "refactor: rename magic constants, add PageIndex enabled check"
```

---

## Task 12: Final cleanup and verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 2: Run ruff linter**

Run: `ruff check src/ tests/`
Expected: No errors (fix any that appear)

- [ ] **Step 3: Verify no remaining private imports across layers**

Run: `grep -rn "from.*import _" src/stock_analyze_system/cli/`
Expected: No results (all private imports removed from CLI layer)

- [ ] **Step 4: Verify no remaining bare filing type strings in source**

Run: `grep -rn '"10-K"\|"10-Q"\|"20-F"\|"6-K"' src/stock_analyze_system/`
Expected: No results in source files (only in test data fixtures is acceptable)

- [ ] **Step 5: Commit any final fixes**

```bash
git add -u
git commit -m "chore: final cleanup after maintainability refactoring"
```
