# SEC EDGAR Daily Filing-Based Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `jobs daily --market us` process only SEC EDGAR filings whose SEC `filingDate` is the target date, while updating financial data only for companies with financial-reporting filings.

**Architecture:** Add a SEC daily index reader to `SecEdgarClient`, normalize index rows into the existing filing-record shape, add a pre-fetched-record entry point to `FilingSyncService`, and branch `JobService.run_daily_update()` so US daily updates are filing-driven while JP/EDINET remains unchanged. SEC request rate configuration is set and propagated as 10 requests/second.

**Tech Stack:** Python 3.11+, SQLAlchemy async models/services, `httpx` via existing `BaseClient`, `argparse`, `pytest` / `pytest-asyncio`, `pytest-httpx`.

---

## File Structure

- Modify: `src/stock_analyze_system/config.py`
  - Change SEC EDGAR default rate to `10`.
- Modify: `config/settings.yaml.example`
  - Change sample SEC EDGAR rate to `10`.
- Modify: `src/stock_analyze_system/cli/container.py`
  - Pass `config.sec_edgar.rate_limit_rps` to `SecEdgarClient`.
- Modify: `src/stock_analyze_system/web/dependencies.py`
  - Pass `config.sec_edgar.rate_limit_rps` to the web singleton `SecEdgarClient`.
- Modify: `src/stock_analyze_system/ingestion/sec_edgar.py`
  - Add SEC daily index URL construction and `list_daily_filings()`.
- Modify: `src/stock_analyze_system/services/filing_sync.py`
  - Add `update_from_sec_records()` and `list_daily_sec_filings()`.
  - Treat `40-F` as annual.
- Modify: `src/stock_analyze_system/services/job.py`
  - Add US filing-driven daily path with SEC `filingDate` target date support.
  - Keep JP path on existing all-company `sync_company()` flow.
  - Extract valuation update logic so `sync_company()` and filing-driven daily processing share it.
- Modify: `src/stock_analyze_system/cli/jobs.py`
  - Add optional `--filing-date YYYY-MM-DD`.
  - Pass parsed date to `run_daily_update()`.
- Modify tests:
  - `tests/unit/test_config.py`
  - `tests/unit/characterization/test_container_assembly.py`
  - `tests/unit/web/test_dependencies.py`
  - `tests/unit/ingestion/test_sec_edgar.py`
  - `tests/unit/services/test_filing_sync.py`
  - `tests/unit/services/test_job_service.py`
  - `tests/unit/cli/test_jobs_cli.py`

## Task 1: SEC Rate Limit Configuration

**Files:**
- Modify: `tests/unit/test_config.py`
- Modify: `tests/unit/characterization/test_container_assembly.py`
- Modify: `tests/unit/web/test_dependencies.py`
- Modify: `src/stock_analyze_system/config.py`
- Modify: `config/settings.yaml.example`
- Modify: `src/stock_analyze_system/cli/container.py`
- Modify: `src/stock_analyze_system/web/dependencies.py`

- [ ] **Step 1: Add failing config default assertion**

In `tests/unit/test_config.py`, inside `TestLoadConfig.test_default_config`, add:

```python
        assert config.sec_edgar.rate_limit_rps == 10
```

- [ ] **Step 2: Add failing CLI container rate propagation test**

In `tests/unit/characterization/test_container_assembly.py`, add this import near the top:

```python
from unittest.mock import patch
```

Add this test method inside `TestSetupServicesAssembly`:

```python
    async def test_setup_services_passes_sec_rate_limit(self, session):
        config = build_test_config(pageindex_enabled=False)
        config.sec_edgar.email = "sec@example.com"
        config.sec_edgar.rate_limit_rps = 10

        with patch("stock_analyze_system.ingestion.sec_edgar.SecEdgarClient") as sec_cls:
            await setup_services(session, config)

        sec_cls.assert_called_once_with(email="sec@example.com", rate=10)
```

- [ ] **Step 3: Add failing web AppState rate propagation test**

In `tests/unit/web/test_dependencies.py`, add this test after `test_app_state_creates_engine`:

```python
async def test_app_state_passes_sec_rate_limit(tmp_path):
    cfg = AppConfig()
    cfg.database.path = str(tmp_path / "rate.db")
    cfg.sec_edgar.email = "sec@example.com"
    cfg.sec_edgar.rate_limit_rps = 10

    with patch("stock_analyze_system.ingestion.sec_edgar.SecEdgarClient") as sec_cls:
        state = await AppState.create(cfg)

    try:
        sec_cls.assert_called_once_with(email="sec@example.com", rate=10)
    finally:
        await state.engine.dispose()
```

- [ ] **Step 4: Run the new failing tests**

Run:

```bash
uv run pytest tests/unit/test_config.py::TestLoadConfig::test_default_config tests/unit/characterization/test_container_assembly.py::TestSetupServicesAssembly::test_setup_services_passes_sec_rate_limit tests/unit/web/test_dependencies.py::test_app_state_passes_sec_rate_limit -q
```

Expected: FAIL because the default is still `5` and client constructors do not pass `rate`.

- [ ] **Step 5: Implement SEC rate default and propagation**

In `src/stock_analyze_system/config.py`, change:

```python
class SecEdgarConfig:
    email: str = ""
    rate_limit_rps: int = 5
```

to:

```python
class SecEdgarConfig:
    email: str = ""
    rate_limit_rps: int = 10
```

In `config/settings.yaml.example`, change:

```yaml
sec_edgar:
  email: "user@example.com"
  rate_limit_rps: 5
```

to:

```yaml
sec_edgar:
  email: "user@example.com"
  rate_limit_rps: 10
```

In `src/stock_analyze_system/cli/container.py`, change:

```python
        sec_client = SecEdgarClient(email=config.sec_edgar.email)
```

to:

```python
        sec_client = SecEdgarClient(
            email=config.sec_edgar.email,
            rate=config.sec_edgar.rate_limit_rps,
        )
```

In `src/stock_analyze_system/web/dependencies.py`, change:

```python
            sec=SecEdgarClient(email=config.sec_edgar.email),
```

to:

```python
            sec=SecEdgarClient(
                email=config.sec_edgar.email,
                rate=config.sec_edgar.rate_limit_rps,
            ),
```

- [ ] **Step 6: Run the task tests**

Run:

```bash
uv run pytest tests/unit/test_config.py::TestLoadConfig::test_default_config tests/unit/characterization/test_container_assembly.py::TestSetupServicesAssembly::test_setup_services_passes_sec_rate_limit tests/unit/web/test_dependencies.py::test_app_state_passes_sec_rate_limit -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/config.py config/settings.yaml.example src/stock_analyze_system/cli/container.py src/stock_analyze_system/web/dependencies.py tests/unit/test_config.py tests/unit/characterization/test_container_assembly.py tests/unit/web/test_dependencies.py
git commit -m "config: set SEC EDGAR rate limit to 10 rps"
```

## Task 2: SEC Daily Index Reader

**Files:**
- Modify: `tests/unit/ingestion/test_sec_edgar.py`
- Modify: `src/stock_analyze_system/ingestion/sec_edgar.py`

- [ ] **Step 1: Add failing daily index tests**

In `tests/unit/ingestion/test_sec_edgar.py`, add this import:

```python
from datetime import date
```

Add this test class near `TestListFilings`:

```python
class TestListDailyFilings:
    async def test_list_daily_filings_parses_master_index(self, mock_edgar):
        index_text = """Description: Master Index of EDGAR Dissemination Feed
Last Data Received: April 28, 2026
Comments: webmaster@sec.gov
Anonymous FTP: ftp://ftp.sec.gov/edgar/

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
320193|Apple Inc.|10-K|2026-04-28|edgar/data/320193/0000320193-26-000001.txt
789019|Microsoft Corp|8-K|2026-04-28|edgar/data/789019/0000789019-26-000002.txt
999999|Other Corp|4|2026-04-28|edgar/data/999999/0000999999-26-000003.txt
"""
        mock_edgar.add_response(
            url="https://www.sec.gov/Archives/edgar/daily-index/2026/QTR2/master.20260428.idx",
            text=index_text,
        )

        async with SecEdgarClient(email="test@example.com") as client:
            filings = await client.list_daily_filings(
                date(2026, 4, 28),
                form_types=["10-K", "8-K"],
            )

        assert len(filings) == 2
        assert filings[0] == {
            "cik": "0000320193",
            "companyName": "Apple Inc.",
            "form": "10-K",
            "filingDate": "2026-04-28",
            "reportDate": "",
            "accessionNumber": "0000320193-26-000001",
            "primaryDocument": "",
            "primaryDocDescription": "",
            "documentUrl": "https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001.txt",
        }
        assert filings[1]["cik"] == "0000789019"
        assert filings[1]["form"] == "8-K"

    async def test_list_daily_filings_skips_malformed_rows(self, mock_edgar, caplog):
        index_text = """CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
not-a-cik|Bad Corp|10-K|2026-04-28|edgar/data/bad/file.txt
320193|Apple Inc.|10-K|2026-04-27|edgar/data/320193/old.txt
320193|Apple Inc.|10-Q|2026-04-28|edgar/data/320193/0000320193-26-000004.txt
"""
        mock_edgar.add_response(
            url="https://www.sec.gov/Archives/edgar/daily-index/2026/QTR2/master.20260428.idx",
            text=index_text,
        )

        async with SecEdgarClient(email="test@example.com") as client:
            with caplog.at_level("WARNING", logger="stock_analyze_system.ingestion.sec_edgar"):
                filings = await client.list_daily_filings(date(2026, 4, 28))

        assert len(filings) == 1
        assert filings[0]["accessionNumber"] == "0000320193-26-000004"
        assert any("invalid daily filing row" in r.getMessage() for r in caplog.records)
```

