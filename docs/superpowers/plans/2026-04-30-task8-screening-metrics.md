# Task 8: ScreeningMetricsService Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ScreeningMetricsService` to populate `screening_cache` from SEC financials (`financial_data`) + Google Sheets cached quotes (`quote_prices`), enabling full-universe screening without Yahoo bulk enrichment.

**Architecture:** A new `ScreeningMetricsService` reads the latest `financial_data` (annual, fallback to quarterly) and `quote_prices` (provider=`google_sheets`) per company, computes valuation ratios, and upserts them into `screening_cache` via the existing `ScreeningRepository.upsert_cache`. The CLI `screening refresh` command gains a `--source sec-google` option that routes to this service. This closes the gap where `screening_cache` currently only has 5 rows because the only enrichment path is YahooFinance bulk.

**Tech Stack:** Python 3.12, SQLAlchemy async, pytest, existing CLI framework.

---

## File Structure

| File | Responsibility |
|------|--------------|
| `src/stock_analyze_system/services/screening_metrics.py` | **Create** — Core service that computes metrics from financials + quotes and writes to `screening_cache`. |
| `tests/unit/services/test_screening_metrics_service.py` | **Create** — Unit tests for the service with mocked repos. |
| `src/stock_analyze_system/cli/screening.py` | **Modify** — Add `--source sec-google` to `screening refresh` subcommand and route to the new service. |
| `src/stock_analyze_system/cli/container.py` | **Modify** — Wire `ScreeningMetricsService` into `ServiceContainer` and `setup_services`. |
| `tests/unit/cli/test_screening_cli.py` | **Modify** — Add CLI tests for `--source sec-google`. |

---

## Phase 0: Commit Task 7 cleanly before starting Task 8

**Prerequisite:** The working tree is dirty with Task 7 changes (valuation quote-provider wiring + CLI) mixed with unrelated SEC daily auto-registration changes, web UI changes, `pyproject.toml`/`uv.lock` drift, and script changes. We must isolate and commit only the Task 7 valuation changes.

### Task 0.1: Audit the diff and isolate Task 7 files

**Files to inspect:**
- `src/stock_analyze_system/services/job.py`
- `src/stock_analyze_system/cli/jobs.py`
- `src/stock_analyze_system/cli/container.py`
- `tests/unit/services/test_job_service.py`
- `tests/unit/cli/test_jobs_cli.py`

**Command:**
```bash
git diff --stat
git diff src/stock_analyze_system/services/job.py | less
```

- [ ] **Step 1: Identify Task 7 hunks in `job.py`**
  Keep hunks that add:
  - `_QUOTE_PROVIDERS`
  - `_validate_quote_provider()`
  - `_get_price_data_for_company()`
  - `update_valuation_for_company()`
  - `run_target_valuation_update()`
  - `target_svc` / `quote_service` constructor wiring
  Exclude hunks that add:
  - `_sec_universe_by_cik()`
  - `register_sec_filer` call inside `_run_us_daily_filing_update()`

- [ ] **Step 2: Identify Task 7 hunks in `test_job_service.py`**
  Keep tests named like `test_update_valuation_*` and `test_target_valuation_update_*`.
  Exclude tests for SEC daily auto-registration.

- [ ] **Step 3: Stage clean files entirely**
  ```bash
  git add src/stock_analyze_system/cli/jobs.py
  git add tests/unit/cli/test_jobs_cli.py
  git add src/stock_analyze_system/cli/container.py
  ```

- [ ] **Step 4: Stage `job.py` selectively**
  ```bash
  git add -p src/stock_analyze_system/services/job.py
  # interactively accept only valuation/provider hunks, skip SEC auto-registration hunks
  ```
  If interactive patch is too error-prone, create a temporary patch of the valuation-only changes and apply it:
  ```bash
  git diff HEAD -- src/stock_analyze_system/services/job.py > /tmp/job_full.diff
  # manually edit /tmp/job_full.diff to remove _sec_universe_by_cik and daily_update changes
  git checkout -- src/stock_analyze_system/services/job.py
  git apply /tmp/job_valuation_only.diff
  git add src/stock_analyze_system/services/job.py
  ```

- [ ] **Step 5: Stage `test_job_service.py` selectively**
  Same pattern as Step 4.

- [ ] **Step 6: Verify nothing else is staged**
  ```bash
  git diff --cached --stat
  ```
  Expected output should list **only**:
  - `src/stock_analyze_system/services/job.py`
  - `src/stock_analyze_system/cli/jobs.py`
  - `src/stock_analyze_system/cli/container.py`
  - `tests/unit/services/test_job_service.py`
  - `tests/unit/cli/test_jobs_cli.py`

