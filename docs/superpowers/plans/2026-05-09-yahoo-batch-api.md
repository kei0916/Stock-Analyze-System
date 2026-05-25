# Yahoo Finance v7 Batch API Implementation Plan (Revised v3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `ScreeningUniverseService.enrich_with_yahoo()` to use Yahoo Finance v7 batch API (1000 tickers/request) and batch DB upsert, reducing processing time from ~8 minutes to ~15 seconds for 10,376 companies.

**Architecture:** Replace individual `Ticker.info` calls with direct v7 `/finance/quote` batch HTTP requests via `yfinance.data.YfData`, accumulating results in memory and persisting via a new `bulk_upsert_cache` repository method that preserves existing column values not present in the payload. Keep existing `get_screening_info()` for backward compatibility.

**Tech Stack:** Python 3.12, yfinance, SQLAlchemy AsyncSession, AsyncRateLimiter

**Scope:** Step 1 only — Yahoo v7 batch fetch + batch upsert with existing-value preservation. Sector/industry/beta/roe/operating_margin/net_margin/revenue_growth/earnings_growth/peg_ratio/fcf_yield/de_ratio from Yahoo are **out of scope** for this plan; they remain available via the existing `refresh_from_sec_google()` flow or will be addressed in a future financial_data integration plan.

---

## ADR Check

This plan introduces a new pattern (batch HTTP API + batch DB write) that replaces the existing individual-call pattern. A **Light ADR** is required.

**ADR Status:** `docs/adr/003-yahoo-batch-api.md` must be created before implementation begins. (002 is already used by `002-filing-content-auto-recovery.md`)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/stock_analyze_system/ingestion/yahoo_finance.py` | Modify | Add `get_screening_info_batch()`; keep `get_screening_info()` |
| `src/stock_analyze_system/repositories/screening.py` | Modify | Add `bulk_upsert_cache()` — groups rows by key set, issues separate INSERT per group to prevent NULL overwrite |
| `src/stock_analyze_system/services/screening_universe.py` | Modify | Refactor `enrich_with_yahoo()` to batch API + batch save; fallback to individual upsert on batch DB failure |
| `tests/unit/ingestion/test_yahoo_finance.py` | Modify | Add tests for batch API method |
| `tests/unit/repositories/test_screening_repo.py` | Create | Add tests for `bulk_upsert_cache` including mixed key shapes |
| `tests/unit/services/test_screening_universe_service.py` | Modify | Replace `get_screening_info` mocks with `get_screening_info_batch`; update assertions for batch behavior |

---

## Task 1: Add `get_screening_info_batch()` to YahooFinanceClient

**Files:**
- Modify: `src/stock_analyze_system/ingestion/yahoo_finance.py`
- Test: `tests/unit/ingestion/test_yahoo_finance.py`

**Rationale:** The core batch API wrapper. Uses `yfinance.data.YfData` directly to call `/v7/finance/quote` with up to 1000 symbols per request. Failed tickers within a batch are silently skipped; the caller receives only successful results.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import patch, MagicMock

from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient


@pytest.mark.asyncio
async def test_get_screening_info_batch_success():
    """1000銘柄のバッチリクエストが成功し、正しい辞書リストを返す"""
    client = YahooFinanceClient(rate=1000.0)

    mock_response = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "AAPL",
                    "regularMarketPrice": 150.0,
                    "marketCap": 2000000000000,
                    "trailingPE": 25.0,
                    "forwardPE": 22.0,
                    "priceToBook": 30.0,
                    "dividendYield": 0.005,
                    "exchange": "NMS",
                    "fiftyTwoWeekHigh": 180.0,
                    "fiftyTwoWeekLow": 120.0,
                    "averageVolume": 50000000,
                    "trailingEps": 6.0,
                },
                {
                    "symbol": "MSFT",
                    "regularMarketPrice": 300.0,
                    "marketCap": 2500000000000,
                    "trailingPE": 30.0,
                },
            ],
            "error": None,
        }
    }

    with patch("stock_analyze_system.ingestion.yahoo_finance.YfData") as MockYfData:
        mock_data = MagicMock()
        mock_data.get_raw_json.return_value = mock_response
        MockYfData.return_value = mock_data

        result = await client.get_screening_info_batch(["AAPL", "MSFT"])

        assert len(result) == 2
        assert result["AAPL"]["stock_price"] == 150.0
        assert result["AAPL"]["market_cap"] == 2000000000000
        assert result["AAPL"]["trailing_per"] == 25.0
        assert result["AAPL"]["forward_per"] == 22.0
        assert result["AAPL"]["pbr"] == 30.0
        assert result["AAPL"]["dividend_yield"] == 0.005
        assert result["AAPL"]["exchange"] == "NMS"
        assert result["AAPL"]["fifty_two_week_high"] == 180.0
        assert result["AAPL"]["fifty_two_week_low"] == 120.0
        assert result["AAPL"]["volume"] == 50000000
        assert result["AAPL"]["eps"] == 6.0
        assert result["MSFT"]["stock_price"] == 300.0

        # Verify batch API was called with comma-separated symbols
        mock_data.get_raw_json.assert_called_once()
        call_args = mock_data.get_raw_json.call_args
        assert call_args.kwargs["params"]["symbols"] == "AAPL,MSFT"


@pytest.mark.asyncio
async def test_get_screening_info_batch_partial_failure():
    """一部銘柄が失敗しても成功銘柄は返す"""
    client = YahooFinanceClient(rate=1000.0)

    mock_response = {
        "quoteResponse": {
            "result": [
                {"symbol": "AAPL", "regularMarketPrice": 150.0},
            ],
            "error": [{"code": "Not Found", "symbol": "INVALID"}],
        }
    }

    with patch("stock_analyze_system.ingestion.yahoo_finance.YfData") as MockYfData:
        mock_data = MagicMock()
        mock_data.get_raw_json.return_value = mock_response
        MockYfData.return_value = mock_data

        result = await client.get_screening_info_batch(["AAPL", "INVALID"])

        assert "AAPL" in result
        assert "INVALID" not in result


@pytest.mark.asyncio
async def test_get_screening_info_batch_empty():
    """空リストの場合は空辞書を返す"""
    client = YahooFinanceClient(rate=1000.0)
    result = await client.get_screening_info_batch([])
    assert result == {}


@pytest.mark.asyncio
async def test_get_screening_info_batch_api_error():
    """Yahoo API が全体エラーを返した場合は空辞書を返す"""
    client = YahooFinanceClient(rate=1000.0)

    with patch("stock_analyze_system.ingestion.yahoo_finance.YfData") as MockYfData:
        mock_data = MagicMock()
        mock_data.get_raw_json.side_effect = Exception("Connection timeout")
        MockYfData.return_value = mock_data

        result = await client.get_screening_info_batch(["AAPL"])
        assert result == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/ingestion/test_yahoo_finance.py::test_get_screening_info_batch_success -v`
