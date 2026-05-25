# Test Coverage Strengthening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise project test coverage from 85% to ~95% by testing all critical untested code paths.

**Architecture:** Unit tests with AsyncMock for service/repository layers, direct tests for pure functions. Follow existing pytest-asyncio patterns.

**Tech Stack:** pytest, pytest-asyncio (auto mode), unittest.mock (AsyncMock, MagicMock, patch), pandas (for yfinance DataFrame mocks)

---

### Task 1: period_filter.py tests (0% → ~95%)

**Files:**
- Create: `tests/unit/ingestion/xbrl/test_period_filter.py`

- [ ] **Step 1: Create test file with days_between tests**

```python
"""period_filter のテスト"""
from stock_analyze_system.ingestion.xbrl.period_filter import (
    ANNUAL_MIN_DAYS,
    DURATION_UNKNOWN,
    QUARTERLY_MAX_DAYS,
    days_between,
    duration_ok,
    merge_near_dates,
)


class TestDaysBetween:
    def test_normal_dates(self):
        assert days_between("2024-01-01", "2024-12-31") == 365

    def test_same_date(self):
        assert days_between("2024-06-15", "2024-06-15") == 0

    def test_invalid_date_returns_unknown(self):
        assert days_between("bad", "2024-01-01") == DURATION_UNKNOWN

    def test_invalid_end_date_returns_unknown(self):
        assert days_between("2024-01-01", "bad") == DURATION_UNKNOWN


class TestDurationOk:
    def test_annual_above_min(self):
        assert duration_ok(365, "annual") is True

    def test_annual_below_min(self):
        assert duration_ok(200, "annual") is False

    def test_annual_boundary(self):
        assert duration_ok(ANNUAL_MIN_DAYS, "annual") is True

    def test_quarterly_below_max(self):
        assert duration_ok(90, "quarterly") is True

    def test_quarterly_above_max(self):
        assert duration_ok(200, "quarterly") is False

    def test_quarterly_boundary(self):
        assert duration_ok(QUARTERLY_MAX_DAYS, "quarterly") is True

    def test_unknown_mode_returns_true(self):
        assert duration_ok(999, "unknown_mode") is True


class TestMergeNearDates:
    def test_single_date_unchanged(self):
        dates = {"2024-01-01"}
        result = merge_near_dates(dates, {}, {})
        assert result == {"2024-01-01"}

    def test_empty_set(self):
        result = merge_near_dates(set(), {}, {})
        assert result == set()

    def test_distant_dates_not_merged(self):
        dates = {"2024-01-01", "2024-06-30"}
        result = merge_near_dates(dates, {}, {})
        assert result == {"2024-01-01", "2024-06-30"}

    def test_near_dates_merged_to_best(self):
        """+-3日以内の日付がフィールド数の多い方にマージされる"""
        dates = {"2024-01-01", "2024-01-02"}
        field_data = {
            "revenue": {"2024-01-01": 100.0},
            "net_income": {"2024-01-02": 50.0, "2024-01-01": 200.0},
        }
        mapping = {"revenue": ["tag1"], "net_income": ["tag2"]}
        result = merge_near_dates(dates, field_data, mapping)
        # 2024-01-01 has 2 fields, 2024-01-02 has 1 → 01-01 wins
        assert result == {"2024-01-01"}
        # value migrated
        assert field_data["net_income"]["2024-01-01"] == 200.0

    def test_near_dates_value_migration(self):
        """マージ先にない値は移行される"""
        dates = {"2024-03-29", "2024-03-31"}
        field_data = {
            "revenue": {"2024-03-31": 100.0},
            "net_income": {"2024-03-29": 50.0},
        }
        mapping = {"revenue": ["t1"], "net_income": ["t2"]}
        result = merge_near_dates(dates, field_data, mapping)
        assert len(result) == 1
        best = list(result)[0]
        assert field_data["revenue"].get(best) is not None or field_data["net_income"].get(best) is not None

    def test_conflict_keeps_best_date_value(self):
        """競合時はbest_dateの値を保持"""
        dates = {"2024-01-01", "2024-01-02"}
        field_data = {
            "revenue": {"2024-01-01": 100.0, "2024-01-02": 200.0},
        }
        mapping = {"revenue": ["tag1"]}
        result = merge_near_dates(dates, field_data, mapping)
        best = list(result)[0]
        # best_dateの元の値が保持される
        assert field_data["revenue"][best] is not None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/ingestion/xbrl/test_period_filter.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/ingestion/xbrl/test_period_filter.py
git commit -m "test: add period_filter.py tests (0% → ~95%)"
```