- [ ] **Step 7: Run tests for staged files**
  ```bash
  uv run pytest tests/unit/services/test_job_service.py tests/unit/cli/test_jobs_cli.py tests/unit/characterization/test_container_assembly.py -q
  ```
  Expected: `50 passed`

- [ ] **Step 8: Commit Task 7**
  ```bash
  git commit -m "feat: wire google_sheets quote provider into valuation update + CLI"
  ```

---

## Phase 1: ScreeningMetricsService (TDD)

### Task 1.1: Write failing tests

**Files:**
- Create: `tests/unit/services/test_screening_metrics_service.py`

- [ ] **Step 1: Create the test file with three core test cases**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from stock_analyze_system.services.screening_metrics import (
    RefreshMetricsResult,
    ScreeningMetricsService,
)


class TestScreeningMetricsService:
    def _make_service(self):
        company_repo = AsyncMock()
        financial_repo = AsyncMock()
        quote_repo = AsyncMock()
        screening_repo = AsyncMock()
        svc = ScreeningMetricsService(
            company_repo=company_repo,
            financial_repo=financial_repo,
            quote_repo=quote_repo,
            screening_repo=screening_repo,
        )
        return svc, company_repo, financial_repo, quote_repo, screening_repo

    async def test_refresh_creates_cache_from_financials_and_quotes(self):
        svc, company_repo, financial_repo, quote_repo, screening_repo = self._make_service()

        company = MagicMock(id="US_AAPL", ticker="AAPL", sector="Technology")
        company_repo.list_all.return_value = [company]

        financial = MagicMock(
            revenue=394e9,
            operating_income=120e9,
            net_income=94e9,
            equity=100e9,
            total_debt=100e9,
            cash=50e9,
            fcf=111e9,
            ebitda=130e9,
            eps=6.0,
            dps=0.9,
            shares_outstanding=15e9,
            fiscal_year_end="2024-09-28",
        )
        financial_repo.get_latest.side_effect = [
            financial,  # annual
            None,       # quarterly fallback not needed
        ]

        quote = MagicMock(price=185.0, currency="USD", status="ok")
        quote_repo.get_latest_many.return_value = {"US_AAPL": quote}

        result = await svc.refresh_from_sec_google()

        assert result.succeeded == 1
        assert result.skipped_no_financials == 0
        assert result.skipped_no_quote == 0
        screening_repo.upsert_cache.assert_awaited_once()
        args = screening_repo.upsert_cache.await_args
        assert args[0][0] == "US_AAPL"
        payload = args[0][1]
        assert payload["stock_price"] == 185.0
        assert payload["market_cap"] == pytest.approx(185.0 * 15e9)
        assert payload["trailing_per"] == pytest.approx(185.0 / 6.0)
        assert payload["eps"] == 6.0
        assert payload["pbr"] == pytest.approx(185.0 / (100e9 / 15e9))
        assert payload["psr"] == pytest.approx(185.0 / (394e9 / 15e9))
        assert payload["ev_ebitda"] == pytest.approx(
            (185.0 * 15e9 + 100e9 - 50e9) / 130e9
        )
        assert payload["de_ratio"] == pytest.approx(100e9 / 100e9)
        assert payload["roe"] == pytest.approx(94e9 / 100e9)
        assert payload["operating_margin"] == pytest.approx(120e9 / 394e9)
        assert payload["net_margin"] == pytest.approx(94e9 / 394e9)
        assert payload["fcf_yield"] == pytest.approx(111e9 / (185.0 * 15e9))
        assert payload["dividend_yield"] == pytest.approx(0.9 / 185.0)
        assert payload["sector"] == "Technology"
        screening_repo._session.commit.assert_awaited_once()

    async def test_refresh_skips_when_no_financials(self):
        svc, company_repo, financial_repo, quote_repo, screening_repo = self._make_service()
        company_repo.list_all.return_value = [MagicMock(id="US_XXX", ticker="XXX")]
        financial_repo.get_latest.return_value = None
        quote_repo.get_latest_many.return_value = {}

        result = await svc.refresh_from_sec_google()

        assert result.succeeded == 0
        assert result.skipped_no_financials == 1
        screening_repo.upsert_cache.assert_not_awaited()

    async def test_refresh_skips_when_quote_not_ok(self):
        svc, company_repo, financial_repo, quote_repo, screening_repo = self._make_service()
        company_repo.list_all.return_value = [MagicMock(id="US_AAPL", ticker="AAPL")]
        financial_repo.get_latest.return_value = MagicMock(
            eps=6.0, shares_outstanding=15e9, equity=100e9,
            revenue=394e9, total_debt=100e9, cash=50e9,
            ebitda=130e9, net_income=94e9, operating_income=120e9,
            fcf=111e9, dps=0.9,
        )
        quote_repo.get_latest_many.return_value = {
            "US_AAPL": MagicMock(price=None, status="formula_error"),
        }

        result = await svc.refresh_from_sec_google()

        assert result.succeeded == 0
        assert result.skipped_no_quote == 1
        screening_repo.upsert_cache.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**
  ```bash
  uv run pytest tests/unit/services/test_screening_metrics_service.py -v
  ```
  Expected: `3 failed` with `ImportError: cannot import name 'ScreeningMetricsService'`