Expected: FAIL with "AttributeError: 'YahooFinanceClient' object has no attribute 'get_screening_info_batch'"

- [ ] **Step 3: Write minimal implementation**

Add to `src/stock_analyze_system/ingestion/yahoo_finance.py`:

```python
from yfinance.data import YfData

# ... existing imports ...

class YahooFinanceClient:
    # ... existing __init__ and methods ...

    async def get_screening_info_batch(
        self, tickers: list[str], batch_size: int = 1000
    ) -> dict[str, dict]:
        """Yahoo Finance v7 batch API で複数銘柄の情報を一括取得.

        Args:
            tickers: ティッカーシンボルリスト.
            batch_size: 1回のリクエストに含める最大銘柄数 (default 1000).

        Returns:
            {ticker: screening_info_dict} 形式の辞書.
            取得失敗した銘柄は含まれない.
        """
        if not tickers:
            return {}

        results: dict[str, dict] = {}
        data = YfData()

        for i in range(0, len(tickers), batch_size):
            batch = tickers[i : i + batch_size]
            symbols = ",".join(batch)

            await self._rate_limiter.acquire()
            try:
                response = await asyncio.to_thread(
                    data.get_raw_json,
                    "https://query1.finance.yahoo.com/v7/finance/quote",
                    params={"symbols": symbols, "formatted": "false"},
                )
            except Exception as e:
                logger.warning(
                    "Yahoo Finance batch error for batch %d-%d: %s",
                    i, i + len(batch) - 1, e,
                )
                continue

            if not response or "quoteResponse" not in response:
                logger.warning(
                    "Yahoo Finance batch empty response for batch %d-%d",
                    i, i + len(batch) - 1,
                )
                continue

            quotes = response["quoteResponse"].get("result", [])
            for quote in quotes:
                symbol = quote.get("symbol")
                if not symbol:
                    continue

                price = quote.get("regularMarketPrice") or quote.get("currentPrice")
                if price is None:
                    continue

                info = {
                    "stock_price": price,
                    "market_cap": quote.get("marketCap"),
                    "trailing_per": quote.get("trailingPE"),
                    "forward_per": quote.get("forwardPE"),
                    "pbr": quote.get("priceToBook"),
                    "dividend_yield": quote.get("dividendYield"),
                    "exchange": quote.get("exchange"),
                    "fifty_two_week_high": quote.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": quote.get("fiftyTwoWeekLow"),
                    "volume": quote.get("averageVolume"),
                    "eps": quote.get("trailingEps"),
                }
                # Remove None values to keep payload clean
                results[symbol] = {k: v for k, v in info.items() if v is not None}

        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/ingestion/test_yahoo_finance.py -v`
