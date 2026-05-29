# Screening SEC Universe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure screening refreshes ingest the SEC ticker universe before computing screening metrics.

**Architecture:** Keep universe ingestion in `ScreeningUniverseService`. Have CLI refresh paths call it before provider-specific metric refresh, and let `ScreeningMetricsService` optionally accept a universe refresh callback for direct service callers.

**Tech Stack:** Python, pytest, AsyncMock, SQLAlchemy async repositories.

---

### Task 1: Yahoo Refresh Calls Universe First

**Files:**
- Modify: `tests/unit/cli/test_screening_cli.py`
- Modify: `src/stock_analyze_system/cli/screening.py`

- [ ] **Step 1: Write the failing test**

Add a CLI test that records call order:

```python
@pytest.mark.asyncio
async def test_refresh_yahoo_refreshes_universe_before_enrich(self):
    calls = []
    univ = MagicMock()

    async def refresh_universe():
        calls.append("universe")
        return RefreshUniverseResult(fetched=2, inserted=1, updated=1, skipped=0)

    async def enrich_with_yahoo(**_kwargs):
        calls.append("enrich")
        return EnrichResult(
            eligible=1, attempted=1, succeeded=1, failed=0, skipped=0,
            elapsed_seconds=0.1,
        )

    univ.refresh_universe = AsyncMock(side_effect=refresh_universe)
    univ.enrich_with_yahoo = AsyncMock(side_effect=enrich_with_yahoo)
    await cli_screening.handle(
        _parse(["refresh", "--source", "yahoo"]),
        _make_services(universe=univ, screen=MagicMock()),
    )
    assert calls == ["universe", "enrich"]
```

- [ ] **Step 2: Verify it fails**

Run:

```bash
uv run pytest tests/unit/cli/test_screening_cli.py::TestCli::test_refresh_yahoo_refreshes_universe_before_enrich -q
```

Expected: FAIL because `refresh_universe()` is not called by the `refresh` path.

- [ ] **Step 3: Implement minimal CLI change**

In `src/stock_analyze_system/cli/screening.py`, call `await universe_svc.refresh_universe()` before `enrich_with_yahoo()` and print the universe summary.

- [ ] **Step 4: Verify it passes**

Run the same pytest command. Expected: PASS.

### Task 2: SEC-Google Refresh Calls Universe First

**Files:**
- Modify: `tests/unit/cli/test_screening_cli.py`
- Modify: `src/stock_analyze_system/cli/screening.py`

- [ ] **Step 1: Write the failing test**

Add a CLI test that records `refresh_universe()` before
`refresh_from_sec_google()` for `--source sec-google`.

- [ ] **Step 2: Verify it fails**

Run:

```bash
uv run pytest tests/unit/cli/test_screening_cli.py::TestScreeningRefreshSource::test_refresh_sec_google_refreshes_universe_first -q
```

Expected: FAIL because the `sec-google` branch currently returns before loading
`universe_svc`.

- [ ] **Step 3: Implement minimal CLI change**

Move service availability checks so the `sec-google` branch also requires
`screening_universe_service`, then call `refresh_universe()` before metrics.

- [ ] **Step 4: Verify it passes**

Run the same pytest command. Expected: PASS.

### Task 3: Service-Level Hook for Direct Callers

**Files:**
- Modify: `tests/unit/services/test_screening_metrics_service.py`
- Modify: `src/stock_analyze_system/services/screening_metrics.py`
- Modify: `src/stock_analyze_system/cli/container.py`

- [ ] **Step 1: Write the failing test**

Add a test that constructs `ScreeningMetricsService(..., universe_refresher=AsyncMock())`,
calls `refresh_from_sec_google()`, and asserts the refresher ran before
`company_repo.list_all()`.

- [ ] **Step 2: Verify it fails**

Run:

```bash
uv run pytest tests/unit/services/test_screening_metrics_service.py::test_refresh_runs_universe_refresher_before_listing_companies -q
```

Expected: FAIL because the constructor does not accept `universe_refresher`.

- [ ] **Step 3: Implement minimal service change**

Add an optional async `universe_refresher` dependency to
`ScreeningMetricsService`, call it at the start of `refresh_from_sec_google()`,
and wire it in `cli/container.py` with `screening_universe_svc.refresh_universe`.

- [ ] **Step 4: Verify focused tests**

Run:

```bash
uv run pytest tests/unit/cli/test_screening_cli.py tests/unit/services/test_screening_metrics_service.py -q
```

Expected: PASS.

### Task 4: Chunk Native Bulk Upserts

**Files:**
- Modify: `tests/unit/repositories/test_base_repo.py`
- Modify: `src/stock_analyze_system/repositories/base.py`

- [ ] **Step 1: Write the failing test**

Add `test_bulk_upsert_native_chunks_large_insert`, inserting 6,000 company rows
with `_bulk_upsert_native(..., update_columns=[])`.

- [ ] **Step 2: Verify it fails**

Run:

```bash
uv run pytest tests/unit/repositories/test_base_repo.py::test_bulk_upsert_native_chunks_large_insert -q
```

Expected: FAIL with `sqlite3.OperationalError: too many SQL variables`.

- [ ] **Step 3: Implement batching**

Compute a safe batch size from the maximum row width and execute one SQLite
insert/upsert statement per batch.

- [ ] **Step 4: Verify repository tests**

Run:

```bash
uv run pytest tests/unit/repositories/test_base_repo.py -q
```

Expected: PASS.