### Task 1.2: Implement ScreeningMetricsService

**Files:**
- Create: `src/stock_analyze_system/services/screening_metrics.py`

- [ ] **Step 1: Write the service with minimal implementation**

```python
"""Screening cache metrics computation from SEC financials + cached quotes."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.repositories.screening import ScreeningRepository

logger = logging.getLogger(__name__)


@dataclass
class RefreshMetricsResult:
    eligible: int
    processed: int
    succeeded: int
    skipped_no_financials: int
    skipped_no_quote: int
    failed: int


class ScreeningMetricsService:
    """Compute screening_cache rows from financial_data + quote_prices."""

    def __init__(
        self,
        company_repo: CompanyRepository,
        financial_repo: FinancialRepository,
        quote_repo: QuotePriceRepository,
        screening_repo: ScreeningRepository,
    ):
        self._company_repo = company_repo
        self._financial_repo = financial_repo
        self._quote_repo = quote_repo
        self._screening_repo = screening_repo

    async def refresh_from_sec_google(
        self,
        limit: int | None = None,
    ) -> RefreshMetricsResult:
        """Refresh screening_cache using latest SEC financials and Google Sheets quotes."""
        companies = await self._company_repo.list_all()
        companies = [c for c in companies if c.id.startswith("US_")]
        if limit is not None:
            companies = companies[:limit]

        eligible = len(companies)
        succeeded = skipped_no_financials = skipped_no_quote = failed = 0

        company_ids = [c.id for c in companies]
        quotes = await self._quote_repo.get_latest_many(
            company_ids, provider="google_sheets",
        )

        for company in companies:
            fin = await self._financial_repo.get_latest(company.id, "annual")
            if fin is None:
                fin = await self._financial_repo.get_latest(company.id, "quarterly")
            if fin is None:
                skipped_no_financials += 1
                continue

            quote = quotes.get(company.id)
            if quote is None or quote.status != "ok" or quote.price is None:
                skipped_no_quote += 1
                continue

            try:
                payload = self._compute_metrics(company, fin, quote)
                await self._screening_repo.upsert_cache(company.id, payload)
                await self._screening_repo._session.commit()
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                await self._screening_repo._session.rollback()
                logger.warning(
                    "screening metrics upsert failed for %s: %s",
                    company.id, exc, exc_info=exc,
                )
                failed += 1

        return RefreshMetricsResult(
            eligible=eligible,
            processed=eligible,
            succeeded=succeeded,
            skipped_no_financials=skipped_no_financials,
            skipped_no_quote=skipped_no_quote,
            failed=failed,
        )

    @staticmethod
    def _compute_metrics(company, fin, quote) -> dict:
        price = quote.price
        shares = fin.shares_outstanding
        revenue = fin.revenue
        equity = fin.equity
        total_debt = fin.total_debt
        cash = fin.cash
        ebitda = fin.ebitda
        eps = fin.eps
        net_income = fin.net_income
        operating_income = fin.operating_income
        fcf = fin.fcf
        dps = fin.dps

        market_cap = price * shares if price is not None and shares else None

        trailing_per = price / eps if price is not None and eps else None

        book_value_per_share = equity / shares if equity is not None and shares else None
        pbr = price / book_value_per_share if price is not None and book_value_per_share else None

        psr = (
            price / (revenue / shares)
            if price is not None and revenue is not None and shares
            else None
        )

        ev = (
            (market_cap + total_debt - cash)
            if market_cap is not None and total_debt is not None and cash is not None
            else None
        )
        ev_ebitda = ev / ebitda if ev is not None and ebitda else None

        de_ratio = total_debt / equity if total_debt is not None and equity else None
        roe = net_income / equity if net_income is not None and equity else None
        operating_margin = (
            operating_income / revenue
            if operating_income is not None and revenue
            else None
        )
        net_margin = net_income / revenue if net_income is not None and revenue else None
        fcf_yield = (
            fcf / market_cap
            if fcf is not None and market_cap
            else None
        )
        dividend_yield = dps / price if dps is not None and price else None

        return {
            "stock_price": price,
            "market_cap": market_cap,
            "trailing_per": trailing_per,
            "eps": eps,
            "pbr": pbr,
            "psr": psr,
            "ev_ebitda": ev_ebitda,
            "de_ratio": de_ratio,
            "roe": roe,
            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "fcf_yield": fcf_yield,
            "dividend_yield": dividend_yield,
            "sector": company.sector,
        }
```