Expected: All tests PASS

- [ ] **Step 5: Refactor**

Clean up:
- Extract `_parse_quote` helper to reduce method length
- Ensure logger import is correct
- Check that `asyncio` is already imported at module level

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/ingestion/yahoo_finance.py tests/unit/ingestion/test_yahoo_finance.py
git commit -m "feat(ingestion): add Yahoo Finance v7 batch API support"
```

---

## Task 2: Add `bulk_upsert_cache()` to ScreeningRepository

**Files:**
- Modify: `src/stock_analyze_system/repositories/screening.py`
- Test: `tests/unit/repositories/test_screening_repo.py` (CREATE)

**Rationale:** Enable batch persistence while **preserving existing column values** not present in the payload. Groups rows by key set and issues separate INSERT per group to prevent NULL overwrite (N1 fix).

- [ ] **Step 1: Write the failing test**

```python
import pytest
from datetime import date

from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.models.screening import ScreeningCache


@pytest.mark.asyncio
async def test_bulk_upsert_cache_insert_and_update_preserves_omitted(
    async_session,
):
    """一括upsert: payloadに存在しない列は既存値を上書きしない (C1修正)"""
    repo = ScreeningRepository(async_session)

    # Pre-insert AAPL with trailing_per and sector
    await repo.upsert_cache(
        "US_AAPL",
        {
            "stock_price": 100.0,
            "trailing_per": 20.0,
            "sector": "Technology",
            "roe": 0.15,
        },
    )
    await async_session.commit()

    # Bulk upsert: update AAPL (no trailing_per/sector/roe) + insert MSFT
    payloads = [
        ("US_AAPL", {"stock_price": 150.0, "market_cap": 2_000_000_000_000}),
        ("US_MSFT", {"stock_price": 300.0, "trailing_per": 25.0}),
    ]

    await repo.bulk_upsert_cache(payloads)
    await async_session.commit()

    # Verify AAPL: stock_price updated, trailing_per/sector/roe preserved
    aapl = await repo.get_cache("US_AAPL")
    assert aapl.stock_price == 150.0
    assert aapl.market_cap == 2_000_000_000_000
    assert aapl.trailing_per == 20.0  # MUST be preserved (not NULL)
    assert aapl.sector == "Technology"  # MUST be preserved
    assert aapl.roe == 0.15  # MUST be preserved

    # Verify MSFT inserted
    msft = await repo.get_cache("US_MSFT")
    assert msft.stock_price == 300.0
    assert msft.trailing_per == 25.0