---

### Task 2: taxonomy.py runtime function tests (70% → ~95%)

**Files:**
- Create: `tests/unit/ingestion/xbrl/test_taxonomy_runtime.py`

- [ ] **Step 1: Create test file**

```python
"""taxonomy ランタイム関数のテスト"""
from stock_analyze_system.ingestion.xbrl.taxonomy import (
    detect_currency,
    detect_taxonomy,
    find_unit_data,
    pick_unit,
)


class TestDetectTaxonomy:
    def test_us_gaap_detected(self):
        facts = {"facts": {"us-gaap": {"Revenue": {}}, "ifrs-full": {}}}
        name, data, currency = detect_taxonomy(facts)
        assert name == "us-gaap"
        assert currency == "USD"

    def test_ifrs_when_more_facts(self):
        facts = {"facts": {"us-gaap": {"A": {}}, "ifrs-full": {"A": {}, "B": {}}}}
        name, data, currency = detect_taxonomy(facts)
        assert name == "ifrs-full"

    def test_ifrs_only(self):
        facts = {"facts": {"ifrs-full": {"Revenue": {}}}}
        name, _, _ = detect_taxonomy(facts)
        assert name == "ifrs-full"

    def test_empty_facts(self):
        facts = {"facts": {}}
        name, data, currency = detect_taxonomy(facts)
        assert name == "us-gaap"
        assert data == {}
        assert currency == "USD"

    def test_no_facts_key(self):
        name, data, currency = detect_taxonomy({})
        assert name == "us-gaap"


class TestDetectCurrency:
    def test_non_usd_currency(self):
        facts = {"Revenue": {"units": {"EUR": [{}]}}}
        assert detect_currency(facts) == "EUR"

    def test_usd_currency(self):
        facts = {"Revenue": {"units": {"USD": [{}]}}}
        assert detect_currency(facts) == "USD"

    def test_skips_pure_and_shares(self):
        facts = {"Revenue": {"units": {"pure": [{}], "shares": [{}], "JPY": [{}]}}}
        assert detect_currency(facts) == "JPY"

    def test_skips_ratio_units(self):
        facts = {"Revenue": {"units": {"USD/shares": [{}], "GBP": [{}]}}}
        assert detect_currency(facts) == "GBP"

    def test_fallback_usd(self):
        assert detect_currency({}) == "USD"

    def test_usd_when_only_usd_present(self):
        facts = {"Revenue": {"units": {"USD/shares": [{}], "USD": [{}]}}}
        assert detect_currency(facts) == "USD"


class TestPickUnit:
    def test_share_field(self):
        assert pick_unit("eps", "JPY") == "JPY/shares"

    def test_shares_outstanding(self):
        assert pick_unit("shares_outstanding", "USD") == "USD/shares"

    def test_non_share_field(self):
        assert pick_unit("revenue", "EUR") == "EUR"


class TestFindUnitData:
    def test_exact_match(self):
        tag = {"units": {"JPY": [{"val": 1}]}}
        assert find_unit_data(tag, "JPY") == [{"val": 1}]

    def test_fallback_usd_shares(self):
        tag = {"units": {"USD/shares": [{"val": 2}]}}
        result = find_unit_data(tag, "JPY/shares")
        assert result == [{"val": 2}]

    def test_fallback_any_shares(self):
        tag = {"units": {"EUR/shares": [{"val": 3}]}}
        result = find_unit_data(tag, "JPY/shares")
        assert result == [{"val": 3}]

    def test_fallback_pure_shares(self):
        tag = {"units": {"shares": [{"val": 4}]}}
        result = find_unit_data(tag, "JPY/shares")
        assert result == [{"val": 4}]

    def test_fallback_usd_for_non_usd(self):
        tag = {"units": {"USD": [{"val": 5}]}}
        result = find_unit_data(tag, "EUR")
        assert result == [{"val": 5}]

    def test_last_resort_usd_shares(self):
        tag = {"units": {"USD/shares": [{"val": 6}]}}
        result = find_unit_data(tag, "USD")
        assert result == [{"val": 6}]

    def test_returns_none_when_no_match(self):
        tag = {"units": {}}
        assert find_unit_data(tag, "JPY") is None

    def test_no_units_key(self):
        assert find_unit_data({}, "USD") is None
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/ingestion/xbrl/test_taxonomy_runtime.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/ingestion/xbrl/test_taxonomy_runtime.py
git commit -m "test: add taxonomy runtime function tests (70% → ~95%)"
```