- [ ] **Step 2: Run the new failing tests**

Run:

```bash
uv run pytest tests/unit/ingestion/test_sec_edgar.py::TestListDailyFilings -q
```

Expected: FAIL because `SecEdgarClient.list_daily_filings()` does not exist.

- [ ] **Step 3: Implement daily index parsing**

In `src/stock_analyze_system/ingestion/sec_edgar.py`, replace the existing imports:

```python
import logging
from datetime import datetime, timedelta
```

with:

```python
import logging
from collections.abc import Collection
from datetime import date as date_type
from datetime import datetime, timedelta
from pathlib import PurePosixPath
```

Add this constant near the other SEC URL constants:

```python
_DAILY_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/daily-index/"
    "{year}/QTR{quarter}/master.{yyyymmdd}.idx"
)
```

Add these helpers before `class SecEdgarClient`:

```python
def _quarter_for_date(filing_date: date_type) -> int:
    """Return SEC quarter number for a calendar date."""
    return ((filing_date.month - 1) // 3) + 1


def _daily_index_url(filing_date: date_type) -> str:
    """Build SEC daily master index URL for a filing date."""
    return _DAILY_INDEX_URL.format(
        year=filing_date.year,
        quarter=_quarter_for_date(filing_date),
        yyyymmdd=filing_date.strftime("%Y%m%d"),
    )


def _normalize_cik(raw: str) -> str:
    """Normalize a CIK value to SEC's 10-digit string form."""
    return str(int(raw)).zfill(10)


def _accession_from_filename(filename: str) -> str:
    """Extract accession number from a daily-index filename."""
    return PurePosixPath(filename).stem
```

Change the constructor signature:

```python
    def __init__(self, email: str, rate: float = 5.0):
```

to:

```python
    def __init__(self, email: str, rate: float = 10.0):
```

Add this method to `SecEdgarClient` after `list_filings()`:

```python
    async def list_daily_filings(
        self,
        filing_date: date_type,
        form_types: Collection[str] | None = None,
    ) -> list[dict]:
        """SEC daily master index rows for one SEC filingDate.

        Args:
            filing_date: SEC filing date to fetch.
            form_types: Optional form filter. If omitted, all forms in the
                daily index are returned.

        Returns:
            Normalized filing records compatible with FilingSyncService.
        """
        resp = await self._get(_daily_index_url(filing_date))
        allowed_forms = set(form_types) if form_types is not None else None
        target_date = filing_date.isoformat()
        rows: list[dict] = []
        in_table = False

        for line in resp.text.splitlines():
            if not in_table:
                if line.startswith("----"):
                    in_table = True
                continue
            if not line.strip():
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 5:
                logger.warning("invalid daily filing row: %s", line)
                continue
            cik_raw, company_name, form, filed_at, filename = parts
            if filed_at != target_date:
                continue
            if allowed_forms is not None and form not in allowed_forms:
                continue
            try:
                cik = _normalize_cik(cik_raw)
            except ValueError:
                logger.warning("invalid daily filing row: %s", line)
                continue
            accession_no = _accession_from_filename(filename)
            if not accession_no:
                logger.warning("invalid daily filing row: %s", line)
                continue
            rows.append({
                "cik": cik,
                "companyName": company_name,
                "form": form,
                "filingDate": filed_at,
                "reportDate": "",
                "accessionNumber": accession_no,
                "primaryDocument": "",
                "primaryDocDescription": "",
                "documentUrl": f"https://www.sec.gov/Archives/{filename}",
            })

        return rows
```