@pytest.mark.asyncio
async def test_bulk_upsert_cache_mixed_key_shapes(async_session):
    """payloadごとにキー集合が違っても、各キーは正しい列だけ更新される (N1/Q2修正)"""
    repo = ScreeningRepository(async_session)
    await repo.upsert_cache(
        "US_AAPL", {"stock_price": 100.0, "trailing_per": 20.0}
    )
    await repo.upsert_cache(
        "US_MSFT", {"stock_price": 200.0, "market_cap": 1e12}
    )
    await async_session.commit()

    payloads = [
        ("US_AAPL", {"stock_price": 150.0}),  # only stock_price
        ("US_MSFT", {"stock_price": 300.0, "pbr": 5.0}),  # different key set
    ]
    await repo.bulk_upsert_cache(payloads)
    await async_session.commit()

    aapl = await repo.get_cache("US_AAPL")
    assert aapl.stock_price == 150.0
    assert aapl.trailing_per == 20.0  # preserved

    msft = await repo.get_cache("US_MSFT")
    assert msft.stock_price == 300.0
    assert msft.market_cap == 1e12  # preserved
    assert msft.pbr == 5.0


@pytest.mark.asyncio
async def test_bulk_upsert_cache_empty(async_session):
    """空リストの場合は何もしない"""
    repo = ScreeningRepository(async_session)
    result = await repo.bulk_upsert_cache([])
    assert result == 0


@pytest.mark.asyncio
async def test_bulk_upsert_cache_all_new(async_session):
    """全件新規insert"""
    repo = ScreeningRepository(async_session)
    payloads = [
        ("US_AAPL", {"stock_price": 100.0, "trailing_per": 20.0}),
        ("US_MSFT", {"stock_price": 200.0, "trailing_per": 25.0}),
    ]
    await repo.bulk_upsert_cache(payloads)
    await async_session.commit()

    aapl = await repo.get_cache("US_AAPL")
    assert aapl.stock_price == 100.0
    assert aapl.trailing_per == 20.0


@pytest.mark.asyncio
async def test_bulk_upsert_cache_empty_after_normalize(async_session):
    """normalize後に updatable な列がゼロになっても落ちない (N8修正)"""
    repo = ScreeningRepository(async_session)
    # unknown_column は ScreeningCache に無い → normalize で除外され key_set 空
    await repo.bulk_upsert_cache([("US_X", {"unknown_column": "foo"})])
    await async_session.commit()
    # row 自体は INSERT されない (DO NOTHING) か company_id のみ INSERT される
    # → クラッシュしないことが本テストの主目的
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/repositories/test_screening_repo.py::test_bulk_upsert_cache_insert_and_update_preserves_omitted -v`
Expected: FAIL with "AttributeError: 'ScreeningRepository' object has no attribute 'bulk_upsert_cache'"

- [ ] **Step 3: Write minimal implementation**

Add to `src/stock_analyze_system/repositories/screening.py`:

```python
from collections import defaultdict
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

# ... existing imports ...

class ScreeningRepository(BaseRepository[ScreeningCache]):
    # ... existing methods ...

    async def bulk_upsert_cache(
        self, payloads: list[tuple[str, dict]],
    ) -> int:
        """ScreeningCache を一括 upsert.

        payload に存在しない列は既存値を上書きしない。
        行ごとにキー集合が異なる場合は、キー集合ごとにグループ化して
        個別の INSERT 文を発行する (N1 対策)。

        Args:
            payloads: [(company_id, data_dict), ...] のリスト.

        Returns:
            処理したレコード数.
        """
        if not payloads:
            return 0

        # Group records by key set to avoid NULL overwrites (N1 fix)
        groups: dict[frozenset[str], list[dict]] = defaultdict(list)
        for company_id, data in payloads:
            normalized = normalize_screening_cache_payload(data)
            record = {"company_id": company_id, **normalized}
            key_set = frozenset(normalized.keys())
            groups[key_set].append(record)

        total_rows = 0
        for key_set, records in groups.items():
            stmt = sqlite_insert(ScreeningCache).values(records)
            update_dict = {
                col: stmt.excluded[col]
                for col in key_set
                if hasattr(ScreeningCache, col)
            }
            if not update_dict:
                # No updatable columns (normalize stripped everything).
                # SQLAlchemy rejects on_conflict_do_update(set_={}) → use DO NOTHING (N8 fix).
                stmt = stmt.on_conflict_do_nothing(index_elements=["company_id"])
            else:
                stmt = stmt.on_conflict_do_update(
                    index_elements=["company_id"],
                    set_=update_dict,
                )
            result = await self._session.execute(stmt)
            total_rows += result.rowcount if hasattr(result, "rowcount") else len(records)

        await self._session.flush()
        return total_rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/repositories/test_screening_repo.py -v`
Expected: All tests PASS

- [ ] **Step 5: Refactor**

Clean up:
- Verify `normalize_screening_cache_payload` handles NaN/inf correctly
- Ensure `hasattr(ScreeningCache, col)` check is sufficient or switch to `ScreeningCache.__table__.columns`

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/repositories/screening.py tests/unit/repositories/test_screening_repo.py
git commit -m "feat(repositories): add bulk_upsert_cache with key-set grouping and existing-value preservation"
```