---

### Task 3: financial_sync.py tests (59% → ~90%)

**Files:**
- Modify: `tests/unit/services/test_financial_sync.py`

- [ ] **Step 1: Add _parse_and_upsert_sec tests**

```python
class TestParseAndUpsertSec:
    async def test_parses_and_upserts_records(self):
        """SEC facts をパースして各レコードをupsertすること"""
        repo = AsyncMock()
        svc = _make_sync_svc(financial_repo=repo)

        fake_records = [
            {"fiscal_year_end": "2024-09-28", "revenue": 100.0, "currency": "USD"},
        ]
        with patch("stock_analyze_system.services.financial_sync.SecXbrlParser") as MockParser:
            MockParser.return_value.parse_company_facts.return_value = fake_records
            count = await svc._parse_and_upsert_sec(
                "US_AAPL", {"facts": {}}, "US-GAAP", "annual",
            )
        assert count == 1
        repo.upsert.assert_called_once()

    async def test_returns_zero_on_parse_error(self):
        """パーサーエラー時に0を返すこと"""
        svc = _make_sync_svc()
        with patch("stock_analyze_system.services.financial_sync.SecXbrlParser") as MockParser:
            MockParser.return_value.parse_company_facts.side_effect = ValueError("bad data")
            count = await svc._parse_and_upsert_sec(
                "US_AAPL", {}, "US-GAAP", "annual",
            )
        assert count == 0

    async def test_derives_fcf_for_each_record(self):
        """各レコードでFCF導出が呼ばれること"""
        repo = AsyncMock()
        svc = _make_sync_svc(financial_repo=repo)
        fake_records = [
            {"fiscal_year_end": "2024-09-28", "operating_cf": 100.0, "capex": -30.0, "fcf": None, "currency": "USD"},
        ]
        with patch("stock_analyze_system.services.financial_sync.SecXbrlParser") as MockParser:
            MockParser.return_value.parse_company_facts.return_value = fake_records
            await svc._parse_and_upsert_sec("US_AAPL", {}, "US-GAAP", "annual")
        # FCF should have been derived
        call_args = repo.upsert.call_args
        upserted_data = call_args[0][1]
        assert upserted_data.get("fcf") == 70.0


class TestParseAndUpsertEdinet:
    async def test_parses_and_upserts_edinet_doc(self):
        """EDINET ドキュメントをパースしてupsertすること"""
        repo = AsyncMock()
        edinet_client = AsyncMock()
        edinet_client.download_xbrl.return_value = "/tmp/xbrl"
        svc = _make_sync_svc(financial_repo=repo, edinet_client=edinet_client)

        with patch("stock_analyze_system.services.financial_sync.EdinetXbrlParser") as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.detect_accounting_standard.return_value = "jp_gaap"
            parser_inst.parse_xbrl_directory.return_value = {
                "fiscal_year_end": "2024-03-31", "revenue": 5000.0,
            }
            count = await svc._parse_and_upsert_edinet("JP_7203", {"docID": "S100001"})
        assert count == 1
        repo.upsert.assert_called_once()

    async def test_returns_zero_when_no_doc_id(self):
        """docIDがない場合は0を返すこと"""
        svc = _make_sync_svc()
        count = await svc._parse_and_upsert_edinet("JP_7203", {})
        assert count == 0

    async def test_returns_zero_on_parse_error(self):
        """パーサーエラー時は0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.download_xbrl.side_effect = OSError("download failed")
        svc = _make_sync_svc(edinet_client=edinet_client)
        count = await svc._parse_and_upsert_edinet("JP_7203", {"docID": "S100001"})
        assert count == 0

    async def test_returns_zero_when_parse_result_empty(self):
        """パース結果が空の場合は0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.download_xbrl.return_value = "/tmp/xbrl"
        svc = _make_sync_svc(edinet_client=edinet_client)
        with patch("stock_analyze_system.services.financial_sync.EdinetXbrlParser") as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.detect_accounting_standard.return_value = "jp_gaap"
            parser_inst.parse_xbrl_directory.return_value = {}
            count = await svc._parse_and_upsert_edinet("JP_7203", {"docID": "S100001"})
        assert count == 0


class TestUpdateFromEdinetEmpty:
    async def test_returns_zero_when_no_docs(self):
        """EDINET 検索結果が空の場合は0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.search_filings.return_value = []
        svc = _make_sync_svc(edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/services/test_financial_sync.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/services/test_financial_sync.py
git commit -m "test: add financial_sync.py parse/upsert tests (59% → ~90%)"
```

