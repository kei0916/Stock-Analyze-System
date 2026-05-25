# Google Sheets Quote Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Google Sheets `GOOGLEFINANCE` price provider, persist latest quote prices, and use SEC financial data plus cached prices to populate valuations and screening cache without full-universe yfinance calls.

**Architecture:** Introduce a quote layer between external price sources and valuation/screening computation. Google Sheets writes formulas and reads calculated prices; `QuoteService` persists per-company quote status; `JobService` and a new screening metrics service consume cached prices. Yahoo remains available as a fallback path.

**Tech Stack:** SQLAlchemy async, SQLite, FastAPI/CLI service container, Google Sheets API via `google-api-python-client` + `google-auth`, pytest + pytest-asyncio, existing `uv run pytest` workflow.

---

## Execution Preconditions

- Work in an isolated branch or worktree before changing implementation files. The current repository may contain unrelated dirty changes; do not stage or revert files outside each task's file list.
- Run each task's test command before committing that task.
- Use small commits. Each task below ends with a commit command.
- Do not make real Google API calls from unit tests. Mock the Sheets service boundary.
- Keep `GOOGLEFINANCE` as a price-only provider. Do not import Google-derived PE, EPS, market cap, or shares into valuation logic.

## File Structure

### New Files

- `src/stock_analyze_system/models/quote_price.py`  
  SQLAlchemy model for latest per-provider quote cache.

- `src/stock_analyze_system/repositories/quote_price.py`  
  Repository for latest quote upsert, lookup, stale/failed listing, and status counts.

- `src/stock_analyze_system/services/quote_symbols.py`  
  Pure functions for SEC exchange + ticker -> Google Finance provider symbol.

- `src/stock_analyze_system/services/google_sheets_quotes.py`  
  Google Sheets client wrapper and DTOs. This is the only module that imports Google API libraries.

- `src/stock_analyze_system/services/quotes.py`  
  Quote orchestration service: build requests, call provider, persist results, read latest prices.

- `src/stock_analyze_system/services/screening_metrics.py`  
  SEC financials + cached price -> `screening_cache` computation.

- `src/stock_analyze_system/cli/quotes.py`  
  CLI command group for quote refresh/status/retry.

- `tests/unit/models/test_quote_price_model.py`

- `tests/unit/repositories/test_quote_price_repo.py`

- `tests/unit/services/test_quote_symbols.py`

- `tests/unit/services/test_google_sheets_quotes.py`

- `tests/unit/services/test_quote_service.py`

- `tests/unit/services/test_screening_metrics_service.py`

- `tests/unit/cli/test_quotes_cli.py`

### Modified Files

- `pyproject.toml`  
  Add Google Sheets API dependencies.

- `config/settings.yaml.example`  
  Add `google_sheets` config section.

- `src/stock_analyze_system/config.py`  
  Add `GoogleSheetsConfig` and environment overrides.

- `src/stock_analyze_system/models/__init__.py`  
  Import `QuotePrice` so `Base.metadata.create_all()` registers the table.

- `tests/conftest.py`  
  Import `QuotePrice` for test metadata registration.

- `src/stock_analyze_system/cli/app.py`  
  Register `quotes` command group.

- `src/stock_analyze_system/cli/container.py`  
  Wire `QuotePriceRepository`, `QuoteService`, optional `GoogleSheetsQuoteClient`, `ScreeningMetricsService`, and pass quote service into `JobService` across the relevant tasks.

- `src/stock_analyze_system/web/dependencies.py`  
  No first pass change unless a long-lived Sheets client is added to `ClientBundle`. Prefer constructing the Sheets client inside `setup_services()` from config.

- `src/stock_analyze_system/services/job.py`  
  Add quote-provider path while preserving Yahoo default/fallback.

- `src/stock_analyze_system/cli/jobs.py`  
  Add `--quote-provider` argument for valuation updates.

- `src/stock_analyze_system/cli/screening.py`  
  Add `--source yahoo|sec-google` to `screening refresh`.

- `tests/unit/services/test_job_service.py`  
  Add cached quote valuation tests and preserve existing Yahoo tests.

- `tests/unit/cli/test_jobs_cli.py`  
  Add `--quote-provider` parser/handler coverage.

- `tests/unit/cli/test_screening_cli.py`  
  Add `--source sec-google` parser/handler coverage.

---

### Task 1: Add Google Sheets Configuration

**Files:**
- Modify: `src/stock_analyze_system/config.py`
- Modify: `config/settings.yaml.example`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing config tests**

Append these tests to `tests/unit/test_config.py`:

```python
def test_google_sheets_defaults(config):
    assert config.google_sheets.enabled is False
    assert config.google_sheets.spreadsheet_id == ""
    assert config.google_sheets.worksheet_name == "quotes"
    assert config.google_sheets.credentials_json_path == ""
    assert config.google_sheets.credentials_json_env == "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON"
    assert config.google_sheets.batch_size == 500
    assert config.google_sheets.poll_interval_seconds == 30
    assert config.google_sheets.max_poll_attempts == 10


def test_google_sheets_env_overrides(monkeypatch):
    from stock_analyze_system.config import load_config

    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "sheet-123")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "/tmp/sa.json")
    monkeypatch.setenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')

    cfg = load_config("does-not-exist.yaml")

    assert cfg.google_sheets.spreadsheet_id == "sheet-123"
    assert cfg.google_sheets.credentials_json_path == "/tmp/sa.json"
    assert cfg.google_sheets.credentials_json == '{"type":"service_account"}'
```

- [ ] **Step 2: Run config tests and verify failure**

Run:

```bash
uv run pytest tests/unit/test_config.py -q
```

Expected: failure mentioning `AppConfig` has no `google_sheets` attribute.

- [ ] **Step 3: Add config dataclass and loader wiring**

In `src/stock_analyze_system/config.py`, add this dataclass after `YahooFinanceConfig`:

```python
@dataclass
class GoogleSheetsConfig:
    enabled: bool = False
    spreadsheet_id: str = ""
    worksheet_name: str = "quotes"
    credentials_json_path: str = ""
    credentials_json_env: str = "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON"
    credentials_json: str = field(default="", repr=False)
    batch_size: int = 500
    poll_interval_seconds: int = 30
    max_poll_attempts: int = 10
```

Add this field to `AppConfig`:

```python
google_sheets: GoogleSheetsConfig = field(default_factory=GoogleSheetsConfig)
```

In `load_config()`, add this constructor argument:

```python
google_sheets=_merge_dict_to_dataclass(
    GoogleSheetsConfig, raw.get("google_sheets"),
),
```

After the existing environment overrides, add:

```python
if val := os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID"):
    config.google_sheets.spreadsheet_id = val
if val := os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH"):
    config.google_sheets.credentials_json_path = val
if val := os.environ.get(config.google_sheets.credentials_json_env):
    config.google_sheets.credentials_json = val
```

- [ ] **Step 4: Add example config section**

Append to `config/settings.yaml.example`:

```yaml
google_sheets:
  enabled: false
  spreadsheet_id: ""
  worksheet_name: "quotes"
  credentials_json_path: ""
  credentials_json_env: "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON"
  batch_size: 500
  poll_interval_seconds: 30
  max_poll_attempts: 10
```

- [ ] **Step 5: Run config tests**

Run:

```bash
uv run pytest tests/unit/test_config.py -q
```

Expected: all tests in `tests/unit/test_config.py` pass.

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/config.py config/settings.yaml.example tests/unit/test_config.py
git commit -m "Add Google Sheets quote configuration"
```

---

### Task 2: Add QuotePrice Model and Repository

**Files:**
- Create: `src/stock_analyze_system/models/quote_price.py`
- Create: `src/stock_analyze_system/repositories/quote_price.py`
- Modify: `src/stock_analyze_system/models/__init__.py`
- Modify: `tests/conftest.py`
- Test: `tests/unit/models/test_quote_price_model.py`
- Test: `tests/unit/repositories/test_quote_price_repo.py`

- [ ] **Step 1: Write failing model test**

Create `tests/unit/models/test_quote_price_model.py`:

```python
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.quote_price import QuotePrice


async def _seed_company(session, company_id="US_AAPL", ticker="AAPL"):
    session.add(Company(
        id=company_id,
        ticker=ticker,
        name=ticker,
        market="Nasdaq",
        accounting_standard="US-GAAP",
    ))
    await session.flush()