---

## Task 3: Refactor `enrich_with_yahoo()` to Use Batch API + Batch Save

**Files:**
- Modify: `src/stock_analyze_system/services/screening_universe.py`
- Test: `tests/unit/services/test_screening_universe_service.py` (MODIFY)

**Rationale:** Replace the per-ticker asyncio.gather loop with batch fetch + batch persist. On batch DB failure, fallback to per-row individual `upsert_cache` to preserve R7 pattern (1 failure does not block others). Failed counts are properly tracked (N3 fix).

### M1: Existing Test Migration Strategy

The existing `TestEnrichWithYahoo` class has 8 tests. Here's the mapping:

| Existing Test | Action | Rationale |
|--------------|--------|-----------|
| `test_fills_all_fields_from_full_response` | **Rewrite** | Mock `get_screening_info_batch` instead of `get_screening_info`; assert batch API called once |
| `test_yahoo_date_strings_are_normalized_before_commit` | **Rewrite** | Mock `get_screening_info_batch` returning date strings; assert normalization still works |
| `test_one_ticker_raise_others_continue` | **Rewrite** | Simulate partial batch failure (1 ticker missing from response); assert succeeded=3, skipped=1 |
| `test_yahoo_returns_none_increments_skipped` | **Rewrite** | Mock `get_screening_info_batch` returning `{}`; assert skipped=len(eligible) |
| `test_warning_log_carries_exc_info` | **Rewrite** | Mock `get_screening_info_batch` raising exception; assert error log |
| `test_excludes_ticker_none_companies` | **Keep** | No changes needed (eligibility logic unchanged) |
| `test_limit_truncates_attempted` | **Keep** | No changes needed (limit logic unchanged) |
| `test_respects_max_concurrency` | **Delete** | max_concurrency is ignored in batch mode; behavior is inherently different |

- [ ] **Step 1: Rewrite existing enrich tests for batch mode**

> **Note (Q3):** 以下のテストは既存 `tests/unit/services/test_screening_universe_service.py` 内の
> `_seed_company` ヘルパーと `tests/fixtures/yahoo_screening_responses.py` の
> `yahoo_full_response()` を再利用する。新規定義は不要。