- [ ] **Step 2: Run tests to verify they pass**
  ```bash
  uv run pytest tests/unit/services/test_screening_metrics_service.py -v
  ```
  Expected: `3 passed`

- [ ] **Step 3: Commit**
  ```bash
  git add src/stock_analyze_system/services/screening_metrics.py
  git add tests/unit/services/test_screening_metrics_service.py
  git commit -m "feat: add ScreeningMetricsService for sec-google screening cache"
  ```

---

## Phase 2: CLI Integration & Container Wiring

### Task 2.1: Add `--source sec-google` to screening refresh CLI

**Files:**
- Modify: `src/stock_analyze_system/cli/screening.py`

- [ ] **Step 1: Add `source` argument to refresh subparser**

In `register_parser`, change:
```python
rf = sub.add_parser("refresh", help="Yahoo enrichment")
rf.add_argument("--limit", type=int, default=None)
rf.add_argument("--stale-hours", type=int, default=24)
rf.add_argument("--concurrency", type=int, default=8)
```
to:
```python
rf = sub.add_parser("refresh", help="refresh screening cache")
rf.add_argument("--source", default="yahoo", choices=["yahoo", "sec-google"])
rf.add_argument("--limit", type=int, default=None)
rf.add_argument("--stale-hours", type=int, default=24)
rf.add_argument("--concurrency", type=int, default=8)
```

- [ ] **Step 2: Route `sec-google` in `handle`**

In `handle`, replace the `if args.action == "refresh":` block:
```python
    if args.action == "refresh":
        if args.source == "sec-google":
            metrics_svc = services.screening_metrics_service
            if metrics_svc is None:
                print("ERROR: screening_metrics_service is unavailable.", file=sys.stderr)
                sys.exit(1)
            r = await metrics_svc.refresh_from_sec_google(limit=args.limit)
            print(f"Screening metrics refresh (source=sec-google)")
            print(f"  eligible: {r.eligible}, succeeded: {r.succeeded}")
            print(f"  skipped (no financials): {r.skipped_no_financials}")
            print(f"  skipped (no quote): {r.skipped_no_quote}")
            print(f"  failed: {r.failed}")
        else:
            r = await universe_svc.enrich_with_yahoo(
                limit=args.limit,
                stale_hours=args.stale_hours,
                max_concurrency=args.concurrency,
            )
            print(f"Enrichment (source=yahoo, eligible={r.eligible}, attempted={r.attempted}, "
                  f"concurrency={args.concurrency})")
            print(f"  succeeded: {r.succeeded}, failed: {r.failed}, skipped: {r.skipped}")
            print(f"  elapsed: {r.elapsed_seconds:.1f}s")
        return
```

### Task 2.2: Wire ScreeningMetricsService into ServiceContainer

**Files:**
- Modify: `src/stock_analyze_system/cli/container.py`

- [ ] **Step 1: Add import and field to ServiceContainer**

In `if TYPE_CHECKING:` block, add:
```python
from stock_analyze_system.services.screening_metrics import ScreeningMetricsService
```

In `ServiceContainer` dataclass, add:
```python
screening_metrics_service: ScreeningMetricsService | None = None
```

- [ ] **Step 2: Instantiate in `setup_services`**

After `screening_svc = ScreeningService(...)`:
```python
    from stock_analyze_system.services.screening_metrics import ScreeningMetricsService

    screening_metrics_svc = ScreeningMetricsService(
        company_repo=company_repo,
        financial_repo=financial_repo,
        quote_repo=quote_repo,
        screening_repo=screening_repo,
    )
```

And add `screening_metrics_service=screening_metrics_svc` to the `ServiceContainer(...)` constructor call.

### Task 2.3: Add CLI tests

**Files:**
- Modify: `tests/unit/cli/test_screening_cli.py`