- [ ] **Step 4: Run SEC ingestion tests**

Run:

```bash
uv run pytest tests/unit/ingestion/test_sec_edgar.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/ingestion/sec_edgar.py tests/unit/ingestion/test_sec_edgar.py
git commit -m "feat(sec): read daily EDGAR filing index"
```

## Task 3: FilingSync Prefetched SEC Records

**Files:**
- Modify: `tests/unit/services/test_filing_sync.py`
- Modify: `src/stock_analyze_system/services/filing_sync.py`

- [ ] **Step 1: Add failing tests for pre-fetched SEC records**

In `tests/unit/services/test_filing_sync.py`, add this import:

```python
from datetime import date
```

In `tests/unit/services/test_filing_sync.py`, add these tests inside `TestFilingSyncService`:

```python
    async def test_update_from_sec_records_registers_prefetched_daily_filing(self):
        filing_repo = AsyncMock()
        filing_repo.find_existing_accessions.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        sec_client = AsyncMock()
        daily_records = [
            {
                "form": "8-K",
                "accessionNumber": "0000789019-26-000002",
                "reportDate": "",
                "filingDate": "2026-04-28",
                "documentUrl": "https://www.sec.gov/Archives/edgar/data/789019/0000789019-26-000002.txt",
            },
        ]
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=sec_client,
            edinet_client=AsyncMock(),
        )

        count = await svc.update_from_sec_records("US_MSFT", daily_records)

        assert count == 1
        sec_client.list_filings.assert_not_called()
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["filing_type"] == "8-K"
        assert rows[0]["period_type"] == "quarterly"
        assert rows[0]["fiscal_year"] == 2026
        assert "period_end" not in rows[0]

    async def test_update_from_sec_records_treats_40f_as_annual(self):
        filing_repo = AsyncMock()
        filing_repo.find_existing_accessions.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(),
            edinet_client=AsyncMock(),
        )

        await svc.update_from_sec_records("US_SHOP", [
            {
                "form": "40-F",
                "accessionNumber": "0001594805-26-000001",
                "reportDate": "2025-12-31",
                "filingDate": "2026-02-15",
            },
        ])

        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["period_type"] == "annual"
        assert rows[0]["period_end"].isoformat() == "2025-12-31"
```

Add this test class near `TestUpdateFromSecErrors`:

```python
class TestDailySecFilingListing:
    async def test_list_daily_sec_filings_delegates_to_client(self):
        sec_client = AsyncMock()
        sec_client.list_daily_filings.return_value = [{"form": "10-K"}]
        svc = _make_filing_svc(sec_client=sec_client)

        result = await svc.list_daily_sec_filings(date(2026, 4, 28), form_types=["10-K"])

        assert result == [{"form": "10-K"}]
        sec_client.list_daily_filings.assert_awaited_once_with(
            date(2026, 4, 28),
            form_types=["10-K"],
        )
```

- [ ] **Step 2: Run the new failing tests**

Run:

```bash
uv run pytest tests/unit/services/test_filing_sync.py::TestFilingSyncService::test_update_from_sec_records_registers_prefetched_daily_filing tests/unit/services/test_filing_sync.py::TestFilingSyncService::test_update_from_sec_records_treats_40f_as_annual tests/unit/services/test_filing_sync.py::TestDailySecFilingListing::test_list_daily_sec_filings_delegates_to_client -q
```

Expected: FAIL because the new methods do not exist and `40-F` is not annual.

- [ ] **Step 3: Implement pre-fetched SEC record support**

In `src/stock_analyze_system/services/filing_sync.py`, add this module constant near the imports:

```python
_SEC_ANNUAL_FORMS = frozenset({
    FilingType.TEN_K,
    FilingType.TWENTY_F,
    "40-F",
})
```

Change this block in `_map_sec_record`:

```python
    period_type = (
        PeriodType.ANNUAL
        if form in (FilingType.TEN_K, FilingType.TWENTY_F)
        else PeriodType.QUARTERLY
    )
```