```python
class TestEnrichWithYahooBatch:
    @pytest.mark.asyncio
    async def test_fills_all_fields_from_full_response(self, session):
        _seed_company(session, "US_AAPL", "AAPL")
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(
            return_value={"AAPL": yahoo_full_response("AAPL")}
        )
        sec = MagicMock()
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec,
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24, limit=None)

        assert result.attempted == 1
        assert result.succeeded == 1
        assert result.failed == 0
        # Verify batch API was called once with all tickers
        yahoo.get_screening_info_batch.assert_called_once_with(["AAPL"])

        cache = await session.get(ScreeningCache, "US_AAPL")
        assert cache is not None
        assert cache.trailing_per == 28.4
        assert cache.market_cap == 3.5e12
        # Note: production batch API does not return sector/industry — fixture reuses
        # the individual-API mock for service-layer test independence (N12).
        assert cache.sector == "Technology"

    @pytest.mark.asyncio
    async def test_batch_partial_failure_skips_missing(self, session):
        """バッチ内の一部銘柄がレスポンスに含まれない場合はスキップ"""
        for tk in ("AAPL", "MSFT", "FAIL", "TSLA", "JPM"):
            _seed_company(session, f"US_{tk}", tk)
        await session.commit()

        # FAIL is not in the response → skipped
        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            "AAPL": yahoo_full_response("AAPL"),
            "MSFT": yahoo_full_response("MSFT"),
            "TSLA": yahoo_full_response("TSLA"),
            "JPM": yahoo_full_response("JPM"),
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.attempted == 5
        assert result.succeeded == 4
        assert result.skipped == 1
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_batch_api_failure_falls_back_to_individual(self, session, caplog):
        """バッチDB保存失敗時は個別upsertにフォールバック (C3/N3修正)"""
        _seed_company(session, "US_AAPL", "AAPL")
        _seed_company(session, "US_MSFT", "MSFT")
        # commit する: rollback で companies 行が消えると後続 upsert が FK 違反になる (N7修正)
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            "AAPL": {"stock_price": 150.0, "trailing_per": 25.0},
            "MSFT": {"stock_price": 300.0, "trailing_per": 30.0},
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )

        # Manually break bulk_upsert to simulate DB error
        async def broken_bulk(*args, **kwargs):
            raise RuntimeError("DB deadlock")
        svc._screening_repo.bulk_upsert_cache = broken_bulk

        with caplog.at_level("WARNING",
                             logger="stock_analyze_system.services.screening_universe"):
            result = await svc.enrich_with_yahoo(stale_hours=24)

        # Should fallback to individual upsert and succeed
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.skipped == 0

        cache = await session.get(ScreeningCache, "US_AAPL")
        assert cache.stock_price == 150.0

    @pytest.mark.asyncio
    async def test_fallback_tracks_failed_count(self, session):
        """フォールバック時に個別upsert失敗をfailedに集計する (N3修正)"""
        _seed_company(session, "US_GOOD", "GOOD")
        _seed_company(session, "US_BAD", "BAD")
        # commit する: rollback で companies 行が消えると後続 upsert が FK 違反になる (N7修正)
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            "GOOD": {"stock_price": 100.0},
            "BAD": {"stock_price": 200.0},
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )

        # Break bulk + break BAD's individual upsert
        async def broken_bulk(*args, **kwargs):
            raise RuntimeError("DB deadlock")

        original_upsert = svc._screening_repo.upsert_cache
        async def selective_fail(cid, data):
            if "BAD" in cid:
                raise RuntimeError("constraint violation")
            return await original_upsert(cid, data)

        svc._screening_repo.bulk_upsert_cache = broken_bulk
        svc._screening_repo.upsert_cache = selective_fail

        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.succeeded == 1
        assert result.failed == 1
        assert result.skipped == 0
```

- [ ] **Step 2: Implement the refactored `enrich_with_yahoo()`**

Replace the body in `src/stock_analyze_system/services/screening_universe.py`:

```python
    async def enrich_with_yahoo(
        self,
        limit: int | None = None,
        stale_hours: int | None = 24,
        max_concurrency: int = 8,  # deprecated/ignored in batch mode, kept for API compat
    ) -> EnrichResult:
        """eligible 全件の ScreeningCache を Yahoo v7 batch API で更新.

        - ティッカー一覧を Yahoo batch API に一括送信 (1000銘柄/リクエスト)
        - 取得結果を screening_cache に一括 upsert
        - 一括 upsert 失敗時は個別 upsert_cache にフォールバック (R7)
        - max_concurrency は batch mode では無視される (API互換のため残存)
        """
        eligible = await self._screening_repo.list_eligible_for_enrich(
            stale_hours=stale_hours, limit=limit,
        )
        logger.info(
            "enrich start (batch mode): eligible=%d limit=%s",
            len(eligible), limit,
        )
        t0 = time.perf_counter()

        if not eligible:
            return EnrichResult(
                eligible=0, attempted=0, succeeded=0, failed=0, skipped=0,
                elapsed_seconds=0.0,
            )

        tickers = [tk for _, tk in eligible]

        # Step 1: Batch fetch from Yahoo
        try:
            batch_results = await self._yahoo.get_screening_info_batch(tickers)
        except Exception as exc:
            logger.error("yahoo batch fetch failed: %s", exc, exc_info=exc)
            return EnrichResult(
                eligible=len(eligible),
                attempted=len(eligible),
                succeeded=0,
                failed=0,
                skipped=len(eligible),
                elapsed_seconds=time.perf_counter() - t0,
            )

        # Step 2: Prepare payloads for successful tickers
        payloads: list[tuple[str, dict]] = []
        skipped = 0
        for cid, ticker in eligible:
            data = batch_results.get(ticker)
            if not data:
                skipped += 1
                continue
            payloads.append((cid, data))

        if not payloads:
            return EnrichResult(
                eligible=len(eligible),
                attempted=len(eligible),
                succeeded=0,
                failed=0,
                skipped=skipped,
                elapsed_seconds=time.perf_counter() - t0,
            )

        # Step 3: Batch persist with fallback to individual (N3 fix)
        succeeded = 0
        failed = 0
        try:
            await self._screening_repo.bulk_upsert_cache(payloads)
            await self._screening_repo._session.commit()
            succeeded = len(payloads)
        except Exception as exc:
            logger.warning(
                "bulk upsert failed (%s), falling back to individual upserts",
                exc, exc_info=exc,
            )
            await self._screening_repo._session.rollback()
            for cid, data in payloads:
                try:
                    await self._screening_repo.upsert_cache(cid, data)
                    await self._screening_repo._session.commit()
                    succeeded += 1
                except Exception as inner_exc:  # noqa: BLE001
                    await self._screening_repo._session.rollback()
                    logger.warning(
                        "individual upsert %s failed: %s",
                        cid, inner_exc, exc_info=inner_exc,
                    )
                    failed += 1

        elapsed = time.perf_counter() - t0
        logger.info(
            "enrich done (batch mode): succeeded=%d failed=%d skipped=%d elapsed=%.2fs",
            succeeded, failed, skipped, elapsed,
        )
        return EnrichResult(
            eligible=len(eligible),
            attempted=len(eligible),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            elapsed_seconds=elapsed,
        )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/services/test_screening_universe_service.py::TestEnrichWithYahooBatch -v`
