# Stooq Price History Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SEC全登録企業（~10,376社）の直近10年分株価データをstooq.comから取得し、SQLite `price_history` テーブルに保存するCLIコマンドを実装する

**Architecture:** 非同期シーケンシャルダウンロード（1並列・2秒間隔）でstooqサーバー負荷を抑えつつ、10,376社分のCSVをパース・フィルタ・DBにUPSERT。1銘柄ごとにCOMMITしてメモリ節約とエラー分離を両立。

**Tech Stack:** Python 3.12, SQLAlchemy (async), httpx, AsyncRateLimiter (既存), csv.DictReader, pytest

**Design Doc:** `docs/superpowers/specs/2026-05-09-stooq-price-history-design.md`

---

## File Structure

| File | Responsibility |
|------|--------------|
| `src/stock_analyze_system/models/price_history.py` | SQLAlchemyモデル `PriceHistory` |
| `src/stock_analyze_system/repositories/price_history.py` | `PriceHistoryRepository`（UPSERT・一括INSERT） |
| `src/stock_analyze_system/ingestion/stooq.py` | `StooqPriceClient`（CSVダウンロード・パース・フィルタ） |
| `src/stock_analyze_system/cli/stooq.py` | `stooq` サブコマンド（download） |
| `src/stock_analyze_system/cli/app.py` | stooqパーサー登録 |
| `tests/unit/ingestion/test_stooq.py` | StooqPriceClientのユニットテスト |
| `tests/unit/repositories/test_price_history_repo.py` | リポジトリテスト |
| `tests/integration/test_stooq_download.py` | E2Eテスト（mock使用） |

---

## Task 0: ADR — Stooq as Historical Price Source

**Files:**
- Create: `docs/adr/001-stooq-historical-price-source.md`

- [ ] **Step 1: Write ADR**

```markdown
# ADR 001: Stooq as Historical Price Source

## Decision
Use stooq.com (free EOD CSV) as the primary source for bulk historical US stock price ingestion.

## Context
- Need 10-year OHLCV for ~10,000 US companies
- Yahoo Finance has rate limits and requires per-ticker API calls
- stooq provides full-history CSV per ticker with a single authenticated request

## Alternatives Considered
1. Yahoo Finance (yfinance): Good for real-time, but 10,000 sequential calls would take ~5+ hours and risk bans
2. FMP API: Daily limit (250) too low for bulk
3. stooq bulk ZIP: Requires authentication and terms are unclear for redistribution

## Consequences
- Data is T+1 delayed (acceptable for fundamental analysis)
- Must respect stooq rate limits (1 req / 2 sec) to avoid being blocked
- API key may expire; manual re-acquisition may be needed
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/001-stooq-historical-price-source.md
git commit -m "docs(adr): add stooq as historical price source"
```

---

## Task 1: PriceHistory Model

**Files:**
- Create: `src/stock_analyze_system/models/price_history.py`
- Test: `tests/unit/models/test_price_history.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/models/test_price_history.py
from stock_analyze_system.models.price_history import PriceHistory

def test_price_history_fields():
    ph = PriceHistory(
        company_id="US_AAPL",
        ticker="AAPL",
        date="2021-05-08",
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000000,
    )
    assert ph.company_id == "US_AAPL"
    assert ph.ticker == "AAPL"
    assert str(ph.date) == "2021-05-08"
```

Run: `pytest tests/unit/models/test_price_history.py -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement the model**

```python
# src/stock_analyze_system/models/price_history.py
from __future__ import annotations

from datetime import date as date_type

from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_analyze_system.models.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(nullable=False)
    ticker: Mapped[str] = mapped_column(nullable=False)
    date: Mapped[date_type] = mapped_column(nullable=False)
    open: Mapped[float | None]
    high: Mapped[float | None]
    low: Mapped[float | None]
    close: Mapped[float | None]
    volume: Mapped[float | None]
    source: Mapped[str] = mapped_column(default="stooq")
    created_at: Mapped[str] = mapped_column(default="now()")

    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_price_history_company_date"),
        Index("idx_price_history_company_date", "company_id", "date"),
        Index("idx_price_history_date", "date"),
    )
```

- [ ] **Step 3: Run test**

Run: `pytest tests/unit/models/test_price_history.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/models/price_history.py tests/unit/models/test_price_history.py
git commit -m "feat(models): add PriceHistory model"
```

---

## Task 2: PriceHistoryRepository

**Files:**
- Create: `src/stock_analyze_system/repositories/price_history.py`
- Test: `tests/unit/repositories/test_price_history_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/repositories/test_price_history_repo.py
import pytest
from datetime import date