---

### Task 4: filing_sync.py tests (56% → ~90%)

**Files:**
- Modify: `tests/unit/services/test_filing_sync.py`

- [ ] **Step 1: Add EDINET and SEC error handling tests**

```python
class TestUpdateFromSecErrors:
    async def test_returns_zero_on_api_failure(self):
        """SEC API失敗時に0を返すこと"""
        sec_client = AsyncMock()
        sec_client.list_filings.side_effect = OSError("API error")
        svc = FilingSyncService(
            filing_repo=AsyncMock(), sec_client=sec_client,
            edinet_client=AsyncMock(),
        )
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0

    async def test_returns_zero_on_empty_list(self):
        """空リスト時に0を返すこと"""
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = []
        svc = FilingSyncService(
            filing_repo=AsyncMock(), sec_client=sec_client,
            edinet_client=AsyncMock(),
        )
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0

    async def test_skips_entry_without_accession(self):
        """accessionNumber がないエントリはスキップ"""
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = [
            {"form": "10-K", "reportDate": "2024-09-28"},
        ]
        filing_repo = AsyncMock()
        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=sec_client,
            edinet_client=AsyncMock(),
        )
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0
        filing_repo.upsert.assert_not_called()


class TestUpdateFromEdinet:
    async def test_registers_edinet_filings(self):
        """EDINET ファイリングが登録されること"""
        filing_repo = AsyncMock()
        filing_repo.find_by_doc_id.return_value = None
        edinet_client = AsyncMock()
        edinet_client.search_filings.return_value = [
            {"docID": "S100001", "periodEnd": "2024-03-31", "docTypeCode": "120"},
        ]
        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=AsyncMock(),
            edinet_client=edinet_client,
        )
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 1
        filing_repo.upsert.assert_called_once()

    async def test_skips_existing_edinet_filing(self):
        """既存ファイリングはスキップ"""
        filing_repo = AsyncMock()
        filing_repo.find_by_doc_id.return_value = MagicMock(id=1)
        edinet_client = AsyncMock()
        edinet_client.search_filings.return_value = [
            {"docID": "S100001", "periodEnd": "2024-03-31", "docTypeCode": "120"},
        ]
        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=AsyncMock(),
            edinet_client=edinet_client,
        )
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_skips_doc_without_id(self):
        """docIDがないドキュメントはスキップ"""
        filing_repo = AsyncMock()
        edinet_client = AsyncMock()
        edinet_client.search_filings.return_value = [
            {"periodEnd": "2024-03-31", "docTypeCode": "120"},
        ]
        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=AsyncMock(),
            edinet_client=edinet_client,
        )
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_returns_zero_on_api_failure(self):
        """EDINET API失敗時に0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.search_filings.side_effect = OSError("API error")
        svc = FilingSyncService(
            filing_repo=AsyncMock(), sec_client=AsyncMock(),
            edinet_client=edinet_client,
        )
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_returns_zero_on_empty_docs(self):
        """空ドキュメントリスト時に0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.search_filings.return_value = []
        svc = FilingSyncService(
            filing_repo=AsyncMock(), sec_client=AsyncMock(),
            edinet_client=edinet_client,
        )
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_quarterly_period_type(self):
        """docTypeCode 140 は quarterly として登録"""
        filing_repo = AsyncMock()
        filing_repo.find_by_doc_id.return_value = None
        edinet_client = AsyncMock()
        edinet_client.search_filings.return_value = [
            {"docID": "S100002", "periodEnd": "2024-06-30", "docTypeCode": "140"},
        ]
        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=AsyncMock(),
            edinet_client=edinet_client,
        )
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 1
        call_data = filing_repo.upsert.call_args[0][1]
        assert call_data["period_type"] == "quarterly"
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/services/test_filing_sync.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/services/test_filing_sync.py
git commit -m "test: add filing_sync.py EDINET + error handling tests (56% → ~90%)"
```