Expected: All tests PASS

- [ ] **Step 4: Remove old `TestEnrichWithYahoo` class**

Delete the old per-ticker test class. Keep `TestRefreshUniverse` unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/screening_universe.py tests/unit/services/test_screening_universe_service.py
git commit -m "feat(services): refactor enrich_with_yahoo to batch API + batch save with fallback"
```

---

## Task 4: Integration Test

**Files:**
- Create: `tests/integration/test_yahoo_batch_enrich.py`

- [ ] **Step 1: Write the test**

> **Note (Q4):** session fixture 名は既存統合テスト (`tests/integration/test_stooq_download.py` 等)
> の規約に揃える。このリポジトリは `session` を採用しているため以下も `session` を使用。

```python
import pytest
from unittest.mock import patch, MagicMock

from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient  # N9修正
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.screening_universe import ScreeningUniverseService


@pytest.mark.asyncio
async def test_batch_enrich_end_to_end(session):  # N10: test_companies 削除
    """10社のバッチenrichが1回のAPI呼び出しで完了し、DBに正しく保存される (N5修正)"""
    # Insert 10 test companies
    for i in range(10):
        session.add(Company(
            id=f"US_T{i}", ticker=f"T{i}",
            name=f"Test {i}", market="Nasdaq",
            accounting_standard="US-GAAP",
        ))
    await session.commit()

    # Mock Yahoo batch API to return all 10
    mock_response = {
        "quoteResponse": {
            "result": [
                {"symbol": f"T{i}", "regularMarketPrice": float(i * 10)}
                for i in range(10)
            ],
        }
    }

    # Patch the correct import path (M3修正)
    with patch(
        "stock_analyze_system.ingestion.yahoo_finance.YfData"
    ) as MockYfData:
        mock_data = MagicMock()
        mock_data.get_raw_json.return_value = mock_response
        MockYfData.return_value = mock_data

        service = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=YahooFinanceClient(rate=1000.0),
        )
        result = await service.enrich_with_yahoo()

        assert result.succeeded == 10
        # Verify only 1 HTTP call was made (all 10 in one batch)
        assert mock_data.get_raw_json.call_count == 1
        # Verify DB state: 10 screening_cache rows exist
        for i in range(10):
            cache = await session.get(ScreeningCache, f"US_T{i}")
            assert cache is not None
            assert cache.stock_price == float(i * 10)
```

- [ ] **Step 2: Run test**

Run: `pytest tests/integration/test_yahoo_batch_enrich.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_yahoo_batch_enrich.py
git commit -m "test(integration): add batch enrich end-to-end test"
```

---

## Task 5: Update Design Doc and ADR

**Files:**
- Modify: `docs/superpowers/specs/2026-05-09-yahoo-batch-api-design.md`
- Create: `docs/adr/003-yahoo-batch-api.md`

- [ ] **Step 1: Write Light ADR**

```markdown
# ADR-003: Yahoo Finance v7 Batch API for Screening Enrichment