from stock_analyze_system.repositories.price_history import PriceHistoryRepository
from stock_analyze_system.models.price_history import PriceHistory
from sqlalchemy import select

@pytest.mark.asyncio
async def test_upsert_many_creates_records(session):
    repo = PriceHistoryRepository(session)
    rows = [
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 5, 8), "close": 100.0},
        {"company_id": "US_AAPL", "ticker": "AAPL", "date": date(2021, 5, 7), "close": 99.0},
    ]
    count = await repo.upsert_many(rows)
    assert count == 2
    
    result = await session.execute(select(PriceHistory).where(PriceHistory.company_id == "US_AAPL"))
    assert len(result.scalars().all()) == 2
```

Run: `pytest tests/unit/repositories/test_price_history_repo.py -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement repository**

```python
# src/stock_analyze_system/repositories/price_history.py
from __future__ import annotations

import logging
from datetime import date as date_type

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.price_history import PriceHistory
from stock_analyze_system.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PriceHistoryRepository(BaseRepository[PriceHistory]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PriceHistory)

    async def upsert_many(self, rows: list[dict]) -> int:
        """Bulk upsert price history rows. Returns inserted/updated count."""
        if not rows:
            return 0
        
        stmt = sqlite_insert(PriceHistory).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["company_id", "date"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "ticker": stmt.excluded.ticker,
                "source": stmt.excluded.source,
            },
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def get_history(
        self, company_id: str, start_date: date_type | None = None, end_date: date_type | None = None,
    ) -> list[PriceHistory]:
        from sqlalchemy import select
        
        stmt = select(PriceHistory).where(PriceHistory.company_id == company_id)
        if start_date:
            stmt = stmt.where(PriceHistory.date >= start_date)
        if end_date:
            stmt = stmt.where(PriceHistory.date <= end_date)
        stmt = stmt.order_by(PriceHistory.date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 3: Run test**

Run: `pytest tests/unit/repositories/test_price_history_repo.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/repositories/price_history.py tests/unit/repositories/test_price_history_repo.py
git commit -m "feat(repositories): add PriceHistoryRepository with bulk upsert"
```

---

## Task 3: StooqPriceClient

**Files:**
- Create: `src/stock_analyze_system/ingestion/stooq.py`
- Test: `tests/unit/ingestion/test_stooq.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/ingestion/test_stooq.py
import pytest
from datetime import date, timedelta

from stock_analyze_system.ingestion.stooq import StooqPriceClient

@pytest.mark.asyncio
async def test_fetch_history_parses_csv(httpx_mock):
    csv_body = "Date,Open,High,Low,Close,Volume\n2021-05-08,100,105,99,104,1000000\n2021-05-07,99,101,98,100,900000"
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=testkey", text=csv_body)
    
    client = StooqPriceClient(api_key="testkey", rate=1000)  # high rate for test
    rows = await client.fetch_history("AAPL")
    
    assert len(rows) == 2
    assert rows[0]["date"] == date(2021, 5, 8)
    assert rows[0]["close"] == 104.0

@pytest.mark.asyncio
async def test_fetch_history_filters_by_years(httpx_mock):
    cutoff = date.today() - timedelta(days=10*365)
    old_date = (cutoff - timedelta(days=1)).strftime("%Y-%m-%d")
    new_date = date.today().strftime("%Y-%m-%d")
    csv_body = f"Date,Open,High,Low,Close,Volume\n{new_date},100,105,99,104,1000000\n{old_date},50,55,49,54,500000"
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=msft.us&i=d&apikey=testkey", text=csv_body)
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    rows = await client.fetch_history("MSFT", years=10)
    
    assert len(rows) == 1
    assert rows[0]["date"] == date.fromisoformat(new_date)
```

Run: `pytest tests/unit/ingestion/test_stooq.py -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement client**