- [ ] **Step 1: Add tests for `--source sec-google`**

```python
class TestScreeningRefreshSource:
    def test_refresh_accepts_sec_google_source(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)

        args = parser.parse_args(["screening", "refresh", "--source", "sec-google"])
        assert args.source == "sec-google"

    async def test_refresh_sec_google_runs_metrics_service(self, capsys):
        svc = _make_services()
        from stock_analyze_system.services.screening_metrics import RefreshMetricsResult
        result = RefreshMetricsResult(
            eligible=10, processed=10, succeeded=8,
            skipped_no_financials=1, skipped_no_quote=1, failed=0,
        )
        svc.screening_metrics_service.refresh_from_sec_google.return_value = result

        args = argparse.Namespace(
            action="refresh",
            source="sec-google",
            limit=None,
            json_output=False,
        )
        await handle(args, svc)

        svc.screening_metrics_service.refresh_from_sec_google.assert_awaited_once_with(limit=None)
        out = capsys.readouterr().out
        assert "sec-google" in out
        assert "succeeded: 8" in out
```

- [ ] **Step 2: Run all screening CLI tests**
  ```bash
  uv run pytest tests/unit/cli/test_screening_cli.py -v
  ```
  Expected: all pass (existing + new)

- [ ] **Step 3: Commit**
  ```bash
  git add src/stock_analyze_system/cli/screening.py
  git add src/stock_analyze_system/cli/container.py
  git add tests/unit/cli/test_screening_cli.py
  git commit -m "feat: add --source sec-google to screening refresh CLI"
  ```

---

## Phase 3: Operational Validation

**Goal:** Run the full pipeline against the real DB and confirm `screening_cache` grows beyond 5 rows.

### Task 3.1: Populate companies universe

- [ ] **Step 1: Run universe refresh**
  ```bash
  uv run stock-analyze screening universe refresh
  ```
  Expected: `fetched: ~12000`, `inserted: >0`, `updated: >0`

### Task 3.2: Populate quote_prices

- [ ] **Step 1: Run Google Sheets quote refresh**
  ```bash
  uv run stock-analyze quotes refresh --provider google_sheets
  ```
  Expected: `succeeded: >0` (depending on sheet contents)

### Task 3.3: Populate screening_cache via sec-google

- [ ] **Step 1: Run screening refresh with sec-google source**
  ```bash
  uv run stock-analyze screening refresh --source sec-google
  ```
  Expected: `eligible: >0`, `succeeded: >0`

- [ ] **Step 2: Verify DB counts**
  ```bash
  uv run python -c "
  import sqlite3
  conn = sqlite3.connect('data/stock_analyze.db')
  c = conn.cursor()
  for t in ['companies', 'quote_prices', 'screening_cache']:
      c.execute(f'SELECT COUNT(*) FROM {t}')
      print(f'{t}: {c.fetchone()[0]}')
  conn.close()
  "
  ```
  Expected: `companies: >>5`, `quote_prices: >0`, `screening_cache: >>5`

### Task 3.4: Run screening

- [ ] **Step 1: Run a broad screen**
  ```bash
  uv run stock-analyze screening run --gte trailing_per=0 --limit 50
  ```
  Expected: `matched=>>5`, shown=50

---

## Self-Review Checklist

1. **Spec coverage:**
   - ✅ Task 7 isolation before Task 8 → Phase 0
   - ✅ ScreeningMetricsService creation → Phase 1
   - ✅ `--source sec-google` CLI → Phase 2
   - ✅ Container wiring → Phase 2
   - ✅ Operational pipeline validation → Phase 3

2. **Placeholder scan:**
   - No "TBD", "TODO", "implement later" in code steps.
   - All test code is complete.
   - All commands have expected outputs.

3. **Type consistency:**
   - `RefreshMetricsResult` fields match usage in service and CLI.
   - `ScreeningRepository.upsert_cache` signature unchanged.
   - `QuotePriceRepository.get_latest_many` signature unchanged.

4. **Gap check:**
   - `forward_per`, `peg_ratio`, `revenue_growth`, `earnings_growth`, `beta`, `volume`, `industry`, `exchange`, `most_recent_quarter`, `last_fiscal_year_end`, `trailing_eps_date` are intentionally left `None` in Phase 1 because we lack data sources for them in the sec-google path. This is acceptable per YAGNI; they can be added later when data becomes available.
   - Error handling: per-record rollback + continue is consistent with `enrich_with_yahoo` pattern.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-30-task8-screening-metrics.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints for review.

**Which approach?**