to:

```python
    period_type = (
        PeriodType.ANNUAL
        if form in _SEC_ANNUAL_FORMS
        else PeriodType.QUARTERLY
    )
```

Add these methods to `FilingSyncService` after `update_from_sec()`:

```python
    async def list_daily_sec_filings(
        self,
        filing_date: date_type,
        form_types: list[str] | None = None,
    ) -> list[dict]:
        """List SEC filings for one SEC filingDate via the SEC client."""
        return await self._sec.list_daily_filings(
            filing_date,
            form_types=form_types,
        )

    async def update_from_sec_records(
        self,
        company_id: str,
        records: list[dict],
    ) -> int:
        """Register already-fetched SEC filing records for a company."""
        async def _fetch_prefetched(_: str) -> list[dict]:
            return records

        adapter = FilingSourceAdapter(
            source=FilingSource.SEC,
            fetch=_fetch_prefetched,
            key_field="accessionNumber",
            find_existing=self._repo.find_existing_accessions,
            map_record=_map_sec_record,
        )
        return await self._sync(adapter, company_id, company_id)
```

- [ ] **Step 4: Run FilingSync tests**

Run:

```bash
uv run pytest tests/unit/services/test_filing_sync.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/filing_sync.py tests/unit/services/test_filing_sync.py
git commit -m "feat(filings): sync prefetched SEC daily records"
```

## Task 4: Filing-Driven US Daily Job

**Files:**
- Modify: `tests/unit/services/test_job_service.py`
- Modify: `src/stock_analyze_system/services/job.py`

- [ ] **Step 1: Add failing US filing-driven daily job tests**

In `tests/unit/services/test_job_service.py`, change:

```python
from datetime import date
```

to:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo
```

Add this import near the other `stock_analyze_system` imports:

```python
from stock_analyze_system.services import job as job_module
```

Add these tests inside `TestRunDailyUpdate`:

```python
    def test_default_sec_filing_date_uses_new_york(self, monkeypatch):
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                utc_now = datetime(2026, 4, 28, 1, 30, tzinfo=ZoneInfo("UTC"))
                if tz is None:
                    return utc_now.replace(tzinfo=None)
                return utc_now.astimezone(tz)

        monkeypatch.setattr(job_module, "datetime", FrozenDateTime)

        assert job_module._default_sec_filing_date() == date(2026, 4, 27)

    async def test_us_daily_update_uses_sec_daily_filings_not_sync_company(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0000320193",
                "form": "10-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000320193-26-000001",
                "reportDate": "",
            },
        ]
        filing_sync.update_from_sec_records.return_value = 1

        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 4

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )
        svc.sync_company = AsyncMock(side_effect=AssertionError("sync_company must not be called"))

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.total_companies == 1
        assert len(result.results) == 1
        assert result.results[0].company_id == "US_AAPL"
        assert result.results[0].filings_count == 1
        assert result.results[0].financials_count == 4
        filing_sync.list_daily_sec_filings.assert_awaited_once_with(
            date(2026, 4, 28),
            form_types=["10-K", "10-Q", "20-F", "40-F", "8-K", "6-K"],
        )
        filing_sync.update_from_sec_records.assert_awaited_once()
        financial_sync.update_from_sec.assert_awaited_once()
        svc.sync_company.assert_not_awaited()

    async def test_us_daily_update_skips_unknown_cik(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="0000320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0009999999",
                "form": "10-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0009999999-26-000001",
            },
        ]

        svc = self._make_job_svc(company_svc=company_svc, filing_sync=filing_sync)
        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.total_companies == 1
        assert result.results == []
        filing_sync.update_from_sec_records.assert_not_called()

    async def test_us_daily_update_8k_registers_without_financial_refresh(self):
        msft = MagicMock(
            id="US_MSFT",
            cik="789019",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="MSFT",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [msft]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0000789019",
                "form": "8-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000789019-26-000002",
            },
        ]
        filing_sync.update_from_sec_records.return_value = 1
        financial_sync = AsyncMock()

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.results[0].filings_count == 1
        assert result.results[0].financials_count == 0
        financial_sync.update_from_sec.assert_not_called()

    async def test_us_daily_update_refreshes_financials_once_per_company(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="0000320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0000320193",
                "form": "10-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000320193-26-000001",
            },
            {
                "cik": "0000320193",
                "form": "10-Q",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000320193-26-000002",
            },
        ]
        filing_sync.update_from_sec_records.return_value = 2
        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 8

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.results[0].filings_count == 2
        assert result.results[0].financials_count == 8
        financial_sync.update_from_sec.assert_awaited_once()

    async def test_jp_daily_update_keeps_existing_sync_company_path(self):
        jp_co = MagicMock(
            id="JP_7203",
            cik=None,
            edinet_code="E02144",
            accounting_standard="JP-GAAP",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [jp_co]
        svc = self._make_job_svc(company_svc=company_svc)
        svc.sync_company = AsyncMock(return_value=SyncResult(company_id="JP_7203", filings_count=1))

        result = await svc.run_daily_update(market="jp", target_date=date(2026, 4, 28))

        assert result.total_companies == 1
        assert result.results[0].company_id == "JP_7203"
        svc.sync_company.assert_awaited_once_with("JP_7203")
```

- [ ] **Step 2: Run the new failing tests**

Run:

```bash
uv run pytest tests/unit/services/test_job_service.py::TestRunDailyUpdate -q
```

Expected: FAIL because `run_daily_update()` does not accept `target_date` and still calls `sync_company()` for US.

- [ ] **Step 3: Implement helper constants and date helpers**

In `src/stock_analyze_system/services/job.py`, change the imports:

```python
from datetime import date as date_type
from datetime import datetime, timezone
```

to:

```python
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
```

Add these constants below the logger:

```python
_SEC_FILING_TZ = ZoneInfo("America/New_York")
_US_DAILY_FILING_FORMS = ["10-K", "10-Q", "20-F", "40-F", "8-K", "6-K"]
_US_FINANCIAL_TRIGGER_FORMS = frozenset({"10-K", "10-Q", "20-F", "40-F"})
```

Add these helpers before `class JobService`:

```python
def _default_sec_filing_date() -> date_type:
    """Return today's date in SEC filing-date timezone."""
    return datetime.now(_SEC_FILING_TZ).date()


def _normalize_cik(cik: str | None) -> str | None:
    """Normalize a company/feed CIK to 10 digits."""
    if not cik:
        return None
    try:
        return str(int(cik)).zfill(10)
    except ValueError:
        return None
```

- [ ] **Step 4: Extract valuation update helper**

In `src/stock_analyze_system/services/job.py`, add this method to `JobService` before `sync_company()`:

```python
    async def _update_valuation_for_company(
        self,
        company,
        result: SyncResult,
    ) -> None:
        """Update valuation from Yahoo Finance for a single company."""
        yf_ticker = self._company_svc.resolve_yf_ticker(company)
        if not yf_ticker:
            return
        try:
            price_data = await self._yahoo.get_stock_price(yf_ticker)
            if not price_data:
                return
            currency = price_data.get("currency", "USD")
            stock_price = price_data.get("price")
            market_cap_val = price_data.get("market_cap")

            latest_fd = await self._financial_svc.get_latest(
                result.company_id,
                PeriodType.ANNUAL,
            )
            if latest_fd:
                val_data = compute_valuation_from_financials(
                    stock_price,
                    latest_fd,
                    currency,
                    date_type.today(),
                    market_cap=market_cap_val,
                )
            else:
                val_data = {
                    "currency": currency,
                    "date": date_type.today(),
                    "stock_price": stock_price,
                    "market_cap": market_cap_val,
                }

            await self._valuation_svc.upsert_valuation(
                result.company_id,
                val_data,
            )
            result.valuations_count += 1
        except (ValueError, TypeError, AttributeError) as exc:
            result.errors.append(f"Valuation error: {exc}")
            logger.warning("Valuation failed for %s: %s", result.company_id, exc)
```

Then replace the whole existing `# 3. Valuation from Yahoo Finance` block in `sync_company()` with:

```python
        # 3. Valuation from Yahoo Finance
        await self._update_valuation_for_company(company, result)
```

- [ ] **Step 5: Add US filing-driven daily method**

In `src/stock_analyze_system/services/job.py`, add this method to `JobService` before `run_daily_update()`:

```python
    async def _run_us_daily_filing_update(
        self,
        target_date: date_type,
    ) -> DailyUpdateResult:
        """Run US daily update from SEC filings for one filingDate."""
        result = DailyUpdateResult(market="us")
        companies = await self._company_svc.list_companies()
        companies = [c for c in companies if c.id.startswith("US_")]
        result.total_companies = len(companies)

        companies_by_cik: dict[str, list[object]] = defaultdict(list)
        for company in companies:
            normalized_cik = _normalize_cik(company.cik)
            if normalized_cik is not None:
                companies_by_cik[normalized_cik].append(company)

        try:
            daily_filings = await self._filing_sync.list_daily_sec_filings(
                target_date,
                form_types=_US_DAILY_FILING_FORMS,
            )
        except (ValueError, TypeError, AttributeError, OSError) as exc:
            logger.exception("SEC daily filing fetch failed for %s", target_date)
            sr = SyncResult(company_id="SEC_EDGAR")
            sr.errors.append(str(exc))
            result.results.append(sr)
            result.finished_at = datetime.now(timezone.utc)
            return result

        filings_by_company_id: dict[str, list[dict]] = defaultdict(list)
        company_by_id: dict[str, object] = {}
        unknown_cik_count = 0
        for filing in daily_filings:
            normalized_cik = _normalize_cik(filing.get("cik"))
            if normalized_cik is None or normalized_cik not in companies_by_cik:
                unknown_cik_count += 1
                continue
            for company in companies_by_cik[normalized_cik]:
                filings_by_company_id[company.id].append(filing)
                company_by_id[company.id] = company

        logger.info(
            "SEC daily filings target_date=%s feed_rows=%d matched_companies=%d unknown_ciks=%d",
            target_date,
            len(daily_filings),
            len(filings_by_company_id),
            unknown_cik_count,
        )

        for company_id in sorted(filings_by_company_id):
            company = company_by_id[company_id]
            filings = filings_by_company_id[company_id]
            sr = SyncResult(company_id=company_id)
            try:
                sr.filings_count = await self._filing_sync.update_from_sec_records(
                    company_id,
                    filings,
                )
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                logger.exception("SEC daily filing registration failed for %s", company_id)
                sr.errors.append(f"Filing error: {exc}")

            if any(f.get("form") in _US_FINANCIAL_TRIGGER_FORMS for f in filings):
                try:
                    sr.financials_count = await self._financial_sync.update_from_sec(
                        company_id,
                        company.cik,
                        company.accounting_standard,
                        period_types=(PeriodType.ANNUAL, PeriodType.QUARTERLY),
                    )
                except (ValueError, TypeError, AttributeError, OSError) as exc:
                    logger.exception("SEC daily financial refresh failed for %s", company_id)
                    sr.errors.append(f"Financial error: {exc}")

            await self._update_valuation_for_company(company, sr)
            result.results.append(sr)

        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Daily SEC filing update complete: target_date=%s companies=%d",
            target_date,
            len(result.results),
        )
        return result
```

- [ ] **Step 6: Branch `run_daily_update()` by market**

Change the signature:

```python
    async def run_daily_update(self, market: str = "us") -> DailyUpdateResult:
```

to:

```python
    async def run_daily_update(
        self,
        market: str = "us",
        target_date: date_type | None = None,
    ) -> DailyUpdateResult:
```

At the start of `run_daily_update()`, before `result = DailyUpdateResult(market=market)`, add:

```python
        if market.lower() == "us":
            return await self._run_us_daily_filing_update(
                target_date or _default_sec_filing_date(),
            )
```

In the remaining JP/current path, keep:

```python
        result = DailyUpdateResult(market=market)
```

and leave the existing loop unchanged.

- [ ] **Step 7: Run job service tests**

Run:

```bash
uv run pytest tests/unit/services/test_job_service.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/stock_analyze_system/services/job.py tests/unit/services/test_job_service.py
git commit -m "feat(jobs): drive US daily updates from SEC filings"
```

## Task 5: CLI Filing Date Argument

**Files:**
- Modify: `tests/unit/cli/test_jobs_cli.py`
- Modify: `src/stock_analyze_system/cli/jobs.py`

- [ ] **Step 1: Add failing CLI tests**

In `tests/unit/cli/test_jobs_cli.py`, add this import:

```python
from datetime import date
```

In `TestBug3NoTypeOption`, add:

```python
    def test_daily_accepts_filing_date(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args([
            "jobs",
            "daily",
            "--market",
            "us",
            "--filing-date",
            "2026-04-28",
        ])
        assert args.action == "daily"
        assert args.market == "us"
        assert args.filing_date == date(2026, 4, 28)

    def test_daily_rejects_invalid_filing_date(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        with pytest.raises(SystemExit):
            parser.parse_args(["jobs", "daily", "--filing-date", "20260428"])
```

In `TestJobsDaily`, add:

```python
    async def test_daily_passes_filing_date(self, capsys):
        svc = _make_services()
        result = DailyUpdateResult(market="us", total_companies=1)
        result.results = [SyncResult(company_id="US_AAPL", filings_count=1)]
        svc.job_service.run_daily_update.return_value = result

        args = argparse.Namespace(
            action="daily",
            json=False,
            market="us",
            filing_date=date(2026, 4, 28),
        )

        await handle(args, svc)

        svc.job_service.run_daily_update.assert_awaited_once_with(
            market="us",
            target_date=date(2026, 4, 28),
        )
        assert "Daily update complete" in capsys.readouterr().out
```

- [ ] **Step 2: Run the new failing CLI tests**

Run:

```bash
uv run pytest tests/unit/cli/test_jobs_cli.py -q
```

Expected: FAIL because `--filing-date` is not registered and `_handle_daily()` does not pass `target_date`.

- [ ] **Step 3: Implement CLI parser and handler changes**

In `src/stock_analyze_system/cli/jobs.py`, add these imports:

```python
from datetime import date as date_type
```

Add this helper before `register_parser()`:

```python
def _parse_filing_date(value: str) -> date_type:
    """Parse --filing-date as YYYY-MM-DD."""
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--filing-date must be in YYYY-MM-DD format"
        ) from exc
```

After the existing `daily_p.add_argument("--market", ...)`, add:

```python
    daily_p.add_argument(
        "--filing-date",
        type=_parse_filing_date,
        default=None,
        help="SEC filingDate to process (YYYY-MM-DD); defaults to current SEC date",
    )
```

Change `_handle_daily()` from:

```python
    result = await services.job_service.run_daily_update(market=args.market)
```

to:

```python
    result = await services.job_service.run_daily_update(
        market=args.market,
        target_date=getattr(args, "filing_date", None),
    )
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
uv run pytest tests/unit/cli/test_jobs_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/cli/jobs.py tests/unit/cli/test_jobs_cli.py
git commit -m "feat(cli): add SEC filing date for daily jobs"
```

## Task 6: Integration Verification And Regression Sweep

**Files:**
- No source edits expected unless tests expose a real issue.

- [ ] **Step 1: Run focused test set**

Run:

```bash
uv run pytest tests/unit/ingestion/test_sec_edgar.py tests/unit/services/test_filing_sync.py tests/unit/services/test_job_service.py tests/unit/cli/test_jobs_cli.py tests/unit/test_config.py tests/unit/characterization/test_container_assembly.py tests/unit/web/test_dependencies.py -q
```

Expected: PASS.

- [ ] **Step 2: Run lint**

Run:

```bash
uv run ruff check src/stock_analyze_system/ingestion/sec_edgar.py src/stock_analyze_system/services/filing_sync.py src/stock_analyze_system/services/job.py src/stock_analyze_system/cli/jobs.py src/stock_analyze_system/config.py src/stock_analyze_system/cli/container.py src/stock_analyze_system/web/dependencies.py tests/unit/ingestion/test_sec_edgar.py tests/unit/services/test_filing_sync.py tests/unit/services/test_job_service.py tests/unit/cli/test_jobs_cli.py tests/unit/test_config.py tests/unit/characterization/test_container_assembly.py tests/unit/web/test_dependencies.py
```

Expected: PASS.

- [ ] **Step 3: Run full unit suite**

Run:

```bash
uv run pytest tests/unit -q
```

Expected: PASS.

- [ ] **Step 4: Inspect staged and unstaged changes**

Run:

```bash
git status --short
```

Expected: only intentional files from this plan are changed, plus pre-existing unrelated dirty files that should not be reverted.

- [ ] **Step 5: Commit verification fixes if needed**

If Step 1-3 required small fixes, first run:

```bash
git status --short
```

Then stage only the explicitly listed source or test files changed by those
verification fixes. Use paths from the `git status --short` output, not a broad
directory add. Commit them with:

```bash
git commit -m "test: verify SEC daily filing update"
```

If no fixes were needed after Task 5, do not create an empty commit.