```python
# src/stock_analyze_system/ingestion/stooq.py
from __future__ import annotations

import csv
import io
import logging
from datetime import date as date_type
from datetime import timedelta

import httpx

from stock_analyze_system.ingestion.base import AsyncRateLimiter

logger = logging.getLogger(__name__)

_STOOQ_CSV_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d&apikey={apikey}"
_DEFAULT_TIMEOUT = 30.0


class StooqPriceClient:
    """stooq.com から株価履歴CSVを取得するクライアント."""

    def __init__(self, api_key: str, rate: float = 0.5):
        self._api_key = api_key
        self._rate_limiter = AsyncRateLimiter(rate=rate)
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def fetch_history(
        self, ticker: str, years: int | None = 10,
    ) -> list[dict]:
        """指定tickerの履歴を取得し、yearsでフィルタしてdictリストを返す.

        Args:
            ticker: 大文字のティッカー（e.g. AAPL）
            years: 何年分まで保持するか。Noneなら全履歴。
        """
        await self._rate_limiter.acquire()
        symbol = f"{ticker.lower()}.us"
        url = _STOOQ_CSV_URL.format(symbol=symbol, apikey=self._api_key)
        
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("stooq: ticker not found: %s", ticker)
                raise StooqNotFoundError(ticker) from exc
            raise
        
        text = resp.text
        if not text or "Date" not in text:
            logger.warning("stooq: empty or invalid response for %s", ticker)
            raise StooqParseError(ticker, "empty or invalid response")
        
        rows = self._parse_csv(text, ticker, years)
        logger.info("stooq: fetched %d rows for %s", len(rows), ticker)
        return rows

    def _parse_csv(
        self, text: str, ticker: str, years: int | None,
    ) -> list[dict]:
        cutoff: date_type | None = None
        if years is not None:
            cutoff = date_type.today() - timedelta(days=years * 365)
        
        rows: list[dict] = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                row_date = date_type.fromisoformat(row["Date"])
            except (KeyError, ValueError):
                continue
            
            if cutoff is not None and row_date < cutoff:
                continue
            
            rows.append({
                "company_id": None,  # filled by caller
                "ticker": ticker,
                "date": row_date,
                "open": self._to_float(row.get("Open")),
                "high": self._to_float(row.get("High")),
                "low": self._to_float(row.get("Low")),
                "close": self._to_float(row.get("Close")),
                "volume": self._to_float(row.get("Volume")),
                "source": "stooq",
            })
        
        # 古い順に並べる（stooqは最新が先頭）
        rows.reverse()
        return rows

    @staticmethod
    def _to_float(val: str | None) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except ValueError:
            return None

    async def close(self):
        await self._client.aclose()


class StooqError(Exception):
    pass


class StooqNotFoundError(StooqError):
    pass


class StooqParseError(StooqError):
    pass
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ingestion/test_stooq.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/ingestion/stooq.py tests/unit/ingestion/test_stooq.py
git commit -m "feat(ingestion): add StooqPriceClient for historical CSV download"
```

---

## Task 4: CLI Command

**Files:**
- Create: `src/stock_analyze_system/cli/stooq.py`
- Test: `tests/unit/cli/test_stooq_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cli/test_stooq_cli.py
import argparse
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli import stooq as cli_stooq

def _parse(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    cli_stooq.register_parser(sub)
    return parser.parse_args(["stooq", *argv])

class TestStooqCli:
    @pytest.mark.asyncio
    async def test_download_parses_args(self):
        args = _parse(["download", "--years", "10", "--apikey", "testkey"])
        assert args.action == "download"
        assert args.years == 10
        assert args.apikey == "testkey"
```