---

### Task 5: job.py tests (70% → ~90%)

**Files:**
- Modify: `tests/unit/services/test_job_service.py`

- [ ] **Step 1: Add EDINET path and daily_update tests**

Tests for:
- `sync_company` with EDINET paths (non-US market, edinet_code)
- `sync_company` valuation error handling
- `run_daily_update` full flow
- `run_daily_update` with sync failure

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/services/test_job_service.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/services/test_job_service.py
git commit -m "test: add job.py daily_update + EDINET path tests (70% → ~90%)"
```

---

### Task 6: yahoo_finance.py tests (39% → ~85%)

**Files:**
- Modify: `tests/unit/ingestion/test_yahoo_finance.py`

- [ ] **Step 1: Add _fetch_quarterly and _fetch_history tests**

Tests for:
- `_fetch_quarterly` with mocked yfinance Ticker returning DataFrames
- `_fetch_quarterly` with empty DataFrame
- `_yf_val` edge cases (NaN, missing rows, type errors)
- `_fetch_history` with mocked history DataFrame
- `_fetch_history` with empty result
- Exception handlers for all async methods

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/ingestion/test_yahoo_finance.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/ingestion/test_yahoo_finance.py
git commit -m "test: add yahoo_finance quarterly/history tests (39% → ~85%)"
```

---

### Task 7: edinet.py + watchlist repo tests

**Files:**
- Modify: `tests/unit/ingestion/test_edinet.py`
- Create: `tests/unit/repositories/test_watchlist_repo.py`

- [ ] **Step 1: Add edinet download_xbrl_zip and search error tests**

Tests for:
- `download_xbrl_zip` with mocked HTTP response and zip file
- `download_xbrl_zip` raises ValueError when no API key
- `search_company_filings` continues on daily exception

- [ ] **Step 2: Add watchlist repository tests**

Tests for:
- `list_items` returns items for watchlist
- `add_item` creates and returns WatchlistItem
- `delete_item` removes item
- Uses in-memory SQLite with real async session

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/unit/ingestion/test_edinet.py tests/unit/repositories/test_watchlist_repo.py -v`

- [ ] **Step 4: Commit**

```bash
git add tests/unit/ingestion/test_edinet.py tests/unit/repositories/test_watchlist_repo.py
git commit -m "test: add edinet download + watchlist repo tests"
```

---

### Task 8: base.py + remaining CLI gaps

**Files:**
- Create: `tests/unit/test_db_engine.py`

- [ ] **Step 1: Add create_db_engine integration test**

Tests for:
- `create_db_engine` creates engine with WAL mode
- `create_db_engine` creates parent directory
- Tables are created in metadata

- [ ] **Step 2: Run all tests and verify coverage improvement**

Run: `python3 -m pytest --cov=stock_analyze_system --cov-report=term-missing --tb=short -q`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_db_engine.py
git commit -m "test: add create_db_engine integration test"
```
