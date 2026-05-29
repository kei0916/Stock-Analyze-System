# Review Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent regressions like the review findings by making RAG DI, screening payload normalization, and web navigation/page routing executable contracts.

**Architecture:** Keep existing runtime behavior and add contract tests at the boundaries where the regressions occur. The only production-code change is a clarifying repository docstring so future code routes external screening payloads through the DB-safe normalizer.

**Tech Stack:** Python, FastAPI TestClient, pytest, SQLAlchemy async repositories, existing `uv run python -m pytest` workflow.

---

### Task 1: RAG Enabled Runtime DI Contract

**Files:**
- Modify: `tests/unit/web/test_dependencies.py`

- [x] **Step 1: Add a contract test**

Add a test that creates `AppState` with `pageindex.enabled=True`, calls `get_services()`, and asserts that:
- `services.rag_service` is built.
- `services.rag_service._qa_history_repo` is present.
- `services.rag_service._filing_content_service` is the same instance as `services.filing_content_service`.

- [x] **Step 2: Run the test**

Run:

```bash
uv run python -m pytest tests/unit/web/test_dependencies.py::test_get_services_wires_rag_when_pageindex_enabled -q
```

Expected if the old review regression exists: import/constructor failure or missing dependency assertion failure.

- [x] **Step 3: Keep implementation minimal**

If the test fails, fix only the DI mismatch in `src/stock_analyze_system/cli/container.py` and `src/stock_analyze_system/services/rag_service.py`. If it passes, keep the test as a regression contract.

### Task 2: Screening Payload Boundary Contract

**Files:**
- Modify: `tests/unit/services/test_screening_universe_service.py`
- Modify: `src/stock_analyze_system/repositories/screening.py`

- [x] **Step 1: Add a service-level enrichment test**

Add a test where Yahoo returns ISO date strings for `most_recent_quarter` and `last_fiscal_year_end`. Assert enrichment succeeds, failed count stays zero, and stored cache columns are Python `date` values.

- [x] **Step 2: Run the test**

Run:

```bash
uv run python -m pytest tests/unit/services/test_screening_universe_service.py::TestEnrichWithYahoo::test_yahoo_date_strings_are_normalized_before_commit -q
```

Expected if the old review regression exists: enrichment failed count is one or SQLAlchemy raises during flush.

- [x] **Step 3: Clarify the normalizer boundary**

Update `ScreeningRepository.upsert_cache()` docstring to state that it accepts external/Yahoo-style payloads and normalizes them before writing `ScreeningCache`.

### Task 3: Navigation And Page/API Route Contract

**Files:**
- Modify: `tests/unit/web/test_screening_page.py`

- [x] **Step 1: Add a rendered-nav contract test**

Parse rendered sidebar links from the authenticated dashboard response and request each linked href. Assert none return 404. This binds `_sidebar.html` to actual registered page routes instead of a manually duplicated href tuple.

- [x] **Step 2: Run the test**

Run:

```bash
uv run python -m pytest tests/unit/web/test_screening_page.py::TestScreeningPage::test_rendered_sidebar_links_resolve_for_authenticated_user -q
```

Expected if the old review regression exists: `/screening` returns 404.

### Task 4: Final Verification

**Files:**
- No production files beyond the docstring change.

- [x] **Step 1: Run targeted review-regression suite**

```bash
uv run python -m pytest tests/unit/web/test_dependencies.py tests/unit/web/test_screening_page.py tests/unit/web/test_screening_api.py tests/unit/repositories/test_other_repos.py::test_screening_upsert_normalizes_external_payload tests/unit/repositories/test_other_repos.py::test_screening_upsert_normalizes_realistic_date_and_value_forms tests/unit/repositories/test_other_repos.py::test_screening_upsert_normalizes_date_field_forms tests/unit/services/test_screening_universe_service.py tests/integration/test_service_assembly.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-05-06-review-contract-hardening.md tests/unit/web/test_dependencies.py tests/unit/services/test_screening_universe_service.py tests/unit/web/test_screening_page.py src/stock_analyze_system/repositories/screening.py
git commit -m "test: harden review regression contracts"
```