Run: `pytest tests/unit/cli/test_stooq_cli.py -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement CLI**

```python
# src/stock_analyze_system/cli/stooq.py
"""stooq サブコマンド（historical price download）."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date as date_type
from typing import TYPE_CHECKING

from stock_analyze_system.ingestion.stooq import (
    StooqNotFoundError,
    StooqParseError,
    StooqPriceClient,
)

if TYPE_CHECKING:
    from stock_analyze_system.cli.container import ServiceContainer

logger = logging.getLogger(__name__)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("stooq", help="stooq.com historical price operations")
    sub = parser.add_subparsers(dest="action", required=True)

    dl = sub.add_parser("download", help="Download historical prices from stooq")
    dl.add_argument("--years", type=int, default=10, help="Keep only last N years")
    dl.add_argument("--apikey", type=str, required=True, help="stooq API key")
    dl.add_argument("--limit", type=int, default=None, help="Limit number of companies (for testing)")
    dl.add_argument("--dry-run", action="store_true", help="Skip DB writes")

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: "ServiceContainer") -> None:
    if args.action == "download":
        await _handle_download(args, services)


async def _handle_download(args: argparse.Namespace, services: "ServiceContainer") -> None:
    api_key = args.apikey
    years = args.years
    limit = args.limit
    dry_run = args.dry_run

    from stock_analyze_system.models.company import Company
    from stock_analyze_system.repositories.price_history import PriceHistoryRepository
    from sqlalchemy import select

    repo = PriceHistoryRepository(services._session)

    # Fetch US companies with tickers
    stmt = select(Company).where(Company.id.like("US_%"), Company.ticker.is_not(None))
    if limit:
        stmt = stmt.limit(limit)
    result = await services._session.execute(stmt)
    companies = list(result.scalars().all())

    total = len(companies)
    logger.info("stooq download: %d companies to process", total)

    client = StooqPriceClient(api_key=api_key, rate=0.5)
    errors: list[dict] = []
    success = 0
    t0 = time.perf_counter()

    for idx, company in enumerate(companies, 1):
        ticker = company.ticker
        logger.info("[%d/%d] Processing %s (%s)", idx, total, company.id, ticker)
        try:
            rows = await client.fetch_history(ticker, years=years)
        except StooqNotFoundError:
            errors.append({"ticker": ticker, "company_id": company.id, "reason": "NOT_FOUND"})
            continue
        except StooqParseError as exc:
            errors.append({"ticker": ticker, "company_id": company.id, "reason": f"PARSE_ERROR: {exc}"})
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticker": ticker, "company_id": company.id, "reason": f"ERROR: {exc}"})
            continue

        if not rows:
            errors.append({"ticker": ticker, "company_id": company.id, "reason": "EMPTY"})
            continue

        # Fill company_id
        for row in rows:
            row["company_id"] = company.id

        if not dry_run:
            await repo.upsert_many(rows)
            await repo._session.commit()

        success += 1

    await client.close()
    elapsed = time.perf_counter() - t0

    # Report
    report = {
        "total": total,
        "success": success,
        "failed": len(errors),
        "elapsed_seconds": elapsed,
        "errors": errors,
    }

    print(f"\nDownload Summary\n{'='*40}")
    print(f"Total companies: {total}")
    print(f"Success: {success}")
    print(f"Failed: {len(errors)}")
    print(f"Elapsed: {elapsed:.1f}s")
    
    if errors:
        error_path = f"data/stooq_errors_{date_type.today().isoformat()}.json"
        with open(error_path, "w") as f:
            json.dump(errors, f, indent=2)
        print(f"Errors saved to: {error_path}")

    return None
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/cli/test_stooq_cli.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/cli/stooq.py tests/unit/cli/test_stooq_cli.py
git commit -m "feat(cli): add stooq download command"
```

---

## Task 5: Wire into app.py

**Files:**
- Modify: `src/stock_analyze_system/cli/app.py`

- [ ] **Step 1: Modify app.py**

```python
# src/stock_analyze_system/cli/app.py
from stock_analyze_system.cli import (
    company, filings, financial, jobs, quotes, rag, screening, serve, target,
    valuation, watchlist, stooq,  # ADD
)
```

And around line 33:
```python
    stooq.register_parser(subparsers)  # ADD
    rag.register_parser(subparsers)
```

- [ ] **Step 2: Commit**

```bash
git add src/stock_analyze_system/cli/app.py
git commit -m "feat(cli): wire stooq command into app parser"
```

---

## Task 6: Integration Test

**Files:**
- Test: `tests/integration/test_stooq_download.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_stooq_download.py
import pytest
from datetime import date, timedelta

from stock_analyze_system.ingestion.stooq import StooqPriceClient


@pytest.mark.asyncio
async def test_stooq_client_fetch_aapl_real():
    """Real network test — requires valid API key."""
    import os
    api_key = os.getenv("STOOQ_API_KEY")
    if not api_key:
        pytest.skip("STOOQ_API_KEY not set")
    
    client = StooqPriceClient(api_key=api_key, rate=0.5)
    try:
        rows = await client.fetch_history("AAPL", years=1)
        assert len(rows) > 200  # ~1 year of trading days
        assert all(r["ticker"] == "AAPL" for r in rows)
        assert all(isinstance(r["date"], date) for r in rows)
    finally:
        await client.close()
```

Run: `STOOQ_API_KEY=xxx pytest tests/integration/test_stooq_download.py -v`
Expected: PASS (with valid key)

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_stooq_download.py
git commit -m "test(integration): add stooq real network test"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:** All design requirements implemented
- [ ] **Placeholder scan:** No TBD/TODO/fill-in-later
- [ ] **Type consistency:** `PriceHistory` model matches repository and client
- [ ] **Test coverage:** Unit + integration tests for all new code
- [ ] **Commit discipline:** Conventional commits, one logical change per commit
- [ ] **Error handling:** All 4 error categories covered
- [ ] **Rate limiting:** 2-second interval enforced
- [ ] **DB safety:** One commit per ticker, bulk upsert with conflict handling

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-09-stooq-price-history.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