@pytest.mark.asyncio
async def test_quote_price_unique_company_provider(session):
    await _seed_company(session)
    session.add(QuotePrice(
        company_id="US_AAPL",
        provider="google_sheets",
        provider_symbol="NASDAQ:AAPL",
        price=185.0,
        currency="USD",
        data_delay_minutes=20,
        as_of=datetime(2026, 4, 29, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        status="ok",
        raw_value="185",
    ))
    await session.flush()

    session.add(QuotePrice(
        company_id="US_AAPL",
        provider="google_sheets",
        provider_symbol="NASDAQ:AAPL",
        price=186.0,
        currency="USD",
        status="ok",
    ))

    with pytest.raises(IntegrityError):
        await session.flush()
```

- [ ] **Step 2: Write failing repository tests**

Create `tests/unit/repositories/test_quote_price_repo.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.quote_price import QuotePriceRepository


async def _seed_company(session, company_id="US_AAPL", ticker="AAPL"):
    session.add(Company(
        id=company_id,
        ticker=ticker,
        name=ticker,
        market="Nasdaq",
        accounting_standard="US-GAAP",
    ))
    await session.flush()


@pytest.mark.asyncio
async def test_upsert_latest_quote_updates_same_provider(session):
    await _seed_company(session)
    repo = QuotePriceRepository(session)

    first = await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
        "fetched_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
    })
    second = await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 186.0,
        "currency": "USD",
        "status": "ok",
        "fetched_at": datetime(2026, 4, 30, tzinfo=timezone.utc),
    })

    assert first.id == second.id
    latest = await repo.get_latest("US_AAPL", provider="google_sheets")
    assert latest.price == 186.0


@pytest.mark.asyncio
async def test_status_counts_and_failed_listing(session):
    await _seed_company(session, "US_AAPL", "AAPL")
    await _seed_company(session, "US_BAD", "BAD")
    repo = QuotePriceRepository(session)

    await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
    })
    await repo.upsert_latest({
        "company_id": "US_BAD",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:BAD",
        "price": None,
        "currency": None,
        "status": "formula_error",
        "error_message": "#N/A",
    })

    counts = await repo.count_by_status(provider="google_sheets")
    failed = await repo.list_failed(provider="google_sheets", limit=10)

    assert counts == {"formula_error": 1, "ok": 1}
    assert [row.company_id for row in failed] == ["US_BAD"]


@pytest.mark.asyncio
async def test_list_stale(session):
    await _seed_company(session)
    repo = QuotePriceRepository(session)
    old = datetime.now(timezone.utc) - timedelta(hours=30)

    await repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
        "fetched_at": old,
    })

    stale = await repo.list_stale(provider="google_sheets", max_age_hours=24, limit=10)
    assert [row.company_id for row in stale] == ["US_AAPL"]
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/models/test_quote_price_model.py tests/unit/repositories/test_quote_price_repo.py -q
```

Expected: import failure for `stock_analyze_system.models.quote_price`.

- [ ] **Step 4: Create model**

Create `src/stock_analyze_system/models/quote_price.py`:

```python
"""Latest quote price cache model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class QuotePrice(Base):
    __tablename__ = "quote_prices"
    __table_args__ = (
        UniqueConstraint("company_id", "provider", name="uq_quote_price_company_provider"),
        Index("ix_quote_price_provider_status", "provider", "status"),
        Index("ix_quote_price_fetched_at", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="google_sheets")
    provider_symbol: Mapped[str | None] = mapped_column(String(40), default=None)
    price: Mapped[float | None] = mapped_column(default=None)
    currency: Mapped[str | None] = mapped_column(String(3), default=None)
    data_delay_minutes: Mapped[int | None] = mapped_column(default=None)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(String(40), default="missing")
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    raw_value: Mapped[str | None] = mapped_column(String(200), default=None)

    company = relationship("Company")
```

- [ ] **Step 5: Register model**

Add to `src/stock_analyze_system/models/__init__.py`:

```python
from stock_analyze_system.models.quote_price import QuotePrice  # noqa: F401
```

Add to `tests/conftest.py` imports:

```python
from stock_analyze_system.models.quote_price import QuotePrice  # noqa: F401
```

- [ ] **Step 6: Create repository**

Create `src/stock_analyze_system/repositories/quote_price.py`:

```python
"""Quote price cache repository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.quote_price import QuotePrice
from stock_analyze_system.repositories.base import BaseRepository


