# JSON-Safe Screening And PDF Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden option B by locking WeasyPrint URL fetching to the supported API for the pinned dependency and making screening JSON responses safe for non-finite metrics.

**Architecture:** Keep file URL safety checks inside `pdf_converter.py`, and delegate actual reads through `URLFetcher`, which is the non-deprecated fetcher API in the pinned `weasyprint>=68,<69` dependency. Add a shared recursive JSON sanitizer in `shared/json_utils.py`, then use it at the `/api/screening/run` response boundary so service/database layers can still reason about non-finite values internally.

**Tech Stack:** Python, pytest, FastAPI TestClient, WeasyPrint 68, Starlette JSONResponse, existing `uv run python -m pytest` workflow.

---

### Task 1: WeasyPrint Fetcher Contract

**Files:**
- Modify: `tests/unit/services/test_pdf_converter.py`
- Modify: `src/stock_analyze_system/services/pdf_converter.py`

- [x] **Step 1: Add a fetcher contract test**

Add a test that patches `stock_analyze_system.services.pdf_converter.URLFetcher`, builds `_build_safe_url_fetcher()`, fetches a local file URI, and asserts `URLFetcher` is constructed with `allowed_protocols={"file", "data"}` and receives the resolved file URI.

- [x] **Step 2: Run the test**

```bash
uv run python -m pytest tests/unit/services/test_pdf_converter.py::TestSafeUrlFetcher::test_delegates_to_url_fetcher_with_allowed_protocols -q
```

Expected: pass under the pinned WeasyPrint 68 contract.

- [x] **Step 3: Keep the non-deprecated adapter**

Do not switch to `default_url_fetcher`: in WeasyPrint 68.1 it emits a deprecation warning and instructs callers to use `URLFetcher`. Keep `URLFetcher` behind `_build_safe_url_fetcher()` so root/scheme checks remain local.

### Task 2: Shared JSON-Safe Sanitizer

**Files:**
- Modify: `tests/unit/shared/test_json_utils.py`
- Modify: `src/stock_analyze_system/shared/json_utils.py`

- [x] **Step 1: Add a failing recursive sanitizer test**

Add a test for `json_safe()` showing `float("inf")`, `float("-inf")`, and `float("nan")` become `None` inside nested dict/list structures while finite numbers and strings remain unchanged.

- [x] **Step 2: Run the failing test**

```bash
uv run python -m pytest tests/unit/shared/test_json_utils.py::test_json_safe_recursively_converts_non_finite_numbers_to_none -q
```

Expected before implementation: import error for `json_safe`.

- [x] **Step 3: Implement `json_safe()`**

Add a recursive function in `shared/json_utils.py` that handles dicts, lists/tuples, non-finite numeric values, and otherwise returns the input unchanged.

### Task 3: Screening API Response Boundary

**Files:**
- Modify: `tests/unit/web/test_screening_api.py`
- Modify: `src/stock_analyze_system/web/routes/screening.py`

- [x] **Step 1: Add a failing API test**

Patch `_require_service()` to return a mock service whose `run_screen()` returns one item with `metrics={"pbr": float("nan"), "psr": float("inf"), "roe": 1.2}`. Post to `/api/screening/run` and assert status 200 with `pbr` and `psr` as JSON `null`, while `roe` remains `1.2`.

- [x] **Step 2: Run the failing test**

```bash
uv run python -m pytest tests/unit/web/test_screening_api.py::TestScreeningApi::test_run_sanitizes_non_finite_metrics -q
```

Expected before implementation: endpoint raises a JSON rendering error or returns non-compliant values.

- [x] **Step 3: Apply `json_safe()` at the route boundary**

Import `json_safe` and wrap `it.metrics` when building the `/api/screening/run` response payload.

### Task 4: Verification And Commit

**Files:**
- No additional files.

- [x] **Step 1: Run targeted suite**

```bash
uv run python -m pytest tests/unit/services/test_pdf_converter.py tests/unit/shared/test_json_utils.py tests/unit/web/test_screening_api.py tests/unit/web/test_dependencies.py tests/unit/web/test_screening_page.py tests/unit/services/test_screening_universe_service.py tests/integration/test_service_assembly.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-05-06-json-safe-pdf-fetcher.md tests/unit/services/test_pdf_converter.py tests/unit/shared/test_json_utils.py tests/unit/web/test_screening_api.py src/stock_analyze_system/services/pdf_converter.py src/stock_analyze_system/shared/json_utils.py src/stock_analyze_system/web/routes/screening.py
git commit -m "fix: harden pdf fetching and screening json output"
```