## Decision
Replace individual `Ticker.info` calls with direct v7 `/finance/quote` batch API requests (1000 tickers/request) in `ScreeningUniverseService.enrich_with_yahoo()`.

## Context
- Individual calls: 10,376 tickers × 0.36s = ~62 minutes (or ~8 min with concurrency=8)
- Batch API: 11 requests × 0.7s = ~8 seconds
- Batch API fields are limited (no sector/industry/beta/roe/operating_margin/net_margin/revenue_growth/earnings_growth/peg_ratio/fcf_yield/de_ratio)
- These missing fields remain available via `ScreeningMetricsService.refresh_from_sec_google()` which uses SEC financials + quote_prices
- Keep `get_screening_info()` individual method for backward compatibility

## Consequences
- ~60x speed improvement for Yahoo enrichment
- Reduced Yahoo API ban risk (fewer HTTP requests)
- `bulk_upsert_cache` groups rows by key set and issues separate INSERT per group to prevent NULL overwrite of existing values
- Fallback to individual `upsert_cache` on batch DB failure preserves R7 pattern
```

- [ ] **Step 2: Update design doc**

Update `docs/superpowers/specs/2026-05-09-yahoo-batch-api-design.md` to:
- Clarify scope = Step 1 only (Yahoo batch + bulk upsert with key-set grouping)
- List fields NOT returned by v7 API and their current source
- Document `bulk_upsert_cache` key-set grouping behavior
- Note fallback to individual upsert on batch failure

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: add ADR-003 and update design for Yahoo batch API"
```

---

## Self-Review (Post-Revision v3)

### Spec Coverage Check
- [x] Batch API wrapper (`get_screening_info_batch`) → Task 1
- [x] Batch DB upsert with key-set grouping (`bulk_upsert_cache`) → Task 2 (N1修正済み)
- [x] Empty `update_dict` falls back to `DO NOTHING` → Task 2 (N8修正済み)
- [x] Mixed key shape test + empty-after-normalize test → Task 2 (Q2/N8追加済み)
- [x] Service refactor with fallback and failed tracking (`enrich_with_yahoo`) → Task 3 (N3修正済み)
- [x] Fallback test fixtures use `commit` not `flush` to survive rollback → Task 3 (N7修正済み)
- [x] Error handling (partial failures skip, fallback on DB error, failed count) → Task 1 + Task 3 tests
- [x] Rate limiter preserved (batch call intervals via `await self._rate_limiter.acquire()`) → Task 1 implementation
- [x] Backward compatibility (`get_screening_info` kept) → Task 1 (no removal)
- [x] All fields included in batch response mapping → Task 1 implementation
- [x] Existing test migration strategy + helper reuse note → Task 3 M1/Q3
- [x] Out-of-scope fields documented → Task 5 ADR
- [x] Integration test uses DB state assertion instead of commit call count → Task 4 (N5修正済み)
- [x] Integration test imports complete and signature minimal → Task 4 (N9/N10修正済み)
- [x] Dead code removed (company_ids unused, original_bulk unused, dead records check) → Task 2/3 (N2/N4/N11修正済み)
- [x] Misleading "preserved from full_response" comment clarified → Task 3 (N12修正済み)

### Placeholder Scan
- [x] No TBD/TODO
- [x] No vague instructions
- [x] Complete code in every step
- [x] Exact file paths throughout (M2修正済み)
- [x] ADR number fixed to 003 (M4修正済み, Q1確認済み: 002はfiling-content-auto-recoveryで使用中)
- [x] Helper / fixture reuse explicitly noted (Q3/Q4)

### Type Consistency
- [x] `get_screening_info_batch` returns `dict[str, dict]` in all references
- [x] `bulk_upsert_cache` accepts `list[tuple[str, dict]]` consistently
- [x] `EnrichResult` fields match existing dataclass

### ADR Compliance
- [x] ADR-003 covers batch API decision, backward compatibility, key-set grouping, and scope limitation

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-09-yahoo-batch-api.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