class QuotePriceRepository(BaseRepository[QuotePrice]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, QuotePrice)

    async def upsert_latest(self, data: dict[str, Any]) -> QuotePrice:
        filters = {
            "company_id": data["company_id"],
            "provider": data.get("provider", "google_sheets"),
        }
        remainder = {k: v for k, v in data.items() if k not in filters}
        return await self.upsert(filters, remainder)

    async def get_latest(
        self,
        company_id: str,
        provider: str = "google_sheets",
    ) -> QuotePrice | None:
        stmt = select(QuotePrice).where(
            QuotePrice.company_id == company_id,
            QuotePrice.provider == provider,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_many(
        self,
        company_ids: list[str],
        provider: str = "google_sheets",
    ) -> dict[str, QuotePrice]:
        if not company_ids:
            return {}
        stmt = select(QuotePrice).where(
            QuotePrice.company_id.in_(company_ids),
            QuotePrice.provider == provider,
        )
        result = await self._session.execute(stmt)
        return {row.company_id: row for row in result.scalars().all()}

    async def count_by_status(self, provider: str = "google_sheets") -> dict[str, int]:
        stmt = (
            select(QuotePrice.status, func.count())
            .where(QuotePrice.provider == provider)
            .group_by(QuotePrice.status)
            .order_by(QuotePrice.status)
        )
        result = await self._session.execute(stmt)
        return {status: count for status, count in result.all()}

    async def list_failed(
        self,
        provider: str = "google_sheets",
        limit: int = 100,
    ) -> list[QuotePrice]:
        stmt = (
            select(QuotePrice)
            .where(
                QuotePrice.provider == provider,
                QuotePrice.status != "ok",
            )
            .order_by(QuotePrice.company_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_stale(
        self,
        provider: str = "google_sheets",
        max_age_hours: int = 24,
        limit: int | None = None,
    ) -> list[QuotePrice]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        stmt = (
            select(QuotePrice)
            .where(
                QuotePrice.provider == provider,
                QuotePrice.fetched_at < cutoff,
            )
            .order_by(QuotePrice.fetched_at)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 7: Run tests**

Run:

```bash
uv run pytest tests/unit/models/test_quote_price_model.py tests/unit/repositories/test_quote_price_repo.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/stock_analyze_system/models/quote_price.py src/stock_analyze_system/repositories/quote_price.py src/stock_analyze_system/models/__init__.py tests/conftest.py tests/unit/models/test_quote_price_model.py tests/unit/repositories/test_quote_price_repo.py
git commit -m "Add quote price cache model"
```

---

### Task 3: Add Google Finance Symbol Mapping

**Files:**
- Create: `src/stock_analyze_system/services/quote_symbols.py`
- Test: `tests/unit/services/test_quote_symbols.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/services/test_quote_symbols.py`:

```python
import pytest

from stock_analyze_system.services.quote_symbols import (
    build_google_finance_symbol,
    normalize_google_ticker,
)


@pytest.mark.parametrize(
    ("exchange", "ticker", "expected"),
    [
        ("Nasdaq", "AAPL", "NASDAQ:AAPL"),
        ("NASDAQ", "msft", "NASDAQ:MSFT"),
        ("NYSE", "TSM", "NYSE:TSM"),
        ("NYSE American", "LNG", "NYSEAMERICAN:LNG"),
        ("NYSE Arca", "ARKK", "NYSEARCA:ARKK"),
        ("Cboe BZX", "BATS", "BATS:BATS"),
    ],
)
def test_build_google_finance_symbol(exchange, ticker, expected):
    assert build_google_finance_symbol(exchange, ticker) == expected


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("brk-a", "BRK-A"),
        ("brk.b", "BRK.B"),
        ("googl", "GOOGL"),
        (" tsm ", "TSM"),
    ],
)
def test_normalize_google_ticker(ticker, expected):
    assert normalize_google_ticker(ticker) == expected


def test_unknown_exchange_returns_none():
    assert build_google_finance_symbol("UNKNOWN", "AAPL") is None


def test_missing_ticker_returns_none():
    assert build_google_finance_symbol("Nasdaq", None) is None
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/services/test_quote_symbols.py -q
```

Expected: import failure for `quote_symbols`.

- [ ] **Step 3: Implement symbol mapping**

Create `src/stock_analyze_system/services/quote_symbols.py`:

```python
"""Provider symbol mapping for quote services."""
from __future__ import annotations


_GOOGLE_EXCHANGE_PREFIXES = {
    "NASDAQ": "NASDAQ",
    "Nasdaq": "NASDAQ",
    "NYSE": "NYSE",
    "NYSE American": "NYSEAMERICAN",
    "NYSE Arca": "NYSEARCA",
    "Cboe BZX": "BATS",
}


def normalize_google_ticker(ticker: str | None) -> str | None:
    if ticker is None:
        return None
    normalized = ticker.strip().upper()
    return normalized or None


def build_google_finance_symbol(exchange: str | None, ticker: str | None) -> str | None:
    normalized_ticker = normalize_google_ticker(ticker)
    if normalized_ticker is None or exchange is None:
        return None
    prefix = _GOOGLE_EXCHANGE_PREFIXES.get(exchange.strip())
    if prefix is None:
        return None
    return f"{prefix}:{normalized_ticker}"
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/unit/services/test_quote_symbols.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/quote_symbols.py tests/unit/services/test_quote_symbols.py
git commit -m "Add Google Finance symbol mapping"
```

---

### Task 4: Add Google Sheets Quote Client Boundary

**Files:**
- Modify: `pyproject.toml`
- Create: `src/stock_analyze_system/services/google_sheets_quotes.py`
- Test: `tests/unit/services/test_google_sheets_quotes.py`

- [ ] **Step 1: Write failing tests for parsing and retry-free fake service**

Create `tests/unit/services/test_google_sheets_quotes.py`:

```python
from stock_analyze_system.config import GoogleSheetsConfig
from stock_analyze_system.services.google_sheets_quotes import (
    GoogleSheetsQuoteClient,
    QuoteRequest,
)


class FakeValues:
    def __init__(self, read_values):
        self.updated_body = None
        self.read_values = read_values

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.updated_body = body
        return FakeExecute({"updatedRows": len(body["values"])})

    def batchGet(self, spreadsheetId, ranges, valueRenderOption):
        return FakeExecute({"valueRanges": [{"values": self.read_values}]})


class FakeSpreadsheets:
    def __init__(self, values):
        self._values = values

    def values(self):
        return self._values


class FakeService:
    def __init__(self, read_values):
        self.values_api = FakeValues(read_values)

    def spreadsheets(self):
        return FakeSpreadsheets(self.values_api)


class FakeExecute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


def test_refresh_quotes_parses_successful_values():
    service = FakeService([
        ["US_AAPL", "NASDAQ:AAPL", 185.25, "USD", 20],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="quotes",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_AAPL", provider_symbol="NASDAQ:AAPL"),
    ])

    assert results[0].company_id == "US_AAPL"
    assert results[0].price == 185.25
    assert results[0].currency == "USD"
    assert results[0].data_delay_minutes == 20
    assert results[0].status == "ok"
    assert service.values_api.updated_body["values"][1][2] == '=GOOGLEFINANCE(B2,"price")'


def test_refresh_quotes_marks_formula_error():
    service = FakeService([
        ["US_BAD", "NASDAQ:BAD", "#N/A", "", ""],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="quotes",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_BAD", provider_symbol="NASDAQ:BAD"),
    ])

    assert results[0].price is None
    assert results[0].status == "formula_error"
    assert results[0].error_message == "#N/A"


def test_refresh_quotes_marks_missing_after_poll():
    service = FakeService([
        ["US_EMPTY", "NASDAQ:EMPTY", "", "", ""],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="quotes",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_EMPTY", provider_symbol="NASDAQ:EMPTY"),
    ])

    assert results[0].status == "missing"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/services/test_google_sheets_quotes.py -q
```

Expected: import failure for `google_sheets_quotes`.

- [ ] **Step 3: Add dependencies**

Add these dependencies to `pyproject.toml`:

```toml
"google-api-python-client>=2.0",
"google-auth>=2.0",
```

After editing dependencies, run:

```bash
uv lock
```

Expected: `uv.lock` updates successfully. If the environment cannot reach package indexes, request escalation for network access before continuing.

- [ ] **Step 4: Implement Google Sheets client**

Create `src/stock_analyze_system/services/google_sheets_quotes.py`:

```python
"""Google Sheets GOOGLEFINANCE quote provider."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from stock_analyze_system.config import GoogleSheetsConfig


@dataclass(frozen=True)
class QuoteRequest:
    company_id: str
    provider_symbol: str


@dataclass(frozen=True)
class QuoteResult:
    company_id: str
    provider_symbol: str
    price: float | None
    currency: str | None
    data_delay_minutes: int | None
    status: str
    error_message: str | None
    raw_value: str | None
    fetched_at: datetime


class GoogleSheetsQuoteClient:
    def __init__(self, config: GoogleSheetsConfig, service: Any | None = None):
        self._config = config
        self._service = service

    @classmethod
    def from_config(cls, config: GoogleSheetsConfig) -> "GoogleSheetsQuoteClient":
        if not config.enabled:
            raise ValueError("google_sheets.enabled must be true")
        if not config.spreadsheet_id:
            raise ValueError("google_sheets.spreadsheet_id is required")
        service = _build_sheets_service(config)
        return cls(config=config, service=service)

    async def refresh_quotes(self, requests: list[QuoteRequest]) -> list[QuoteResult]:
        return await asyncio.to_thread(self.refresh_quotes_sync, requests)

    def refresh_quotes_sync(self, requests: list[QuoteRequest]) -> list[QuoteResult]:
        if not requests:
            return []
        service = self._require_service()
        self._write_formula_rows(service, requests)
        rows = self._poll_values(service, expected_rows=len(requests))
        rows_by_company = {
            str(row[0]): row for row in rows if len(row) >= 1
        }
        return [
            _row_to_result(request, rows_by_company.get(request.company_id, []))
            for request in requests
        ]

    def _require_service(self):
        if self._service is None:
            self._service = _build_sheets_service(self._config)
        return self._service

    def _write_formula_rows(self, service, requests: list[QuoteRequest]) -> None:
        values = [[
            "company_id",
            "provider_symbol",
            "price",
            "currency",
            "delay",
        ]]
        for idx, request in enumerate(requests, start=2):
            values.append([
                request.company_id,
                request.provider_symbol,
                f'=GOOGLEFINANCE(B{idx},"price")',
                f'=GOOGLEFINANCE(B{idx},"currency")',
                f'=GOOGLEFINANCE(B{idx},"datadelay")',
            ])
        service.spreadsheets().values().update(
            spreadsheetId=self._config.spreadsheet_id,
            range=f"{self._config.worksheet_name}!A1:E{len(values)}",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _poll_values(self, service, expected_rows: int) -> list[list[Any]]:
        range_name = f"{self._config.worksheet_name}!A2:E{expected_rows + 1}"
        rows: list[list[Any]] = []
        for attempt in range(self._config.max_poll_attempts):
            payload = service.spreadsheets().values().batchGet(
                spreadsheetId=self._config.spreadsheet_id,
                ranges=[range_name],
                valueRenderOption="UNFORMATTED_VALUE",
            ).execute()
            rows = payload.get("valueRanges", [{}])[0].get("values", [])
            if _ready_count(rows) >= expected_rows:
                return rows
            if attempt < self._config.max_poll_attempts - 1:
                time.sleep(self._config.poll_interval_seconds)
        return rows


def _build_sheets_service(config: GoogleSheetsConfig):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if config.credentials_json:
        info = json.loads(config.credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=scopes,
        )
    elif config.credentials_json_path:
        credentials = service_account.Credentials.from_service_account_file(
            config.credentials_json_path,
            scopes=scopes,
        )
    else:
        raise ValueError(
            "Google Sheets credentials are required through credentials_json or credentials_json_path"
        )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _ready_count(rows: list[list[Any]]) -> int:
    count = 0
    for row in rows:
        if len(row) >= 3 and row[2] not in ("", None):
            count += 1
    return count


def _row_to_result(request: QuoteRequest, row: list[Any]) -> QuoteResult:
    fetched_at = datetime.now(timezone.utc)
    raw_price = row[2] if len(row) >= 3 else None
    raw_currency = row[3] if len(row) >= 4 else None
    raw_delay = row[4] if len(row) >= 5 else None

    if raw_price in ("", None):
        return QuoteResult(
            request.company_id,
            request.provider_symbol,
            None,
            None,
            None,
            "missing",
            None,
            None,
            fetched_at,
        )
    if isinstance(raw_price, str) and raw_price.startswith("#"):
        return QuoteResult(
            request.company_id,
            request.provider_symbol,
            None,
            None,
            None,
            "formula_error",
            raw_price,
            raw_price,
            fetched_at,
        )
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return QuoteResult(
            request.company_id,
            request.provider_symbol,
            None,
            None,
            None,
            "formula_error",
            str(raw_price),
            str(raw_price),
            fetched_at,
        )

    delay = None
    if raw_delay not in ("", None):
        try:
            delay = int(float(raw_delay))
        except (TypeError, ValueError):
            delay = None

    return QuoteResult(
        request.company_id,
        request.provider_symbol,
        price,
        str(raw_currency) if raw_currency not in ("", None) else None,
        delay,
        "ok",
        None,
        str(raw_price),
        fetched_at,
    )
```

- [ ] **Step 5: Run Google Sheets client tests**

Run:

```bash
uv run pytest tests/unit/services/test_google_sheets_quotes.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/stock_analyze_system/services/google_sheets_quotes.py tests/unit/services/test_google_sheets_quotes.py
git commit -m "Add Google Sheets quote client"
```

---

### Task 5: Add QuoteService Orchestration

**Files:**
- Create: `src/stock_analyze_system/services/quotes.py`
- Test: `tests/unit/services/test_quote_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/unit/services/test_quote_service.py`:

```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.services.google_sheets_quotes import QuoteResult
from stock_analyze_system.services.quotes import QuoteService


async def _seed_company(session, company_id="US_AAPL", ticker="AAPL", market="Nasdaq"):
    session.add(Company(
        id=company_id,
        ticker=ticker,
        name=ticker,
        market=market,
        accounting_standard="US-GAAP",
    ))
    await session.flush()


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_persists_success(session):
    await _seed_company(session)
    sheets = AsyncMock()
    sheets.refresh_quotes.return_value = [
        QuoteResult(
            company_id="US_AAPL",
            provider_symbol="NASDAQ:AAPL",
            price=185.0,
            currency="USD",
            data_delay_minutes=20,
            status="ok",
            error_message=None,
            raw_value="185",
            fetched_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )
    ]
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=sheets,
    )

    result = await svc.refresh_google_sheets_quotes(company_ids=["US_AAPL"])

    assert result.requested == 1
    assert result.succeeded == 1
    quote = await svc.get_latest_price("US_AAPL")
    assert quote.price == 185.0
    assert quote.provider_symbol == "NASDAQ:AAPL"


@pytest.mark.asyncio
async def test_refresh_google_sheets_quotes_records_unsupported_symbol(session):
    await _seed_company(session, company_id="US_UNKNOWN", ticker="UNK", market="UNKNOWN")
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=AsyncMock(),
    )

    result = await svc.refresh_google_sheets_quotes(company_ids=["US_UNKNOWN"])

    assert result.requested == 1
    assert result.succeeded == 0
    assert result.failed == 1
    quote = await svc.get_latest_price("US_UNKNOWN")
    assert quote.status == "unsupported_symbol"


@pytest.mark.asyncio
async def test_status_counts(session):
    await _seed_company(session)
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=QuotePriceRepository(session),
        google_sheets_client=AsyncMock(),
    )
    await svc._quote_repo.upsert_latest({
        "company_id": "US_AAPL",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:AAPL",
        "price": 185.0,
        "currency": "USD",
        "status": "ok",
    })

    assert await svc.status_counts(provider="google_sheets") == {"ok": 1}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/services/test_quote_service.py -q
```

Expected: import failure for `services.quotes`.

- [ ] **Step 3: Implement QuoteService**

Create `src/stock_analyze_system/services/quotes.py`:

```python
"""Quote refresh orchestration service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.quote_price import QuotePrice
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.services.google_sheets_quotes import (
    GoogleSheetsQuoteClient,
    QuoteRequest,
    QuoteResult,
)
from stock_analyze_system.services.quote_symbols import build_google_finance_symbol


@dataclass
class QuoteRefreshResult:
    requested: int
    submitted: int
    succeeded: int
    failed: int
    skipped: int
    statuses: dict[str, int]


class QuoteService:
    def __init__(
        self,
        company_repo: CompanyRepository,
        quote_repo: QuotePriceRepository,
        google_sheets_client: GoogleSheetsQuoteClient | None = None,
    ):
        self._company_repo = company_repo
        self._quote_repo = quote_repo
        self._google = google_sheets_client

    async def get_latest_price(
        self,
        company_id: str,
        provider: str = "google_sheets",
    ) -> QuotePrice | None:
        return await self._quote_repo.get_latest(company_id, provider=provider)

    async def status_counts(self, provider: str = "google_sheets") -> dict[str, int]:
        return await self._quote_repo.count_by_status(provider=provider)

    async def refresh_google_sheets_quotes(
        self,
        company_ids: list[str] | None = None,
        market_prefix: str | None = "US_",
        limit: int | None = None,
    ) -> QuoteRefreshResult:
        companies = await self._select_companies(company_ids, market_prefix, limit)
        requests: list[QuoteRequest] = []
        statuses: dict[str, int] = {}
        skipped = 0

        for company in companies:
            symbol = build_google_finance_symbol(company.market, company.ticker)
            if symbol is None:
                await self._quote_repo.upsert_latest({
                    "company_id": company.id,
                    "provider": "google_sheets",
                    "provider_symbol": None,
                    "price": None,
                    "currency": None,
                    "status": "unsupported_symbol",
                    "error_message": f"unsupported exchange/ticker: {company.market}/{company.ticker}",
                    "fetched_at": datetime.now(timezone.utc),
                })
                statuses["unsupported_symbol"] = statuses.get("unsupported_symbol", 0) + 1
                skipped += 1
                continue
            requests.append(QuoteRequest(company_id=company.id, provider_symbol=symbol))

        if requests:
            if self._google is None:
                raise ValueError("Google Sheets quote client is not configured")
            results = await self._google.refresh_quotes(requests)
            for result in results:
                await self._persist_result(result)
                statuses[result.status] = statuses.get(result.status, 0) + 1
        else:
            results = []

        await self._quote_repo._session.commit()
        succeeded = statuses.get("ok", 0)
        failed = len(companies) - succeeded
        return QuoteRefreshResult(
            requested=len(companies),
            submitted=len(requests),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            statuses=dict(sorted(statuses.items())),
        )

    async def _select_companies(
        self,
        company_ids: list[str] | None,
        market_prefix: str | None,
        limit: int | None,
    ) -> list[Company]:
        if company_ids:
            existing = await self._company_repo.find_existing_ids(company_ids)
            companies = []
            for company_id in company_ids:
                if company_id in existing:
                    company = await self._company_repo.get_by_id(company_id)
                    if company is not None:
                        companies.append(company)
        else:
            companies = await self._company_repo.list_all()
            if market_prefix:
                companies = [c for c in companies if c.id.startswith(market_prefix)]
        companies = sorted(companies, key=lambda c: c.id)
        return companies[:limit] if limit is not None else companies

    async def _persist_result(self, result: QuoteResult) -> None:
        await self._quote_repo.upsert_latest({
            "company_id": result.company_id,
            "provider": "google_sheets",
            "provider_symbol": result.provider_symbol,
            "price": result.price,
            "currency": result.currency,
            "data_delay_minutes": result.data_delay_minutes,
            "as_of": result.fetched_at,
            "fetched_at": result.fetched_at,
            "status": result.status,
            "error_message": result.error_message,
            "raw_value": result.raw_value,
        })
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/unit/services/test_quote_service.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/quotes.py tests/unit/services/test_quote_service.py
git commit -m "Add quote refresh service"
```

---

### Task 6: Wire QuoteService and Add Quotes CLI

**Files:**
- Create: `src/stock_analyze_system/cli/quotes.py`
- Modify: `src/stock_analyze_system/cli/app.py`
- Modify: `src/stock_analyze_system/cli/container.py`
- Test: `tests/unit/cli/test_quotes_cli.py`
- Test: `tests/unit/characterization/test_container_assembly.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/unit/cli/test_quotes_cli.py`:

```python
import argparse
from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli import quotes


def _parse(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    quotes.register_parser(sub)
    return parser.parse_args(["quotes", *argv])


def test_register_parser_accepts_quotes_refresh():
    args = _parse([
        "sheets",
        "refresh",
        "--market",
        "us",
        "--limit",
        "100",
    ])

    assert args.command == "quotes"
    assert args.action == "sheets"
    assert args.sheets_action == "refresh"
    assert args.market == "us"
    assert args.limit == 100


@pytest.mark.asyncio
async def test_handle_refresh_calls_quote_service(capsys):
    result = MagicMock(
        requested=2,
        submitted=2,
        succeeded=1,
        failed=1,
        skipped=0,
        statuses={"formula_error": 1, "ok": 1},
    )
    services = MagicMock()
    services.quote_service.refresh_google_sheets_quotes = AsyncMock(return_value=result)
    args = Namespace(
        action="sheets",
        sheets_action="refresh",
        market="us",
        limit=2,
        json_output=False,
    )

    await quotes.handle(args, services)

    services.quote_service.refresh_google_sheets_quotes.assert_awaited_once_with(
        market_prefix="US_",
        limit=2,
    )
    out = capsys.readouterr().out
    assert "succeeded: 1" in out
    assert "formula_error=1" in out


@pytest.mark.asyncio
async def test_handle_status_prints_counts(capsys):
    services = MagicMock()
    services.quote_service.status_counts = AsyncMock(return_value={"ok": 3})
    args = Namespace(action="sheets", sheets_action="status", market="us", json_output=False)

    await quotes.handle(args, services)

    assert "ok: 3" in capsys.readouterr().out
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
uv run pytest tests/unit/cli/test_quotes_cli.py -q
```

Expected: import failure for `stock_analyze_system.cli.quotes`.

- [ ] **Step 3: Add quotes CLI module**

Create `src/stock_analyze_system/cli/quotes.py`:

```python
"""Quote refresh CLI commands."""
from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stock_analyze_system.cli.container import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("quotes", help="株価キャッシュ管理")
    sub = parser.add_subparsers(dest="action", required=True)

    sheets = sub.add_parser("sheets", help="Google Sheets quote provider")
    sheets_sub = sheets.add_subparsers(dest="sheets_action", required=True)

    refresh = sheets_sub.add_parser("refresh", help="Google Sheetsから株価を更新")
    refresh.add_argument("--market", choices=["us"], default="us")
    refresh.add_argument("--limit", type=int, default=None)
    refresh.add_argument("--json", action="store_true", dest="json_output")

    status = sheets_sub.add_parser("status", help="株価キャッシュのステータス集計")
    status.add_argument("--market", choices=["us"], default="us")
    status.add_argument("--json", action="store_true", dest="json_output")

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: "ServiceContainer") -> None:
    quote_service = getattr(services, "quote_service", None)
    if quote_service is None:
        print("ERROR: quote_service is unavailable. Check container wiring.", file=sys.stderr)
        sys.exit(1)

    if args.action == "sheets" and args.sheets_action == "refresh":
        result = await quote_service.refresh_google_sheets_quotes(
            market_prefix=_market_prefix(args.market),
            limit=args.limit,
        )
        if args.json_output:
            print(json.dumps(result.__dict__, ensure_ascii=False))
        else:
            statuses = ", ".join(f"{k}={v}" for k, v in result.statuses.items())
            print("Google Sheets quote refresh complete.")
            print(f"  requested: {result.requested}")
            print(f"  submitted: {result.submitted}")
            print(f"  succeeded: {result.succeeded}")
            print(f"  failed:    {result.failed}")
            print(f"  skipped:   {result.skipped}")
            print(f"  statuses:  {statuses}")
        return

    if args.action == "sheets" and args.sheets_action == "status":
        counts = await quote_service.status_counts(provider="google_sheets")
        if args.json_output:
            print(json.dumps(counts, ensure_ascii=False))
        else:
            for status, count in sorted(counts.items()):
                print(f"{status}: {count}")
        return


def _market_prefix(market: str) -> str:
    if market == "us":
        return "US_"
    raise ValueError(f"unsupported market: {market}")
```

- [ ] **Step 4: Register CLI command**

Modify `src/stock_analyze_system/cli/app.py` import list to include `quotes`, then call:

```python
quotes.register_parser(subparsers)
```

- [ ] **Step 5: Wire services in container**

In `src/stock_analyze_system/cli/container.py`, add type checking imports:

```python
from stock_analyze_system.services.quotes import QuoteService
```

Add fields to `ServiceContainer`:

```python
quote_service: QuoteService | None = None
```

In `setup_services()`, import:

```python
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.services.google_sheets_quotes import GoogleSheetsQuoteClient
from stock_analyze_system.services.quotes import QuoteService
```

After repository creation:

```python
quote_repo = QuotePriceRepository(session)
google_quote_client = (
    GoogleSheetsQuoteClient.from_config(config.google_sheets)
    if config.google_sheets.enabled
    else None
)
quote_svc = QuoteService(
    company_repo=company_repo,
    quote_repo=quote_repo,
    google_sheets_client=google_quote_client,
)
```

Include `quote_service=quote_svc` in `ServiceContainer(...)`.

- [ ] **Step 6: Run CLI and container tests**

Run:

```bash
uv run pytest tests/unit/cli/test_quotes_cli.py tests/unit/characterization/test_container_assembly.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/cli/quotes.py src/stock_analyze_system/cli/app.py src/stock_analyze_system/cli/container.py tests/unit/cli/test_quotes_cli.py tests/unit/characterization/test_container_assembly.py
git commit -m "Wire quote service and CLI"
```

---

### Task 7: Integrate Cached Quotes into Valuation Updates

**Files:**
- Modify: `src/stock_analyze_system/services/job.py`
- Modify: `src/stock_analyze_system/cli/jobs.py`
- Test: `tests/unit/services/test_job_service.py`
- Test: `tests/unit/cli/test_jobs_cli.py`

- [ ] **Step 1: Add failing JobService test for cached quote path**

Append to `tests/unit/services/test_job_service.py`:

```python
    async def test_update_valuation_uses_google_sheets_cached_quote(self):
        company = MagicMock(id="US_AAPL", ticker="AAPL")

        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")

        quote = MagicMock(
            status="ok",
            price=185.0,
            currency="USD",
        )
        quote_service = AsyncMock()
        quote_service.get_latest_price.return_value = quote

        yahoo_client = AsyncMock()
        valuation_svc = AsyncMock()
        financial_svc = AsyncMock()
        financial_svc.get_latest.return_value = MagicMock(
            eps=6.0,
            equity=100e9,
            shares_outstanding=15e9,
            total_debt=100e9,
            cash=50e9,
            ebitda=130e9,
            revenue=394e9,
            fcf=111e9,
            net_income=94e9,
        )

        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=valuation_svc,
            financial_svc=financial_svc,
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
            quote_service=quote_service,
        )

        result = await svc.update_valuation_for_company(
            "US_AAPL",
            quote_provider="google_sheets",
        )

        assert result.valuations_count == 1
        yahoo_client.get_stock_price.assert_not_awaited()
        saved = valuation_svc.upsert_valuation.await_args.args[1]
        assert saved["stock_price"] == 185.0
        assert saved["market_cap"] == 185.0 * 15e9
```

Append another failure-path test:

```python
    async def test_google_sheets_quote_provider_missing_quote_skips_valuation(self):
        company = MagicMock(id="US_AAPL", ticker="AAPL")
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")

        quote_service = AsyncMock()
        quote_service.get_latest_price.return_value = MagicMock(
            status="formula_error",
            price=None,
            currency=None,
        )
        valuation_svc = AsyncMock()

        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=valuation_svc,
            financial_svc=AsyncMock(),
            yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
            quote_service=quote_service,
        )

        result = await svc.update_valuation_for_company(
            "US_AAPL",
            quote_provider="google_sheets",
        )

        assert result.valuations_count == 0
        assert "No usable quote" in result.skipped_reasons[0]
        valuation_svc.upsert_valuation.assert_not_awaited()
```

- [ ] **Step 2: Add failing CLI parser test**

In `tests/unit/cli/test_jobs_cli.py`, add:

```python
def test_jobs_valuations_accepts_quote_provider():
    import argparse

    from stock_analyze_system.cli.jobs import register_parser

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    register_parser(sub)
    args = parser.parse_args([
        "jobs",
        "valuations",
        "--market",
        "us",
        "--quote-provider",
        "google_sheets",
    ])

    assert args.action == "valuations"
    assert args.quote_provider == "google_sheets"
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/services/test_job_service.py tests/unit/cli/test_jobs_cli.py -q
```

Expected: failure because `JobService.__init__()` has no `quote_service` and CLI has no `--quote-provider`.

- [ ] **Step 4: Modify JobService constructor and valuation path**

In `src/stock_analyze_system/services/job.py`, add TYPE_CHECKING import:

```python
from stock_analyze_system.services.quotes import QuoteService
```

Change constructor signature:

```python
quote_service: QuoteService | None = None,
```

Set:

```python
self._quote_service = quote_service
```

Add helper method:

```python
    async def _get_price_data_for_company(
        self,
        company,
        result: SyncResult,
        quote_provider: str,
    ) -> dict | None:
        if quote_provider == "google_sheets":
            if self._quote_service is None:
                result.errors.append("quote_service unavailable")
                return None
            quote = await self._quote_service.get_latest_price(
                company.id,
                provider="google_sheets",
            )
            if quote is None or quote.status != "ok" or quote.price is None:
                result.skipped_reasons.append(
                    f"No usable quote for {company.id} from google_sheets"
                )
                return None
            return {
                "price": quote.price,
                "market_cap": None,
                "currency": quote.currency or "USD",
            }

        yf_ticker = self._company_svc.resolve_yf_ticker(company)
        if not yf_ticker:
            return None
        return await self._yahoo.get_stock_price(yf_ticker)
```

Change `_update_valuation_for_company()` signature:

```python
quote_provider: str = "yahoo",
```

Replace direct Yahoo price fetch with:

```python
price_data = await self._get_price_data_for_company(
    company,
    result,
    quote_provider,
)
```

Change `update_valuation_for_company()` signature:

```python
async def update_valuation_for_company(
    self,
    company_id: str,
    quote_provider: str = "yahoo",
) -> SyncResult:
```

Pass `quote_provider` to `_update_valuation_for_company()`.

Change `run_target_valuation_update()` signature:

```python
quote_provider: str = "yahoo",
```

Call:

```python
await self.update_valuation_for_company(company_id, quote_provider=quote_provider)
```

Keep `sync_company()` on Yahoo for now by calling `_update_valuation_for_company(company, result)`.

- [ ] **Step 5: Pass QuoteService from container**

In `src/stock_analyze_system/cli/container.py`, update `JobService(...)` construction:

```python
job_svc = JobService(
    company_svc, financial_sync, filing_sync, valuation_svc,
    financial_svc, yahoo_client, fmp_client,
    target_svc=target_svc,
    quote_service=quote_svc,
)
```

Place this after `quote_svc` is defined. If `job_svc` is currently created before quote wiring, move job service construction below `quote_svc`.

- [ ] **Step 6: Add CLI argument and handler pass-through**

In `src/stock_analyze_system/cli/jobs.py`, add to `valuations_p`:

```python
valuations_p.add_argument(
    "--quote-provider",
    choices=["yahoo", "google_sheets"],
    default="yahoo",
    help="株価取得元",
)
```

In `_handle_valuations()`, pass:

```python
quote_provider=args.quote_provider,
```

- [ ] **Step 7: Run tests**

Run:

```bash
uv run pytest tests/unit/services/test_job_service.py tests/unit/cli/test_jobs_cli.py tests/unit/characterization/test_container_assembly.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/stock_analyze_system/services/job.py src/stock_analyze_system/cli/jobs.py src/stock_analyze_system/cli/container.py tests/unit/services/test_job_service.py tests/unit/cli/test_jobs_cli.py tests/unit/characterization/test_container_assembly.py
git commit -m "Use cached quotes for valuation updates"
```

---

### Task 8: Add SEC Financials + Cached Quote Screening Computation

**Files:**
- Create: `src/stock_analyze_system/services/screening_metrics.py`
- Modify: `src/stock_analyze_system/services/screening_universe.py`
- Modify: `src/stock_analyze_system/cli/screening.py`
- Modify: `src/stock_analyze_system/cli/container.py`
- Test: `tests/unit/services/test_screening_metrics_service.py`
- Test: `tests/unit/services/test_screening_universe_service.py`
- Test: `tests/unit/cli/test_screening_cli.py`

- [ ] **Step 1: Write failing screening metrics tests**

Create `tests/unit/services/test_screening_metrics_service.py`:

```python
from datetime import date

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.models.quote_price import QuotePrice
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.financial import FinancialService
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.services.screening_metrics import ScreeningMetricsService


async def _seed_company(session):
    session.add(Company(
        id="US_AAPL",
        ticker="AAPL",
        name="Apple Inc",
        market="Nasdaq",
        sector="Technology",
        accounting_standard="US-GAAP",
        cik="0000320193",
    ))
    await session.flush()


async def _seed_financials(session):
    session.add(FinancialData(
        company_id="US_AAPL",
        accounting_standard="US-GAAP",
        currency="USD",
        period_type="annual",
        fiscal_year_end=date(2025, 12, 31),
        revenue=400e9,
        operating_income=120e9,
        net_income=100e9,
        equity=80e9,
        total_debt=110e9,
        cash=60e9,
        ebitda=140e9,
        fcf=105e9,
        eps=6.0,
        shares_outstanding=15e9,
    ))
    session.add(FinancialData(
        company_id="US_AAPL",
        accounting_standard="US-GAAP",
        currency="USD",
        period_type="annual",
        fiscal_year_end=date(2024, 12, 31),
        revenue=360e9,
        operating_income=100e9,
        net_income=90e9,
        equity=75e9,
        total_debt=100e9,
        cash=50e9,
        ebitda=125e9,
        fcf=95e9,
        eps=5.0,
        shares_outstanding=15.2e9,
    ))
    await session.flush()


async def _seed_quote(session):
    session.add(QuotePrice(
        company_id="US_AAPL",
        provider="google_sheets",
        provider_symbol="NASDAQ:AAPL",
        price=200.0,
        currency="USD",
        status="ok",
    ))
    await session.flush()


@pytest.mark.asyncio
async def test_refresh_from_financials_and_quotes_populates_screening_cache(session):
    await _seed_company(session)
    await _seed_financials(session)
    await _seed_quote(session)

    svc = ScreeningMetricsService(
        company_repo=CompanyRepository(session),
        financial_service=FinancialService(FinancialRepository(session)),
        quote_repo=QuotePriceRepository(session),
        screening_repo=ScreeningRepository(session),
    )

    result = await svc.refresh_from_sec_financials_and_quotes(company_ids=["US_AAPL"])

    assert result.requested == 1
    assert result.succeeded == 1
    cache = await session.get(ScreeningCache, "US_AAPL")
    assert cache.stock_price == 200.0
    assert cache.market_cap == 200.0 * 15e9
    assert cache.trailing_per == 200.0 / 6.0
    assert cache.roe == 100e9 / 80e9
    assert cache.revenue_growth == pytest.approx((400e9 - 360e9) / 360e9)
    assert cache.forward_per is None
    assert cache.beta is None


@pytest.mark.asyncio
async def test_missing_quote_skips_company(session):
    await _seed_company(session)
    await _seed_financials(session)
    svc = ScreeningMetricsService(
        company_repo=CompanyRepository(session),
        financial_service=FinancialService(FinancialRepository(session)),
        quote_repo=QuotePriceRepository(session),
        screening_repo=ScreeningRepository(session),
    )

    result = await svc.refresh_from_sec_financials_and_quotes(company_ids=["US_AAPL"])

    assert result.succeeded == 0
    assert result.skipped == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/services/test_screening_metrics_service.py -q
```

Expected: import failure for `screening_metrics`.

- [ ] **Step 3: Implement ScreeningMetricsService**

Create `src/stock_analyze_system/services/screening_metrics.py`:

```python
"""Screening cache computation from SEC financials and cached quotes."""
from __future__ import annotations

from dataclasses import dataclass, field

from stock_analyze_system.models.enums import PeriodType
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services import metrics
from stock_analyze_system.services.financial import FinancialService


@dataclass
class ScreeningMetricsRefreshResult:
    requested: int
    succeeded: int
    failed: int
    skipped: int
    errors: list[str] = field(default_factory=list)


class ScreeningMetricsService:
    def __init__(
        self,
        company_repo: CompanyRepository,
        financial_service: FinancialService,
        quote_repo: QuotePriceRepository,
        screening_repo: ScreeningRepository,
    ):
        self._company_repo = company_repo
        self._financial_service = financial_service
        self._quote_repo = quote_repo
        self._screening_repo = screening_repo

    async def refresh_from_sec_financials_and_quotes(
        self,
        company_ids: list[str] | None = None,
        market_prefix: str | None = "US_",
        limit: int | None = None,
    ) -> ScreeningMetricsRefreshResult:
        companies = await self._select_companies(company_ids, market_prefix, limit)
        succeeded = failed = skipped = 0
        errors: list[str] = []

        for company in companies:
            try:
                quote = await self._quote_repo.get_latest(company.id, provider="google_sheets")
                if quote is None or quote.status != "ok" or quote.price is None:
                    skipped += 1
                    continue
                series = await self._financial_service.get_timeseries(
                    company.id,
                    PeriodType.ANNUAL,
                    years=3,
                )
                if not series:
                    skipped += 1
                    continue
                latest = series[0]
                previous = series[1] if len(series) > 1 else None
                payload = _build_screening_payload(company, latest, previous, quote.price)
                await self._screening_repo.upsert_cache(company.id, payload)
                succeeded += 1
            except (ValueError, TypeError, AttributeError) as exc:
                failed += 1
                errors.append(f"{company.id}: {exc}")

        await self._screening_repo._session.commit()
        return ScreeningMetricsRefreshResult(
            requested=len(companies),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    async def _select_companies(
        self,
        company_ids: list[str] | None,
        market_prefix: str | None,
        limit: int | None,
    ):
        if company_ids:
            existing = await self._company_repo.find_existing_ids(company_ids)
            companies = []
            for company_id in company_ids:
                if company_id in existing:
                    company = await self._company_repo.get_by_id(company_id)
                    if company is not None:
                        companies.append(company)
        else:
            companies = await self._company_repo.list_all()
            if market_prefix:
                companies = [c for c in companies if c.id.startswith(market_prefix)]
        companies = sorted(companies, key=lambda c: c.id)
        return companies[:limit] if limit is not None else companies


def _build_screening_payload(company, latest, previous, price: float) -> dict:
    market_cap = (
        price * latest.shares_outstanding
        if latest.shares_outstanding is not None
        else None
    )
    return {
        "stock_price": price,
        "market_cap": market_cap,
        "trailing_per": metrics.per(
            price,
            latest.eps,
            market_cap=market_cap,
            net_income=latest.net_income,
        ),
        "eps": latest.eps,
        "forward_per": None,
        "pbr": metrics.pbr(market_cap, latest.equity),
        "psr": metrics.psr(market_cap, latest.revenue),
        "ev_ebitda": (
            metrics.ev_ebitda(market_cap, latest.total_debt, latest.cash, latest.ebitda)
            if market_cap is not None else None
        ),
        "dividend_yield": None,
        "roe": metrics.roe(latest.net_income, latest.equity),
        "operating_margin": metrics.operating_margin(
            latest.operating_income,
            latest.revenue,
        ),
        "net_margin": metrics.net_margin(latest.net_income, latest.revenue),
        "revenue_growth": (
            metrics.revenue_growth(latest.revenue, previous.revenue)
            if previous is not None else None
        ),
        "earnings_growth": (
            metrics.eps_growth(latest.eps, previous.eps)
            if previous is not None else None
        ),
        "de_ratio": metrics.de_ratio(latest.total_debt, latest.equity),
        "peg_ratio": None,
        "fcf_yield": (
            latest.fcf / market_cap
            if latest.fcf is not None and market_cap is not None and market_cap > 0
            else None
        ),
        "sector": company.sector,
        "industry": None,
        "exchange": company.market,
        "beta": None,
        "volume": None,
        "most_recent_quarter": None,
        "last_fiscal_year_end": latest.fiscal_year_end,
        "trailing_eps_date": f"FY ending {latest.fiscal_year_end.isoformat()}",
    }
```

- [ ] **Step 4: Wire service in container**

In `src/stock_analyze_system/cli/container.py`, import:

```python
from stock_analyze_system.services.screening_metrics import ScreeningMetricsService
```

Add this field to `ServiceContainer`:

```python
screening_metrics_service: ScreeningMetricsService | None = None
```

After `screening_repo` is created:

```python
screening_metrics_svc = ScreeningMetricsService(
    company_repo=company_repo,
    financial_service=financial_svc,
    quote_repo=quote_repo,
    screening_repo=screening_repo,
)
```

Include in `ServiceContainer(...)`:

```python
screening_metrics_service=screening_metrics_svc,
```

- [ ] **Step 5: Modify screening CLI**

In `src/stock_analyze_system/cli/screening.py`, change refresh parser:

```python
rf = sub.add_parser("refresh", help="Screening cache enrichment")
rf.add_argument("--source", choices=["yahoo", "sec-google"], default="yahoo")
rf.add_argument("--limit", type=int, default=None)
rf.add_argument("--stale-hours", type=int, default=24)
rf.add_argument("--concurrency", type=int, default=8)
```

In handler:

```python
if args.action == "refresh":
    if args.source == "sec-google":
        metrics_svc = services.screening_metrics_service
        if metrics_svc is None:
            print("ERROR: screening_metrics_service is unavailable.", file=sys.stderr)
            sys.exit(1)
        r = await metrics_svc.refresh_from_sec_financials_and_quotes(
            market_prefix="US_",
            limit=args.limit,
        )
        print("Screening cache refresh (source=sec-google)")
        print(f"  requested: {r.requested}")
        print(f"  succeeded: {r.succeeded}, failed: {r.failed}, skipped: {r.skipped}")
        if r.errors:
            print(f"  errors: {len(r.errors)}")
        return

    r = await universe_svc.enrich_with_yahoo(
        limit=args.limit,
        stale_hours=args.stale_hours,
        max_concurrency=args.concurrency,
    )
```

- [ ] **Step 6: Add CLI tests**

In `tests/unit/cli/test_screening_cli.py`, add:

```python
async def test_screening_refresh_sec_google_calls_metrics_service(capsys):
    from argparse import Namespace
    from unittest.mock import AsyncMock, MagicMock

    from stock_analyze_system.cli import screening

    services = MagicMock()
    services.screening_universe_service = MagicMock()
    services.screening_service = MagicMock()
    services.screening_metrics_service.refresh_from_sec_financials_and_quotes = AsyncMock(
        return_value=MagicMock(requested=2, succeeded=1, failed=0, skipped=1, errors=[])
    )
    args = Namespace(action="refresh", source="sec-google", limit=2)

    await screening.handle(args, services)

    services.screening_metrics_service.refresh_from_sec_financials_and_quotes.assert_awaited_once_with(
        market_prefix="US_",
        limit=2,
    )
    assert "source=sec-google" in capsys.readouterr().out
```

- [ ] **Step 7: Run tests**

Run:

```bash
uv run pytest tests/unit/services/test_screening_metrics_service.py tests/unit/cli/test_screening_cli.py tests/unit/characterization/test_container_assembly.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/stock_analyze_system/services/screening_metrics.py src/stock_analyze_system/cli/screening.py src/stock_analyze_system/cli/container.py tests/unit/services/test_screening_metrics_service.py tests/unit/cli/test_screening_cli.py tests/unit/characterization/test_container_assembly.py
git commit -m "Populate screening cache from SEC financials and quotes"
```

---

### Task 9: Add Operational Status and Retry Support

**Files:**
- Modify: `src/stock_analyze_system/services/quotes.py`
- Modify: `src/stock_analyze_system/repositories/quote_price.py`
- Modify: `src/stock_analyze_system/cli/quotes.py`
- Test: `tests/unit/services/test_quote_service.py`
- Test: `tests/unit/cli/test_quotes_cli.py`

- [ ] **Step 1: Add failing retry service test**

Append to `tests/unit/services/test_quote_service.py`:

```python
@pytest.mark.asyncio
async def test_retry_failed_refreshes_failed_company(session):
    await _seed_company(session, company_id="US_BAD", ticker="BAD", market="Nasdaq")
    repo = QuotePriceRepository(session)
    await repo.upsert_latest({
        "company_id": "US_BAD",
        "provider": "google_sheets",
        "provider_symbol": "NASDAQ:BAD",
        "price": None,
        "currency": None,
        "status": "formula_error",
    })

    sheets = AsyncMock()
    sheets.refresh_quotes.return_value = [
        QuoteResult(
            company_id="US_BAD",
            provider_symbol="NASDAQ:BAD",
            price=10.0,
            currency="USD",
            data_delay_minutes=20,
            status="ok",
            error_message=None,
            raw_value="10",
            fetched_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )
    ]
    svc = QuoteService(
        company_repo=CompanyRepository(session),
        quote_repo=repo,
        google_sheets_client=sheets,
    )

    result = await svc.retry_failed_google_sheets_quotes(limit=10)

    assert result.requested == 1
    assert result.succeeded == 1
```

- [ ] **Step 2: Add failing CLI retry test**

Append to `tests/unit/cli/test_quotes_cli.py`:

```python
@pytest.mark.asyncio
async def test_handle_retry_failed_calls_service(capsys):
    result = MagicMock(
        requested=1,
        submitted=1,
        succeeded=1,
        failed=0,
        skipped=0,
        statuses={"ok": 1},
    )
    services = MagicMock()
    services.quote_service.retry_failed_google_sheets_quotes = AsyncMock(return_value=result)
    args = Namespace(
        action="retry-failed",
        provider="google_sheets",
        limit=10,
        json_output=False,
    )

    await quotes.handle(args, services)

    services.quote_service.retry_failed_google_sheets_quotes.assert_awaited_once_with(limit=10)
    assert "succeeded: 1" in capsys.readouterr().out
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/services/test_quote_service.py tests/unit/cli/test_quotes_cli.py -q
```

Expected: missing `retry_failed_google_sheets_quotes`.

- [ ] **Step 4: Implement retry method**

In `src/stock_analyze_system/services/quotes.py`, add:

```python
    async def retry_failed_google_sheets_quotes(
        self,
        limit: int = 500,
    ) -> QuoteRefreshResult:
        failed = await self._quote_repo.list_failed(
            provider="google_sheets",
            limit=limit,
        )
        return await self.refresh_google_sheets_quotes(
            company_ids=[row.company_id for row in failed],
            market_prefix=None,
            limit=None,
        )
```

- [ ] **Step 5: Add CLI command**

In `src/stock_analyze_system/cli/quotes.py`, register:

```python
retry = sub.add_parser("retry-failed", help="失敗した株価取得を再試行")
retry.add_argument("--provider", choices=["google_sheets"], default="google_sheets")
retry.add_argument("--limit", type=int, default=500)
retry.add_argument("--json", action="store_true", dest="json_output")
```

In `handle()`:

```python
if args.action == "retry-failed":
    result = await quote_service.retry_failed_google_sheets_quotes(limit=args.limit)
    if args.json_output:
        print(json.dumps(result.__dict__, ensure_ascii=False))
    else:
        statuses = ", ".join(f"{k}={v}" for k, v in result.statuses.items())
        print("Google Sheets failed quote retry complete.")
        print(f"  requested: {result.requested}")
        print(f"  submitted: {result.submitted}")
        print(f"  succeeded: {result.succeeded}")
        print(f"  failed:    {result.failed}")
        print(f"  skipped:   {result.skipped}")
        print(f"  statuses:  {statuses}")
    return
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/unit/services/test_quote_service.py tests/unit/cli/test_quotes_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/services/quotes.py src/stock_analyze_system/cli/quotes.py tests/unit/services/test_quote_service.py tests/unit/cli/test_quotes_cli.py
git commit -m "Add quote retry workflow"
```

---

### Task 10: Add Documentation and Manual Verification Commands

**Files:**
- Create: `docs/google-sheets-quote-provider.md`
- Modify: `docs/superpowers/specs/2026-04-29-google-sheets-quote-provider-design.md` only if implementation behavior differs from the design.

- [ ] **Step 1: Create operator documentation**

Create `docs/google-sheets-quote-provider.md`:

```markdown
# Google Sheets Quote Provider

This project can use Google Sheets `GOOGLEFINANCE` as a price-only quote provider for US SEC universe screening.

## Setup

1. Create a Google Cloud service account.
2. Enable the Google Sheets API for the project.
3. Create a spreadsheet and share it with the service account email.
4. Set one of:

```bash
export GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
export GOOGLE_SHEETS_SPREADSHEET_ID='your-spreadsheet-id'
```

or:

```bash
export GOOGLE_SHEETS_CREDENTIALS_JSON_PATH=/path/to/service-account.json
export GOOGLE_SHEETS_SPREADSHEET_ID='your-spreadsheet-id'
```

5. Set `google_sheets.enabled: true` in `config/settings.yaml`.

## Full US Screening Refresh

```bash
scripts/infisical-run uv run stock-analyze screening universe refresh
scripts/infisical-run uv run stock-analyze jobs daily --market us
scripts/infisical-run uv run stock-analyze quotes sheets refresh --market us --limit 100
scripts/infisical-run uv run stock-analyze jobs valuations --market us --quote-provider google_sheets
scripts/infisical-run uv run stock-analyze screening refresh --source sec-google --limit 100
```

Remove `--limit 100` after a successful small run.

## Status and Retry

```bash
scripts/infisical-run uv run stock-analyze quotes sheets status --market us
scripts/infisical-run uv run stock-analyze quotes retry-failed --provider google_sheets --limit 500
```

## Expected Gaps

The Google Sheets provider stores price, currency, and delay only. Forward PER, beta, volume, PEG, dividend yield, and some industry metadata remain empty unless another provider fills them.
```

- [ ] **Step 2: Run doc-related smoke checks**

Run:

```bash
uv run python -m stock_analyze_system --help
uv run python -m stock_analyze_system quotes --help
uv run python -m stock_analyze_system screening refresh --help
uv run python -m stock_analyze_system jobs valuations --help
```

Expected: each command exits with code 0 and shows the new options.

- [ ] **Step 3: Run focused test suite**

Run:

```bash
uv run pytest tests/unit/models/test_quote_price_model.py tests/unit/repositories/test_quote_price_repo.py tests/unit/services/test_quote_symbols.py tests/unit/services/test_google_sheets_quotes.py tests/unit/services/test_quote_service.py tests/unit/services/test_screening_metrics_service.py tests/unit/services/test_job_service.py tests/unit/cli/test_quotes_cli.py tests/unit/cli/test_jobs_cli.py tests/unit/cli/test_screening_cli.py -q
```

Expected: all focused tests pass.

- [ ] **Step 4: Commit**

```bash
git add docs/google-sheets-quote-provider.md
git commit -m "Document Google Sheets quote provider"
```

---

### Task 11: Final Verification

**Files:**
- No implementation files unless verification finds a defect.

- [ ] **Step 1: Run full unit suite**

Run:

```bash
uv run pytest -q
```

Expected: full suite passes.

- [ ] **Step 2: Run lint or syntax checks for changed Python files**

Run:

```bash
uv run python -m compileall src/stock_analyze_system tests
```

Expected: compile succeeds with no syntax errors.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short
```

Expected: only intentional changes from this feature remain. Unrelated pre-existing dirty files may still appear; do not stage them.

- [ ] **Step 4: Manual small-run checklist**

After credentials are configured, run:

```bash
scripts/infisical-run uv run stock-analyze quotes sheets refresh --market us --limit 5
scripts/infisical-run uv run stock-analyze quotes sheets status --market us
scripts/infisical-run uv run stock-analyze jobs valuations --market us --quote-provider google_sheets
scripts/infisical-run uv run stock-analyze screening refresh --source sec-google --limit 5
scripts/infisical-run uv run stock-analyze screening run --limit 5 --json
```

Expected:

- quote refresh reports at least one `ok` status for known US tickers.
- valuation update does not call Yahoo for `google_sheets` provider.
- screening refresh writes rows to `screening_cache`.
- screening run returns non-empty `items` when quotes and financials exist.

- [ ] **Step 5: Final commit if verification fixes were needed**

If any verification-only fixes were made:

```bash
git add <changed-files>
git commit -m "Fix Google Sheets quote provider verification issues"
```

If no fixes were needed, do not create an empty commit.

---

## Plan Self-Review

- Spec coverage:
  - Config: Task 1.
  - Quote cache model/repository: Task 2.
  - Symbol mapping: Task 3.
  - Google Sheets client: Task 4.
  - QuoteService orchestration: Task 5.
  - CLI and container wiring: Task 6.
  - Valuation integration: Task 7.
  - Screening cache computation: Task 8.
  - Retry/status operations: Task 9.
  - Operator docs and verification: Tasks 10-11.
- Scope check: one cohesive feature. It touches several layers, but each task produces testable functionality and preserves existing Yahoo behavior.
- Type consistency:
  - Provider name is consistently `google_sheets`.
  - Latest quote natural key is `(company_id, provider)`.
  - `QuoteRequest`, `QuoteResult`, and `QuoteRefreshResult` are defined before use in service tasks.
  - `JobService` uses `quote_provider="google_sheets"` only for cached quote path and leaves existing Yahoo path available.
