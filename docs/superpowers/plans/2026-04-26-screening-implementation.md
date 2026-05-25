# Screening Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SEC universe (10-K / 20-F filers) を取り込み、Yahoo Finance から ScreeningCache を enrichment し、PER / PBR / ROE 等で filter / sort / distribution を行い analysis_targets へ送り込むバックエンド機能 (Service / Repository / JSON API / CLI / テスト) を実装する。Web UI (filter スライダー) は user 側別実装のため対象外。

**Architecture:** `ScreeningUniverseService` (write — SEC ingestion + Yahoo enrichment) と `ScreeningService` (read-only — filter / distribution / add-to-targets) の二層 service。ScreeningCache は既存 model、 BaseRepository.bulk_upsert + asyncio.Semaphore + per-ticker commit で部分失敗を隔離。 schema-driven な field whitelist で SQL injection を遮断。

**Tech Stack:** SQLAlchemy 2.x async / SQLite (sqlite_insert ON CONFLICT)、 `httpx` async (既存 BaseClient 経由)、 asyncio.Semaphore + asyncio.gather、 pytest + pytest-asyncio + AsyncMock、 FastAPI (既存 web routes パターン)、 argparse (既存 cli パターン)。

**前提:**
- spec: `docs/superpowers/specs/2026-04-26-screening-design.md`
- `infisical run` 経由で test 実行 (既存 `scripts/infisical-run` を使う)
- 1 task = 1 commit。 各 commit 末尾に `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` を入れる
- TDD: 各 task は (Red test → Green 実装 → Refactor / 緑保証 → Commit) を踏む

**ファイル構成 (新規 / 変更):**

```
新規:
  src/stock_analyze_system/services/screening.py            # ScreeningService (read)
  src/stock_analyze_system/services/screening_universe.py   # ScreeningUniverseService (write)
  src/stock_analyze_system/cli/screening.py                 # 新 CLI (旧 screen.py を完全置換)
  tests/fixtures/__init__.py                                # ない場合
  tests/fixtures/screening_universe.py                      # 16-ticker seeds
  tests/fixtures/sec_company_tickers_payload.py             # SEC mock payload
  tests/fixtures/yahoo_screening_responses.py               # Yahoo mock
  tests/unit/services/test_screening_service.py             # read-only service test
  tests/unit/services/test_screening_universe_service.py    # write service test
  tests/unit/web/test_screening_api.py                      # JSON API test
  tests/unit/cli/test_screening_cli.py                      # CLI test

変更:
  src/stock_analyze_system/repositories/screening.py        # list_eligible_for_enrich 追加
  src/stock_analyze_system/repositories/company.py          # find_existing_ids 追加
  src/stock_analyze_system/ingestion/sec_edgar.py           # list_universe 追加
  src/stock_analyze_system/cli/container.py                 # wiring を 2 service に
  src/stock_analyze_system/cli/app.py                       # screen → screening 切替
  src/stock_analyze_system/web/routes/screening.py          # placeholder → JSON router
  src/stock_analyze_system/web/app.py                       # router 配線確認
  src/stock_analyze_system/services/__init__.py             # 必要なら export
  src/stock_analyze_system/repositories/__init__.py         # 必要なら export
  tests/unit/repositories/test_other_repos.py               # repo 拡張 test 追記

削除:
  src/stock_analyze_system/cli/screen.py                    # 旧スタブ
  src/stock_analyze_system/web/templates/screening/placeholder.html  # 旧 placeholder
```

---

### Task 1: Test fixtures — universe seeds

**Goal:** 16 ticker の Company + ScreeningCache seed と SEC / Yahoo mock を提供。 後続 task すべての依存元。

**Files:**
- Create: `tests/fixtures/__init__.py` (空 file)
- Create: `tests/fixtures/screening_universe.py`
- Create: `tests/fixtures/sec_company_tickers_payload.py`
- Create: `tests/fixtures/yahoo_screening_responses.py`

- [ ] **Step 1: 空 `__init__.py` を作成**

```bash
mkdir -p tests/fixtures
touch tests/fixtures/__init__.py
```

- [ ] **Step 2: `screening_universe.py` を作成**

`tests/fixtures/screening_universe.py`:

```python
"""Screening test fixture — 16 ticker spanning ADR / 小型 / penny / 赤字 / NaN・inf 等."""
from __future__ import annotations

from typing import NamedTuple


class ScreenSeed(NamedTuple):
    company: dict          # Company 行 (insert 用)
    cache: dict | None     # ScreeningCache 行 (None = 未生成 = enrich 対象)


_NAN = float("nan")
_INF = float("inf")


def screening_universe_seeds() -> list[ScreenSeed]:
    """16 ticker 完全セット."""
    return [
        # 1. AAPL — 大型 US ベースライン
        ScreenSeed(
            company={
                "id": "US_AAPL", "ticker": "AAPL", "name": "Apple Inc",
                "market": "Nasdaq", "accounting_standard": "US-GAAP",
                "cik": "0000320193", "sector": "Technology",
            },
            cache={
                "stock_price": 232.0, "market_cap": 3.5e12,
                "trailing_per": 28.4, "eps": 6.5, "forward_per": 25.0,
                "pbr": 47.2, "psr": 8.0, "ev_ebitda": 22.0,
                "dividend_yield": 0.0044, "roe": 1.45,
                "operating_margin": 0.30, "net_margin": 0.25,
                "revenue_growth": 0.06, "earnings_growth": 0.10,
                "de_ratio": 1.5, "peg_ratio": 2.5, "fcf_yield": 0.034,
                "beta": 1.28, "volume": 52_000_000,
                "sector": "Technology", "industry": "Consumer Electronics",
                "exchange": "Nasdaq",
            },
        ),
        # 2. MSFT — 大型 US (sort 検証用、 mc=3.0T)
        ScreenSeed(
            company={
                "id": "US_MSFT", "ticker": "MSFT", "name": "Microsoft Corp",
                "market": "Nasdaq", "accounting_standard": "US-GAAP",
                "cik": "0000789019", "sector": "Technology",
            },
            cache={
                "stock_price": 410.0, "market_cap": 3.0e12,
                "trailing_per": 35.0, "eps": 11.7, "forward_per": 30.0,
                "pbr": 12.5, "psr": 13.0, "ev_ebitda": 24.0,
                "dividend_yield": 0.008, "roe": 0.36,
                "operating_margin": 0.42, "net_margin": 0.36,
                "revenue_growth": 0.16, "earnings_growth": 0.20,
                "de_ratio": 0.5, "peg_ratio": 2.0, "fcf_yield": 0.022,
                "beta": 0.95, "volume": 22_000_000,
                "sector": "Technology", "industry": "Software—Infrastructure",
                "exchange": "Nasdaq",
            },
        ),
        # 3. BRK-A — ticker ダッシュ、 multi-class 親、 high price
        ScreenSeed(
            company={
                "id": "US_BRK-A", "ticker": "BRK-A",
                "name": "BERKSHIRE HATHAWAY INC",
                "market": "NYSE", "accounting_standard": "US-GAAP",
                "cik": "0001067983", "sector": "Financial Services",
            },
            cache={
                "stock_price": 605_000.0, "market_cap": 8.7e11,
                "trailing_per": 9.5, "eps": 63_500.0, "forward_per": 22.0,
                "pbr": 1.6, "psr": 2.5, "ev_ebitda": 8.0,
                "dividend_yield": None, "roe": 0.12,
                "operating_margin": 0.08, "net_margin": 0.20,
                "revenue_growth": 0.02, "earnings_growth": 0.05,
                "de_ratio": 0.3, "peg_ratio": 1.9, "fcf_yield": 0.04,
                "beta": 0.85, "volume": 5_000,
                "sector": "Financial Services", "industry": "Insurance—Diversified",
                "exchange": "NYSE",
            },
        ),
        # 4. BRK-B — 同 CIK 別 ticker
        ScreenSeed(
            company={
                "id": "US_BRK-B", "ticker": "BRK-B",
                "name": "BERKSHIRE HATHAWAY INC",
                "market": "NYSE", "accounting_standard": "US-GAAP",
                "cik": "0001067983", "sector": "Financial Services",
            },
            cache={
                "stock_price": 403.0, "market_cap": 8.7e11,
                "trailing_per": 9.5, "eps": 42.4, "forward_per": 22.0,
                "pbr": 1.6, "psr": 2.5, "ev_ebitda": 8.0,
                "dividend_yield": None, "roe": 0.12,
                "operating_margin": 0.08, "net_margin": 0.20,
                "revenue_growth": 0.02, "earnings_growth": 0.05,
                "de_ratio": 0.3, "peg_ratio": 1.9, "fcf_yield": 0.04,
                "beta": 0.85, "volume": 4_000_000,
                "sector": "Financial Services", "industry": "Insurance—Diversified",
                "exchange": "NYSE",
            },
        ),
        # 5. GOOGL — dual class B
        ScreenSeed(
            company={
                "id": "US_GOOGL", "ticker": "GOOGL", "name": "Alphabet Inc",
                "market": "Nasdaq", "accounting_standard": "US-GAAP",
                "cik": "0001652044", "sector": "Communication Services",
            },
            cache={
                "stock_price": 175.0, "market_cap": 2.1e12,
                "trailing_per": 24.0, "eps": 7.3, "forward_per": 21.0,
                "pbr": 6.5, "psr": 6.0, "ev_ebitda": 18.0,
                "dividend_yield": 0.005, "roe": 0.30,
                "operating_margin": 0.30, "net_margin": 0.25,
                "revenue_growth": 0.13, "earnings_growth": 0.18,
                "de_ratio": 0.1, "peg_ratio": 1.6, "fcf_yield": 0.04,
                "beta": 1.05, "volume": 35_000_000,
                "sector": "Communication Services", "industry": "Internet Content & Information",
                "exchange": "Nasdaq",
            },
        ),
        # 6. GOOG — dual class C
        ScreenSeed(
            company={
                "id": "US_GOOG", "ticker": "GOOG", "name": "Alphabet Inc",
                "market": "Nasdaq", "accounting_standard": "US-GAAP",
                "cik": "0001652044", "sector": "Communication Services",
            },
            cache={
                "stock_price": 178.0, "market_cap": 2.1e12,
                "trailing_per": 24.5, "eps": 7.3, "forward_per": 21.5,
                "pbr": 6.5, "psr": 6.0, "ev_ebitda": 18.0,
                "dividend_yield": 0.005, "roe": 0.30,
                "operating_margin": 0.30, "net_margin": 0.25,
                "revenue_growth": 0.13, "earnings_growth": 0.18,
                "de_ratio": 0.1, "peg_ratio": 1.6, "fcf_yield": 0.04,
                "beta": 1.05, "volume": 30_000_000,
                "sector": "Communication Services", "industry": "Internet Content & Information",
                "exchange": "Nasdaq",
            },
        ),
        # 7. TSLA — 極端 PER / 高 beta
        ScreenSeed(
            company={
                "id": "US_TSLA", "ticker": "TSLA", "name": "Tesla Inc",
                "market": "Nasdaq", "accounting_standard": "US-GAAP",
                "cik": "0001318605", "sector": "Consumer Cyclical",
            },
            cache={
                "stock_price": 248.0, "market_cap": 7.9e11,
                "trailing_per": 215.0, "eps": 1.15, "forward_per": 95.0,
                "pbr": 12.0, "psr": 8.5, "ev_ebitda": 90.0,
                "dividend_yield": None, "roe": 0.15,
                "operating_margin": 0.07, "net_margin": 0.10,
                "revenue_growth": 0.18, "earnings_growth": 0.05,
                "de_ratio": 0.2, "peg_ratio": 8.0, "fcf_yield": 0.005,
                "beta": 2.4, "volume": 90_000_000,
                "sector": "Consumer Cyclical", "industry": "Auto Manufacturers",
                "exchange": "Nasdaq",
            },
        ),
        # 8. TSM — ADR 台湾 (IFRS、 上書き禁止 test 対象)
        ScreenSeed(
            company={
                "id": "US_TSM", "ticker": "TSM",
                "name": "Taiwan Semiconductor Manufacturing Co",
                "market": "NYSE", "accounting_standard": "IFRS",
                "cik": "0001046179", "sector": "Technology",
            },
            cache={
                "stock_price": 195.0, "market_cap": 1.0e12,
                "trailing_per": 28.0, "eps": 7.0, "forward_per": 24.0,
                "pbr": 7.0, "psr": 9.0, "ev_ebitda": 18.0,
                "dividend_yield": 0.012, "roe": 0.27,
                "operating_margin": 0.42, "net_margin": 0.38,
                "revenue_growth": 0.30, "earnings_growth": 0.40,
                "de_ratio": 0.3, "peg_ratio": 1.0, "fcf_yield": 0.025,
                "beta": 1.20, "volume": 12_000_000,
                "sector": "Technology", "industry": "Semiconductors",
                "exchange": "NYSE",
            },
        ),
        # 9. SAP — ADR ドイツ (IFRS)
        ScreenSeed(
            company={
                "id": "US_SAP", "ticker": "SAP", "name": "SAP SE",
                "market": "NYSE", "accounting_standard": "IFRS",
                "cik": "0001000184", "sector": "Technology",
            },
            cache={
                "stock_price": 230.0, "market_cap": 2.7e11,
                "trailing_per": 38.0, "eps": 6.0, "forward_per": 28.0,
                "pbr": 5.0, "psr": 6.5, "ev_ebitda": 22.0,
                "dividend_yield": 0.011, "roe": 0.16,
                "operating_margin": 0.18, "net_margin": 0.14,
                "revenue_growth": 0.10, "earnings_growth": 0.30,
                "de_ratio": 0.5, "peg_ratio": 1.5, "fcf_yield": 0.022,
                "beta": 1.10, "volume": 1_500_000,
                "sector": "Technology", "industry": "Software—Application",
                "exchange": "NYSE",
            },
        ),
        # 10. SONY — ADR 日本、 sector="技術" (unicode test)
        ScreenSeed(
            company={
                "id": "US_SONY", "ticker": "SONY", "name": "Sony Group Corp",
                "market": "NYSE", "accounting_standard": "IFRS",
                "cik": "0000313838", "sector": "Consumer Electronics",
            },
            cache={
                "stock_price": 90.0, "market_cap": 1.1e11,
                "trailing_per": 18.0, "eps": 5.0, "forward_per": 16.0,
                "pbr": 2.0, "psr": 1.5, "ev_ebitda": 8.0,
                "dividend_yield": 0.007, "roe": 0.13,
                "operating_margin": 0.10, "net_margin": 0.08,
                "revenue_growth": 0.05, "earnings_growth": 0.07,
                "de_ratio": 0.4, "peg_ratio": 2.5, "fcf_yield": 0.05,
                "beta": 1.0, "volume": 800_000,
                "sector": "技術", "industry": "Consumer Electronics",
                "exchange": "NYSE",
            },
        ),
        # 11. JPM — 銀行
        ScreenSeed(
            company={
                "id": "US_JPM", "ticker": "JPM", "name": "JPMorgan Chase & Co",
                "market": "NYSE", "accounting_standard": "US-GAAP",
                "cik": "0000019617", "sector": "Financial Services",
            },
            cache={
                "stock_price": 215.0, "market_cap": 6.2e11,
                "trailing_per": 12.0, "eps": 18.0, "forward_per": 11.5,
                "pbr": 2.0, "psr": 3.5, "ev_ebitda": None,
                "dividend_yield": 0.022, "roe": 0.18,
                "operating_margin": 0.40, "net_margin": 0.35,
                "revenue_growth": 0.08, "earnings_growth": 0.10,
                "de_ratio": 12.0, "peg_ratio": 1.2, "fcf_yield": 0.06,
                "beta": 1.10, "volume": 9_000_000,
                "sector": "Financial Services", "industry": "Banks—Diversified",
                "exchange": "NYSE",
            },
        ),
        # 12. O — REIT 高配当
        ScreenSeed(
            company={
                "id": "US_O", "ticker": "O", "name": "Realty Income Corp",
                "market": "NYSE", "accounting_standard": "US-GAAP",
                "cik": "0000726728", "sector": "Real Estate",
            },
            cache={
                "stock_price": 56.0, "market_cap": 5.0e10,
                "trailing_per": 50.0, "eps": 1.12, "forward_per": 35.0,
                "pbr": 1.3, "psr": 11.0, "ev_ebitda": 17.0,
                "dividend_yield": 0.058, "roe": 0.03,
                "operating_margin": 0.32, "net_margin": 0.22,
                "revenue_growth": 0.30, "earnings_growth": 0.0,
                "de_ratio": 0.7, "peg_ratio": None, "fcf_yield": 0.06,
                "beta": 0.85, "volume": 4_500_000,
                "sector": "Real Estate", "industry": "REIT—Retail",
                "exchange": "NYSE",
            },
        ),
        # 13. IZEA — 小型 (mc=18M)、 多くの null
        ScreenSeed(
            company={
                "id": "US_IZEA", "ticker": "IZEA",
                "name": "IZEA Worldwide Inc",
                "market": "Nasdaq", "accounting_standard": "US-GAAP",
                "cik": "0001495231", "sector": "Communication Services",
            },
            cache={
                "stock_price": 2.4, "market_cap": 1.8e7,
                "trailing_per": None, "eps": -0.8, "forward_per": None,
                "pbr": 0.5, "psr": 0.6, "ev_ebitda": None,
                "dividend_yield": None, "roe": -0.30,
                "operating_margin": -0.20, "net_margin": -0.18,
                "revenue_growth": -0.15, "earnings_growth": None,
                "de_ratio": None, "peg_ratio": None, "fcf_yield": None,
                "beta": 1.5, "volume": 50_000,
                "sector": "Communication Services", "industry": "Advertising Agencies",
                "exchange": "Nasdaq",
            },
        ),
        # 14. PLTR — 赤字 (trailing_per=None, roe=-0.12)
        ScreenSeed(
            company={
                "id": "US_PLTR", "ticker": "PLTR",
                "name": "Palantir Technologies Inc",
                "market": "NYSE", "accounting_standard": "US-GAAP",
                "cik": "0001321655", "sector": "Technology",
            },
            cache={
                "stock_price": 35.0, "market_cap": 8.0e10,
                "trailing_per": None, "eps": -0.05, "forward_per": 110.0,
                "pbr": 25.0, "psr": 35.0, "ev_ebitda": 200.0,
                "dividend_yield": None, "roe": -0.12,
                "operating_margin": -0.05, "net_margin": -0.08,
                "revenue_growth": 0.20, "earnings_growth": None,
                "de_ratio": 0.0, "peg_ratio": None, "fcf_yield": 0.005,
                "beta": 2.6, "volume": 50_000_000,
                "sector": "Technology", "industry": "Software—Infrastructure",
                "exchange": "NYSE",
            },
        ),
        # 15. CETX — penny、 NaN / inf 注入
        ScreenSeed(
            company={
                "id": "US_CETX", "ticker": "CETX",
                "name": "Cemtrex Inc",
                "market": "Nasdaq", "accounting_standard": "US-GAAP",
                "cik": "0001435064", "sector": "Industrials",
            },
            cache={
                "stock_price": 0.42, "market_cap": 1.2e6,
                "trailing_per": None, "eps": -0.6, "forward_per": None,
                "pbr": _NAN, "psr": _INF, "ev_ebitda": None,
                "dividend_yield": None, "roe": -1.5,
                "operating_margin": -0.40, "net_margin": -0.55,
                "revenue_growth": -0.30, "earnings_growth": None,
                "de_ratio": _INF, "peg_ratio": None, "fcf_yield": None,
                "beta": 3.5, "volume": 12_000,
                "sector": "Industrials", "industry": "Electronic Components",
                "exchange": "Nasdaq",
            },
        ),
        # 16. DEFUNCT — ticker None で enrich skip、 universe overwrite 禁止
        ScreenSeed(
            company={
                "id": "US_DEFUNCT", "ticker": None,
                "name": "Defunct Holdings Inc",
                "market": "DELISTED", "accounting_standard": "US-GAAP",
                "cik": "0009999999", "sector": None,
            },
            cache=None,
        ),
    ]


def aapl_seed() -> ScreenSeed:
    return screening_universe_seeds()[0]


def adr_seeds() -> list[ScreenSeed]:
    """#8 TSM, #9 SAP, #10 SONY (IFRS)."""
    return screening_universe_seeds()[7:10]


def edge_value_seeds() -> list[ScreenSeed]:
    """#13 IZEA, #14 PLTR, #15 CETX (null / 負値 / NaN・inf)."""
    return screening_universe_seeds()[12:15]


def delisted_seed() -> ScreenSeed:
    """#16 DEFUNCT."""
    return screening_universe_seeds()[15]
```

- [ ] **Step 3: `sec_company_tickers_payload.py` を作成**

`tests/fixtures/sec_company_tickers_payload.py`:

```python
"""SEC company_tickers_exchange.json mock payload — universe registration test 用."""
from __future__ import annotations


def sec_universe_payload() -> dict:
    """16 ticker (DEFUNCT 除く 15) + 異常 4 entry を含む payload.

    SEC actual response shape:
        {"fields": ["cik", "name", "ticker", "exchange"], "data": [[...], ...]}
    """
    rows = [
        # ── universe seeds (DEFUNCT 除く 15) ──
        [320193,    "Apple Inc",                              "AAPL",  "Nasdaq"],
        [789019,    "Microsoft Corp",                         "MSFT",  "Nasdaq"],
        [1067983,   "BERKSHIRE HATHAWAY INC",                 "BRK-A", "NYSE"],
        [1067983,   "BERKSHIRE HATHAWAY INC",                 "BRK-B", "NYSE"],   # 同 CIK
        [1652044,   "Alphabet Inc",                           "GOOGL", "Nasdaq"],
        [1652044,   "Alphabet Inc",                           "GOOG",  "Nasdaq"], # 同 CIK
        [1318605,   "Tesla Inc",                              "TSLA",  "Nasdaq"],
        [1046179,   "Taiwan Semiconductor Manufacturing Co",  "TSM",   "NYSE"],
        [1000184,   "SAP SE",                                 "SAP",   "NYSE"],
        [313838,    "Sony Group Corp",                        "SONY",  "NYSE"],
        [19617,     "JPMorgan Chase & Co",                    "JPM",   "NYSE"],
        [726728,    "Realty Income Corp",                     "O",     "NYSE"],
        [1495231,   "IZEA Worldwide Inc",                     "IZEA",  "Nasdaq"],
        [1321655,   "Palantir Technologies Inc",              "PLTR",  "NYSE"],
        [1435064,   "Cemtrex Inc",                            "CETX",  "Nasdaq"],
        # ── 異常 4 entry ──
        [9999000,   "Empty Ticker Co",                        "",      "Nasdaq"], # ticker 空 → skip + warn
        [9999001,   "",                                       "EMTNAM","NYSE"],   # name 空 → skip + warn
        [9999002,   "Unknown Exchange Co",                    "UNKEX", ""],       # exchange 空 → market=UNKNOWN
        [9999003,   "Empty Both",                             "",      ""],       # 両方空 → skip + warn
    ]
    return {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": rows,
    }


def sec_universe_payload_minimal() -> dict:
    """最小 payload (test の 1 ticker upsert 確認用)."""
    return {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[320193, "Apple Inc", "AAPL", "Nasdaq"]],
    }
```

- [ ] **Step 4: `yahoo_screening_responses.py` を作成**

`tests/fixtures/yahoo_screening_responses.py`:

```python
"""Yahoo Finance get_screening_info() mock response — enrich test 用."""
from __future__ import annotations

import httpx

_NAN = float("nan")
_INF = float("inf")


def yahoo_full_response(ticker: str) -> dict:
    """完全 dict (18 numeric + 3 categorical を全て埋める)."""
    return {
        "stock_price": 232.0, "market_cap": 3.5e12,
        "trailing_per": 28.4, "eps": 6.5, "forward_per": 25.0,
        "pbr": 47.2, "psr": 8.0, "ev_ebitda": 22.0,
        "dividend_yield": 0.0044, "roe": 1.45,
        "operating_margin": 0.30, "net_margin": 0.25,
        "revenue_growth": 0.06, "earnings_growth": 0.10,
        "de_ratio": 1.5, "peg_ratio": 2.5, "fcf_yield": 0.034,
        "beta": 1.28, "volume": 52_000_000,
        "sector": "Technology", "industry": "Consumer Electronics",
        "exchange": "Nasdaq",
    }


def yahoo_high_dividend_response() -> dict:
    return {**yahoo_full_response("O"), "dividend_yield": 0.058, "sector": "Real Estate"}


def yahoo_partial_null_response() -> dict:
    """半数の field が None (IZEA 想定)."""
    return {
        "stock_price": 2.4, "market_cap": 1.8e7,
        "trailing_per": None, "eps": -0.8, "forward_per": None,
        "pbr": 0.5, "psr": 0.6, "ev_ebitda": None,
        "dividend_yield": None, "roe": -0.30,
        "operating_margin": -0.20, "net_margin": -0.18,
        "revenue_growth": -0.15, "earnings_growth": None,
        "de_ratio": None, "peg_ratio": None, "fcf_yield": None,
        "beta": 1.5, "volume": 50_000,
        "sector": "Communication Services", "industry": "Advertising Agencies",
        "exchange": "Nasdaq",
    }


def yahoo_negative_roe_response() -> dict:
    """PLTR 想定 — trailing_per=None, roe=-0.12."""
    return {
        **yahoo_full_response("PLTR"),
        "trailing_per": None, "eps": -0.05, "roe": -0.12,
    }


def yahoo_nan_inf_response() -> dict:
    """CETX 想定 — pbr=NaN, psr=inf を注入."""
    base = yahoo_full_response("CETX")
    base.update({"pbr": _NAN, "psr": _INF, "de_ratio": _INF})
    return base


def yahoo_timeout_side_effect():
    """ticker fetch を timeout で raise させる side_effect."""
    return httpx.ReadTimeout("read timeout")


def yahoo_ratelimit_side_effect():
    """ticker fetch を 429 で raise させる side_effect."""
    request = httpx.Request("GET", "https://example/")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError(
        "429 Too Many Requests",
        request=request,
        response=response,
    )
```

- [ ] **Step 5: import smoke (構文チェックのみ)**

Run:
```
scripts/infisical-run uv run python -c "from tests.fixtures import screening_universe, sec_company_tickers_payload, yahoo_screening_responses; print(len(screening_universe.screening_universe_seeds()))"
```
Expected: `16`

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/__init__.py tests/fixtures/screening_universe.py tests/fixtures/sec_company_tickers_payload.py tests/fixtures/yahoo_screening_responses.py
git commit -m "$(cat <<'EOF'
test(fixtures): add screening universe seeds + SEC/Yahoo mocks

16-ticker fixture (ADR / 小型 / penny / 赤字 / NaN・inf / DELISTED) と
SEC company_tickers_exchange.json 模擬 payload (異常 4 entry 含む)、
Yahoo get_screening_info() 戻り値 (完全 / partial null / 負 ROE / NaN+inf /
timeout / rate limit) を tests/fixtures/ 配下に追加。 後続 task の依存元。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Repository extensions

**Goal:** `ScreeningRepository.list_eligible_for_enrich` (enrich 対象選定 LEFT JOIN クエリ) と `CompanyRepository.find_existing_ids` (id 存在 set) を TDD で追加。

**Files:**
- Modify: `src/stock_analyze_system/repositories/screening.py`
- Modify: `src/stock_analyze_system/repositories/company.py`
- Modify: `tests/unit/repositories/test_other_repos.py`

- [ ] **Step 1: 既存 test ファイルを確認**

```
grep -n 'class Test\|test_screen' tests/unit/repositories/test_other_repos.py | head
```
Expected: 既存 `test_screening_*` クラスが見える (既存 ScreeningRepository test 群)。

- [ ] **Step 2: 失敗テストを追加 — `list_eligible_for_enrich` for "未登録 + ticker not None"**

`tests/unit/repositories/test_other_repos.py` 末尾に追記:

```python
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.repositories.company import CompanyRepository


class TestScreeningRepositoryEligible:
    @pytest.mark.asyncio
    async def test_lists_companies_without_cache_excluding_ticker_none(self, session):
        """ScreeningCache 未登録 かつ ticker not NULL の company を返す."""
        session.add_all([
            Company(id="US_AAPL", ticker="AAPL", name="Apple",
                    market="Nasdaq", accounting_standard="US-GAAP"),
            Company(id="US_MSFT", ticker="MSFT", name="MS",
                    market="Nasdaq", accounting_standard="US-GAAP"),
            Company(id="US_DEFUNCT", ticker=None, name="Def",
                    market="DELISTED", accounting_standard="US-GAAP"),
        ])
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=24, limit=None)

        ids = sorted([cid for cid, _ in eligible])
        assert ids == ["US_AAPL", "US_MSFT"]

    @pytest.mark.asyncio
    async def test_lists_stale_cache_rows(self, session):
        """updated_at が stale_hours 超過の cache は eligible."""
        session.add(Company(id="US_AAPL", ticker="AAPL", name="Apple",
                            market="Nasdaq", accounting_standard="US-GAAP"))
        session.add(Company(id="US_MSFT", ticker="MSFT", name="MS",
                            market="Nasdaq", accounting_standard="US-GAAP"))
        await session.flush()
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        fresh = datetime.now(timezone.utc) - timedelta(hours=1)
        session.add(ScreeningCache(company_id="US_AAPL", updated_at=old))
        session.add(ScreeningCache(company_id="US_MSFT", updated_at=fresh))
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=24, limit=None)

        ids = [cid for cid, _ in eligible]
        assert ids == ["US_AAPL"]

    @pytest.mark.asyncio
    async def test_stale_hours_none_returns_all_with_ticker(self, session):
        """stale_hours=None で全件 (キャッシュ存在問わず) eligible."""
        session.add(Company(id="US_AAPL", ticker="AAPL", name="Apple",
                            market="Nasdaq", accounting_standard="US-GAAP"))
        await session.flush()
        session.add(ScreeningCache(
            company_id="US_AAPL",
            updated_at=datetime.now(timezone.utc),
        ))
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=None, limit=None)

        assert [cid for cid, _ in eligible] == ["US_AAPL"]

    @pytest.mark.asyncio
    async def test_limit_truncates_eligible_set(self, session):
        for i in range(5):
            session.add(Company(
                id=f"US_T{i}", ticker=f"T{i}", name=f"T{i}",
                market="Nasdaq", accounting_standard="US-GAAP",
            ))
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=24, limit=2)

        assert len(eligible) == 2


class TestCompanyRepositoryFindExistingIds:
    @pytest.mark.asyncio
    async def test_returns_set_of_existing_ids(self, session):
        session.add_all([
            Company(id="US_AAPL", ticker="AAPL", name="Apple",
                    market="Nasdaq", accounting_standard="US-GAAP"),
            Company(id="US_MSFT", ticker="MSFT", name="MS",
                    market="Nasdaq", accounting_standard="US-GAAP"),
        ])
        await session.flush()

        repo = CompanyRepository(session)
        result = await repo.find_existing_ids(["US_AAPL", "US_MSFT", "US_NOPE"])

        assert result == {"US_AAPL", "US_MSFT"}

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_set(self, session):
        repo = CompanyRepository(session)
        result = await repo.find_existing_ids([])
        assert result == set()
```

- [ ] **Step 3: テストを実行 — 失敗確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/repositories/test_other_repos.py::TestScreeningRepositoryEligible tests/unit/repositories/test_other_repos.py::TestCompanyRepositoryFindExistingIds -v
```
Expected: 全 6 件が `AttributeError: 'ScreeningRepository' object has no attribute 'list_eligible_for_enrich'` または `find_existing_ids` で fail。

- [ ] **Step 4: `ScreeningRepository.list_eligible_for_enrich` を実装**

`src/stock_analyze_system/repositories/screening.py` の末尾に追加 (既存 imports 済の `select`, `datetime`, `timedelta`, `timezone` を流用):

```python
    async def list_eligible_for_enrich(
        self,
        stale_hours: int | None,
        limit: int | None,
    ) -> list[tuple[str, str]]:
        """enrich 対象 (cache 未登録 OR cache.updated_at < cutoff) の (company_id, ticker) 一覧.

        Args:
            stale_hours: cache が古いとみなす時間 (hour)。 None なら全件 eligible
                (キャッシュ存在問わず再取得モード)。
            limit: 返却件数の上限。 None なら全件。

        Returns:
            ticker IS NOT NULL に限定した [(company_id, ticker), ...]。
        """
        from stock_analyze_system.models.company import Company

        cutoff: datetime | None
        if stale_hours is None:
            cutoff = None
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)

        stmt = (
            select(Company.id, Company.ticker)
            .outerjoin(ScreeningCache, Company.id == ScreeningCache.company_id)
            .where(Company.ticker.is_not(None))
        )
        if cutoff is not None:
            stmt = stmt.where(
                (ScreeningCache.company_id.is_(None))
                | (ScreeningCache.updated_at < cutoff),
            )
        stmt = stmt.order_by(Company.id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [(row.id, row.ticker) for row in result]
```

- [ ] **Step 5: `CompanyRepository.find_existing_ids` を実装**

`src/stock_analyze_system/repositories/company.py` の末尾に追加:

```python
    async def find_existing_ids(self, ids: list[str]) -> set[str]:
        """与えた id の中で companies に実在する id を set で返す.

        Used by ScreeningService.add_to_targets to count `skipped` ids that
        do not correspond to a real company.
        """
        if not ids:
            return set()
        stmt = select(Company.id).where(Company.id.in_(ids))
        result = await self._session.execute(stmt)
        return set(result.scalars().all())
```

- [ ] **Step 6: テストを実行 — 緑確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/repositories/test_other_repos.py -q
```
Expected: 全件 PASSED (新規 6 件 + 既存)。

- [ ] **Step 7: ruff / 型チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/repositories/screening.py src/stock_analyze_system/repositories/company.py
```
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add src/stock_analyze_system/repositories/screening.py src/stock_analyze_system/repositories/company.py tests/unit/repositories/test_other_repos.py
git commit -m "$(cat <<'EOF'
feat(repositories): add list_eligible_for_enrich + find_existing_ids

ScreeningRepository.list_eligible_for_enrich は ScreeningCache LEFT JOIN
で「未登録 OR stale」 + ticker not NULL の (company_id, ticker) を 1 query
で返す。 stale_hours=None は cutoff 無効化で全件 eligible モード。

CompanyRepository.find_existing_ids は id 集合 → 実在する id の set を
1 SELECT IN(...) query で返す。 ScreeningService.add_to_targets の
skipped 計上に使う。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: SEC `list_universe()` + ScreeningUniverseService.refresh_universe

**Goal:** SEC `company_tickers_exchange.json` を fetch し、 companies テーブルへ bulk upsert する。 `accounting_standard` は新規 insert 時のみ default、 既存行は触らない。

**Files:**
- Modify: `src/stock_analyze_system/ingestion/sec_edgar.py`
- Create: `src/stock_analyze_system/services/screening_universe.py`
- Create: `tests/unit/services/test_screening_universe_service.py`

- [ ] **Step 1: `SecEdgarClient.list_universe()` 失敗テストを追加**

`tests/unit/ingestion/test_sec_edgar.py` (既存 file) に追記、 もしくは無ければ作成:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
from tests.fixtures.sec_company_tickers_payload import sec_universe_payload


class TestSecEdgarListUniverse:
    @pytest.mark.asyncio
    async def test_returns_normalized_entries(self):
        client = SecEdgarClient(email="t@e.com")
        fake_resp = MagicMock()
        fake_resp.json = MagicMock(return_value=sec_universe_payload())
        with patch.object(client, "_get", AsyncMock(return_value=fake_resp)):
            entries = await client.list_universe()

        # 18 rows total in fixture (15 normal + 3 anomalies; "EMTNAM" name="" and 9999003 both empty also returned raw)
        assert len(entries) >= 15
        # cik must be 10-digit zero-padded string
        sample = next(e for e in entries if e["ticker"] == "AAPL")
        assert sample["cik"] == "0000320193"
        assert sample["exchange"] == "Nasdaq"
        assert sample["name"] == "Apple Inc"

    @pytest.mark.asyncio
    async def test_uses_company_tickers_exchange_endpoint(self):
        client = SecEdgarClient(email="t@e.com")
        fake_resp = MagicMock()
        fake_resp.json = MagicMock(return_value={"fields": ["cik","name","ticker","exchange"], "data": []})
        with patch.object(client, "_get", AsyncMock(return_value=fake_resp)) as get:
            await client.list_universe()
        called_url = get.call_args[0][0]
        assert called_url == "https://www.sec.gov/files/company_tickers_exchange.json"
```

- [ ] **Step 2: テストを実行 — 失敗確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/ingestion/test_sec_edgar.py::TestSecEdgarListUniverse -v
```
Expected: `AttributeError: 'SecEdgarClient' object has no attribute 'list_universe'` で fail。

- [ ] **Step 3: `SecEdgarClient.list_universe()` を実装**

`src/stock_analyze_system/ingestion/sec_edgar.py` の冒頭定数に追加:

```python
_COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
```

メソッド本体を追加 (既存 `_get` を流用):

```python
    async def list_universe(self) -> list[dict]:
        """SEC 全 ticker (10-K/20-F filer) の (ticker, cik, name, exchange) を返す.

        Source: https://www.sec.gov/files/company_tickers_exchange.json
        cik は 10 桁 zero-padded で正規化する。
        """
        resp = await self._get(_COMPANY_TICKERS_EXCHANGE_URL)
        payload = resp.json()
        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        idx = {f: i for i, f in enumerate(fields)}
        out: list[dict] = []
        for row in rows:
            cik_raw = row[idx["cik"]]
            out.append({
                "ticker": str(row[idx["ticker"]] or ""),
                "cik": f"{int(cik_raw):010d}",
                "name": str(row[idx["name"]] or ""),
                "exchange": str(row[idx["exchange"]] or ""),
            })
        return out
```

- [ ] **Step 4: テストを実行 — 緑確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/ingestion/test_sec_edgar.py::TestSecEdgarListUniverse -v
```
Expected: 2 PASSED。

- [ ] **Step 5: `services/screening_universe.py` の枠 + RefreshUniverseResult**

`src/stock_analyze_system/services/screening_universe.py` を新規作成:

```python
"""Screening universe / enrichment write service."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository

logger = logging.getLogger(__name__)


@dataclass
class RefreshUniverseResult:
    fetched: int
    inserted: int
    updated: int
    skipped: int


@dataclass
class EnrichResult:
    eligible: int
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    elapsed_seconds: float


class ScreeningUniverseService:
    """SEC universe ingestion + Yahoo enrichment (write 系)."""

    def __init__(
        self,
        screening_repo: ScreeningRepository,
        company_repo: CompanyRepository,
        sec_client: SecEdgarClient,
        yahoo_client: YahooFinanceClient,
    ):
        self._screening_repo = screening_repo
        self._company_repo = company_repo
        self._sec = sec_client
        self._yahoo = yahoo_client
```

- [ ] **Step 6: 失敗テストを追加 — `refresh_universe` 正常系 + skip + 上書き禁止**

`tests/unit/services/test_screening_universe_service.py` を新規作成:

```python
"""ScreeningUniverseService の単体テスト."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.screening_universe import (
    ScreeningUniverseService,
)
from tests.fixtures.sec_company_tickers_payload import sec_universe_payload


@pytest.fixture
def sec_client():
    c = MagicMock()
    c.list_universe = AsyncMock(return_value=[
        {"ticker": e["ticker"], "cik": e["cik"], "name": e["name"], "exchange": e["exchange"]}
        for e in _normalize_payload(sec_universe_payload())
    ])
    return c


@pytest.fixture
def yahoo_client():
    c = MagicMock()
    c.get_screening_info = AsyncMock(return_value=None)
    return c


def _normalize_payload(payload: dict) -> list[dict]:
    fields = payload["fields"]
    idx = {f: i for i, f in enumerate(fields)}
    out = []
    for row in payload["data"]:
        out.append({
            "ticker": str(row[idx["ticker"]] or ""),
            "cik": f"{int(row[idx['cik']]):010d}",
            "name": str(row[idx["name"]] or ""),
            "exchange": str(row[idx["exchange"]] or ""),
        })
    return out


class TestRefreshUniverse:
    @pytest.mark.asyncio
    async def test_inserts_new_companies(self, session, sec_client, yahoo_client):
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        result = await svc.refresh_universe()

        assert result.fetched >= 18    # 15 + 3 anomalies that pass through (1 skipped is 9999003)
        assert result.inserted >= 15   # at least 15 normal entries
        assert result.skipped >= 2     # ticker="" and name="" rows
        # AAPL must exist
        co = await session.get(Company, "US_AAPL")
        assert co is not None
        assert co.ticker == "AAPL"
        assert co.market == "Nasdaq"
        assert co.accounting_standard == "US-GAAP"

    @pytest.mark.asyncio
    async def test_inserts_unknown_exchange_as_UNKNOWN(self, session, sec_client, yahoo_client):
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        await svc.refresh_universe()
        co = await session.get(Company, "US_UNKEX")
        assert co is not None
        assert co.market == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_accounting_standard(
        self, session, sec_client, yahoo_client,
    ):
        # 既存 TSM が IFRS で登録されている前提
        session.add(Company(
            id="US_TSM", ticker="TSM",
            name="OLD NAME",  # name は更新されることを併せて確認
            market="OLD_MARKET",
            accounting_standard="IFRS",
            cik="0001046179",
        ))
        await session.flush()

        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        await svc.refresh_universe()
        await session.refresh(await session.get(Company, "US_TSM"))
        co = await session.get(Company, "US_TSM")
        assert co.accounting_standard == "IFRS"   # 上書きされていない
        assert co.name == "Taiwan Semiconductor Manufacturing Co"  # 更新されている
        assert co.market == "NYSE"                  # 更新されている

    @pytest.mark.asyncio
    async def test_idempotent_second_call_inserts_nothing(
        self, session, sec_client, yahoo_client,
    ):
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        first = await svc.refresh_universe()
        second = await svc.refresh_universe()
        assert second.inserted == 0
        assert second.fetched == first.fetched
```

- [ ] **Step 7: テストを実行 — 失敗確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_universe_service.py::TestRefreshUniverse -v
```
Expected: `AttributeError: 'ScreeningUniverseService' object has no attribute 'refresh_universe'` で fail。

- [ ] **Step 8: `refresh_universe()` を実装**

`src/stock_analyze_system/services/screening_universe.py` の `ScreeningUniverseService` クラス内に追加:

```python
    async def refresh_universe(self) -> RefreshUniverseResult:
        """SEC company_tickers_exchange.json を取り込み companies へ bulk upsert.

        既存行の `accounting_standard` は上書きしない (新規 insert 時のみ default
        US-GAAP を入れる)。 ticker/name 空 entry は skip + warn。
        """
        entries = await self._sec.list_universe()
        existing_ids = await self._company_repo.find_existing_ids(
            [self._make_id(e) for e in entries if e["ticker"]],
        )
        rows_insert: list[dict] = []
        rows_update: list[dict] = []
        skipped = 0
        seen_ids: set[str] = set()
        for entry in entries:
            ticker = (entry.get("ticker") or "").strip()
            name = (entry.get("name") or "").strip()
            if not ticker or not name:
                logger.warning(
                    "screening universe: skip entry ticker=%r name=%r cik=%s",
                    ticker, name, entry.get("cik"),
                )
                skipped += 1
                continue
            cid = self._make_id(entry)
            if cid in seen_ids:
                # 同 SEC payload 内の重複は無視
                continue
            seen_ids.add(cid)
            row = {
                "id": cid,
                "ticker": ticker.upper(),
                "name": name,
                "market": (entry.get("exchange") or "UNKNOWN") or "UNKNOWN",
                "cik": entry.get("cik"),
            }
            if cid in existing_ids:
                rows_update.append(row)
            else:
                row["accounting_standard"] = "US-GAAP"
                rows_insert.append(row)

        if rows_insert:
            await self._company_repo._bulk_upsert_native(
                rows_insert,
                index_elements=["id"],
                update_columns=[],   # insert-only (既存衝突は ON CONFLICT DO NOTHING)
            )
        if rows_update:
            await self._company_repo._bulk_upsert_native(
                rows_update,
                index_elements=["id"],
                update_columns=["ticker", "name", "market", "cik"],
            )
        await self._screening_repo._session.commit()

        return RefreshUniverseResult(
            fetched=len(entries),
            inserted=len(rows_insert),
            updated=len(rows_update),
            skipped=skipped,
        )

    @staticmethod
    def _make_id(entry: dict) -> str:
        return f"US_{(entry.get('ticker') or '').upper().strip()}"
```

- [ ] **Step 9: テストを実行 — 緑確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_universe_service.py::TestRefreshUniverse -v
```
Expected: 4 PASSED。

- [ ] **Step 10: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/screening_universe.py src/stock_analyze_system/ingestion/sec_edgar.py
```
Expected: `All checks passed!`

- [ ] **Step 11: Commit**

```bash
git add src/stock_analyze_system/ingestion/sec_edgar.py src/stock_analyze_system/services/screening_universe.py tests/unit/ingestion/test_sec_edgar.py tests/unit/services/test_screening_universe_service.py
git commit -m "$(cat <<'EOF'
feat(screening): add SecEdgarClient.list_universe + refresh_universe

SecEdgarClient.list_universe は company_tickers_exchange.json を 1 fetch して
{ticker, cik(10桁zero-pad), name, exchange} のリストを返す。

ScreeningUniverseService.refresh_universe は SEC 取り込み → companies テーブルへ
bulk upsert する。 既存行の accounting_standard は変更しない (新規 insert 時のみ
US-GAAP を default 設定)。 ticker / name 空 entry は skip + warn。
2 回目実行は inserted=0 で冪等。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: ScreeningUniverseService.enrich_with_yahoo

**Goal:** Semaphore で並列 fetch、 1 ticker 失敗を warn + skip で隔離。 stale_hours=None / 0 / N の挙動を網羅。

**Files:**
- Modify: `src/stock_analyze_system/services/screening_universe.py`
- Modify: `tests/unit/services/test_screening_universe_service.py`

- [ ] **Step 1: 失敗テスト群を追加**

`tests/unit/services/test_screening_universe_service.py` 末尾に追記:

```python
import asyncio
from unittest.mock import call

from stock_analyze_system.models.screening import ScreeningCache
from tests.fixtures.yahoo_screening_responses import (
    yahoo_full_response,
    yahoo_partial_null_response,
    yahoo_timeout_side_effect,
    yahoo_ratelimit_side_effect,
)


def _seed_company(session, id, ticker):
    session.add(Company(
        id=id, ticker=ticker, name=ticker,
        market="Nasdaq", accounting_standard="US-GAAP",
    ))


class TestEnrichWithYahoo:
    @pytest.mark.asyncio
    async def test_fills_all_fields_from_full_response(self, session):
        _seed_company(session, "US_AAPL", "AAPL")
        await session.flush()

        yahoo = MagicMock()
        yahoo.get_screening_info = AsyncMock(return_value=yahoo_full_response("AAPL"))
        sec = MagicMock()
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec,
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24, limit=None,
                                             max_concurrency=4)

        assert result.attempted == 1
        assert result.succeeded == 1
        cache = await session.get(ScreeningCache, "US_AAPL")
        assert cache is not None
        assert cache.trailing_per == 28.4
        assert cache.roe == 1.45
        assert cache.market_cap == 3.5e12
        assert cache.sector == "Technology"
        assert cache.exchange == "Nasdaq"

    @pytest.mark.asyncio
    async def test_one_ticker_raise_others_continue(self, session):
        for tk in ("AAPL", "MSFT", "FAIL", "TSLA", "JPM"):
            _seed_company(session, f"US_{tk}", tk)
        await session.flush()

        async def yahoo_side_effect(ticker):
            if ticker == "FAIL":
                raise yahoo_timeout_side_effect()
            return yahoo_full_response(ticker)

        yahoo = MagicMock()
        yahoo.get_screening_info = AsyncMock(side_effect=yahoo_side_effect)
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24, max_concurrency=2)

        assert result.attempted == 5
        assert result.succeeded == 4
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_yahoo_returns_none_increments_skipped(self, session):
        _seed_company(session, "US_EMPTY", "EMPTY")
        await session.flush()
        yahoo = MagicMock()
        yahoo.get_screening_info = AsyncMock(return_value=None)
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.skipped == 1
        assert result.succeeded == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_warning_log_carries_exc_info(self, session, caplog):
        _seed_company(session, "US_RL", "RL")
        await session.flush()
        yahoo = MagicMock()
        yahoo.get_screening_info = AsyncMock(side_effect=yahoo_ratelimit_side_effect())
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        with caplog.at_level("WARNING",
                             logger="stock_analyze_system.services.screening_universe"):
            await svc.enrich_with_yahoo(stale_hours=24)
        warns = [r for r in caplog.records if r.levelname == "WARNING"
                 and "RL" in r.getMessage()]
        assert warns
        assert warns[0].exc_info is not None

    @pytest.mark.asyncio
    async def test_excludes_ticker_none_companies(self, session):
        _seed_company(session, "US_AAPL", "AAPL")
        session.add(Company(id="US_DEFUNCT", ticker=None, name="Def",
                            market="DELISTED", accounting_standard="US-GAAP"))
        await session.flush()
        yahoo = MagicMock()
        yahoo.get_screening_info = AsyncMock(return_value=yahoo_full_response("AAPL"))
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.attempted == 1   # DEFUNCT は eligible に出ない
        # mock が AAPL のみで呼ばれたことを確認
        assert yahoo.get_screening_info.await_count == 1

    @pytest.mark.asyncio
    async def test_limit_truncates_attempted(self, session):
        for i in range(5):
            _seed_company(session, f"US_T{i}", f"T{i}")
        await session.flush()
        yahoo = MagicMock()
        yahoo.get_screening_info = AsyncMock(return_value=yahoo_full_response("T"))
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24, limit=3)
        assert result.attempted == 3

    @pytest.mark.asyncio
    async def test_respects_max_concurrency(self, session):
        for i in range(8):
            _seed_company(session, f"US_T{i}", f"T{i}")
        await session.flush()

        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def fake(ticker):
            nonlocal in_flight, peak
            async with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            async with lock:
                in_flight -= 1
            return yahoo_full_response(ticker)

        yahoo = MagicMock()
        yahoo.get_screening_info = AsyncMock(side_effect=fake)
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        await svc.enrich_with_yahoo(stale_hours=24, max_concurrency=2)
        assert peak <= 2
        assert peak >= 1
```

- [ ] **Step 2: テストを実行 — 失敗確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_universe_service.py::TestEnrichWithYahoo -v
```
Expected: 全件 `AttributeError: 'ScreeningUniverseService' object has no attribute 'enrich_with_yahoo'`。

- [ ] **Step 3: `enrich_with_yahoo()` を実装**

`src/stock_analyze_system/services/screening_universe.py` のクラス内に追加:

```python
    async def enrich_with_yahoo(
        self,
        limit: int | None = None,
        stale_hours: int | None = 24,
        max_concurrency: int = 8,
    ) -> EnrichResult:
        """eligible 全件 (cache 未登録 OR stale) の ScreeningCache を Yahoo で更新.

        - max_concurrency で同時 in-flight を絞る (Yahoo per-call rate limit と独立)
        - 1 ticker 失敗は warn + skip。 上位処理は止めない (R7 パターン)
        - Yahoo が None / 空 dict を返した ticker は skipped カウント
        - 各 ticker = 1 commit で隔離 (中断しても先行分は永続化)
        """
        eligible = await self._screening_repo.list_eligible_for_enrich(
            stale_hours=stale_hours, limit=limit,
        )
        sem = asyncio.Semaphore(max_concurrency)
        succeeded = failed = skipped = 0
        succ_lock = asyncio.Lock()
        logger.info(
            "enrich start: eligible=%d limit=%s concurrency=%d",
            len(eligible), limit, max_concurrency,
        )
        t0 = time.perf_counter()

        async def _one(company_id: str, ticker: str) -> None:
            nonlocal succeeded, failed, skipped
            async with sem:
                try:
                    data = await self._yahoo.get_screening_info(ticker)
                except Exception as exc:  # noqa: BLE001 (R7: warn + 続行)
                    logger.warning(
                        "yahoo enrich %s failed: %s", ticker, exc, exc_info=exc,
                    )
                    async with succ_lock:
                        failed += 1
                    return
                if not data:
                    async with succ_lock:
                        skipped += 1
                    return
                try:
                    await self._screening_repo.upsert_cache(company_id, data)
                    await self._screening_repo._session.commit()
                except Exception as exc:  # noqa: BLE001
                    await self._screening_repo._session.rollback()
                    logger.warning(
                        "screening cache upsert %s failed: %s",
                        company_id, exc, exc_info=exc,
                    )
                    async with succ_lock:
                        failed += 1
                    return
                async with succ_lock:
                    succeeded += 1

        await asyncio.gather(*[_one(cid, tk) for cid, tk in eligible])
        elapsed = time.perf_counter() - t0
        logger.info(
            "enrich done: succeeded=%d failed=%d skipped=%d elapsed=%.2fs",
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

- [ ] **Step 4: テストを実行 — 緑確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_universe_service.py -q
```
Expected: 全件 PASSED (Task 3 + Task 4 合算)。

- [ ] **Step 5: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/screening_universe.py
```
Expected: clean。

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/services/screening_universe.py tests/unit/services/test_screening_universe_service.py
git commit -m "$(cat <<'EOF'
feat(screening): add enrich_with_yahoo with semaphore + per-ticker commit

ScreeningUniverseService.enrich_with_yahoo は eligible 行 (cache 未登録 OR
stale) を asyncio.Semaphore で並列に Yahoo へ問い合わせ ScreeningCache を
upsert する。 1 ticker の例外 / DB 失敗は warn (exc_info 付) + 集計のみ、
他 ticker は継続。 ticker None の company は eligible に出ないため skip。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: ScreeningService — schema declaration + validation

**Goal:** filter / sort で参照する column whitelist と FieldMetadata、 ScreenSpec dataclass、 spec validation を追加。

**Files:**
- Create: `src/stock_analyze_system/services/screening.py`
- Create: `tests/unit/services/test_screening_service.py`

- [ ] **Step 1: `services/screening.py` の枠組み (schema 宣言のみ)**

`src/stock_analyze_system/services/screening.py`:

```python
"""Screening read-only query service."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.analysis_target import AnalysisTargetService

logger = logging.getLogger(__name__)


SCREENING_NUMERIC_FIELDS: tuple[str, ...] = (
    "stock_price", "market_cap", "trailing_per", "eps",
    "forward_per", "pbr", "psr", "ev_ebitda",
    "dividend_yield", "roe", "operating_margin", "net_margin",
    "revenue_growth", "earnings_growth", "de_ratio",
    "peg_ratio", "fcf_yield", "beta", "volume",
)
SCREENING_CATEGORICAL_FIELDS: tuple[str, ...] = ("sector", "industry", "exchange")


@dataclass(frozen=True)
class FieldMetadata:
    field: str
    label: str
    format: Literal["ratio", "currency", "percent", "count", "string"]


FIELD_METADATA: tuple[FieldMetadata, ...] = (
    FieldMetadata("trailing_per", "PER (trailing)", "ratio"),
    FieldMetadata("forward_per",  "PER (forward)",  "ratio"),
    FieldMetadata("pbr",          "PBR",            "ratio"),
    FieldMetadata("psr",          "PSR",            "ratio"),
    FieldMetadata("ev_ebitda",    "EV/EBITDA",      "ratio"),
    FieldMetadata("market_cap",   "時価総額",        "currency"),
    FieldMetadata("eps",          "EPS",            "currency"),
    FieldMetadata("stock_price",  "株価",            "currency"),
    FieldMetadata("dividend_yield","配当利回り",     "percent"),
    FieldMetadata("roe",          "ROE",            "percent"),
    FieldMetadata("operating_margin", "営業利益率",  "percent"),
    FieldMetadata("net_margin",   "純利益率",        "percent"),
    FieldMetadata("revenue_growth", "売上成長率",    "percent"),
    FieldMetadata("earnings_growth","利益成長率",    "percent"),
    FieldMetadata("de_ratio",     "負債資本倍率",    "ratio"),
    FieldMetadata("peg_ratio",    "PEG",            "ratio"),
    FieldMetadata("fcf_yield",    "FCF利回り",      "percent"),
    FieldMetadata("beta",         "β",             "ratio"),
    FieldMetadata("volume",       "出来高",          "count"),
    FieldMetadata("sector",       "セクター",        "string"),
    FieldMetadata("industry",     "業種",            "string"),
    FieldMetadata("exchange",     "市場",            "string"),
)


@dataclass(frozen=True)
class FilterClause:
    field: str
    op: Literal["gte", "lte", "between", "eq", "in"]
    value: float | int | tuple[float, float] | str | list[str]


@dataclass(frozen=True)
class SortSpec:
    field: str
    desc: bool = True


@dataclass(frozen=True)
class ScreenSpec:
    filters: list[FilterClause] = field(default_factory=list)
    sort: SortSpec | None = None
    limit: int = 100
    offset: int = 0
    include_null: bool = False


class ScreeningService:
    """Filter / sort / distribution / add-to-targets (read-only)."""

    def __init__(
        self,
        screening_repo: ScreeningRepository,
        company_repo: CompanyRepository,
        target_service: AnalysisTargetService,
    ):
        self._screening_repo = screening_repo
        self._company_repo = company_repo
        self._target_service = target_service

    @staticmethod
    def _validate(spec: ScreenSpec) -> None:
        all_fields = set(SCREENING_NUMERIC_FIELDS) | set(SCREENING_CATEGORICAL_FIELDS)
        if not (1 <= spec.limit <= 1000):
            raise ValueError(f"limit must be in 1..1000, got {spec.limit}")
        if spec.offset < 0:
            raise ValueError(f"offset must be >= 0, got {spec.offset}")
        if spec.sort is not None and spec.sort.field not in all_fields:
            raise ValueError(f"unknown sort field: {spec.sort.field!r}")
        for clause in spec.filters:
            if clause.field not in all_fields:
                raise ValueError(f"unknown field: {clause.field!r}")
            is_numeric = clause.field in SCREENING_NUMERIC_FIELDS
            if is_numeric and clause.op in ("eq", "in"):
                raise ValueError(
                    f"op {clause.op!r} not allowed on numeric field "
                    f"{clause.field!r}",
                )
            if not is_numeric and clause.op in ("gte", "lte", "between"):
                raise ValueError(
                    f"op {clause.op!r} not allowed on categorical field "
                    f"{clause.field!r}",
                )
            if clause.op == "between":
                v = clause.value
                if not (isinstance(v, (tuple, list)) and len(v) == 2):
                    raise ValueError(
                        f"between expects 2-tuple, got {v!r}",
                    )
                lo, hi = v
                if lo > hi:
                    raise ValueError(
                        f"between lower must be <= upper, got ({lo}, {hi})",
                    )
            if clause.op == "in":
                if not isinstance(clause.value, (list, tuple)):
                    raise ValueError(
                        f"in expects list/tuple, got {clause.value!r}",
                    )
```

- [ ] **Step 2: 失敗テストを追加 — validation のみ**

`tests/unit/services/test_screening_service.py`:

```python
"""ScreeningService の単体テスト."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from stock_analyze_system.services.screening import (
    FilterClause,
    ScreenSpec,
    ScreeningService,
    SortSpec,
)


def _svc():
    return ScreeningService(
        screening_repo=MagicMock(),
        company_repo=MagicMock(),
        target_service=MagicMock(),
    )


class TestValidate:
    def test_unknown_field_rejected(self):
        with pytest.raises(ValueError, match="unknown field"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("company_id", "gte", 0)
            ]))

    def test_sql_injection_in_field_rejected(self):
        with pytest.raises(ValueError, match="unknown field"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per; DROP TABLE companies", "gte", 0)
            ]))

    def test_eq_on_numeric_rejected(self):
        with pytest.raises(ValueError, match="not allowed on numeric"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "eq", 15)
            ]))

    def test_in_on_numeric_rejected(self):
        with pytest.raises(ValueError, match="not allowed on numeric"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "in", [1, 2])
            ]))

    def test_gte_on_categorical_rejected(self):
        with pytest.raises(ValueError, match="not allowed on categorical"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("sector", "gte", 1)
            ]))

    def test_between_inverted_range_rejected(self):
        with pytest.raises(ValueError, match="lower must be <= upper"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "between", (15, 5))
            ]))

    def test_between_single_value_rejected(self):
        with pytest.raises(ValueError, match="2-tuple"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "between", (15,))
            ]))

    def test_in_with_non_list_value_rejected(self):
        with pytest.raises(ValueError, match="list/tuple"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("sector", "in", "Nasdaq")
            ]))

    def test_limit_zero_rejected(self):
        with pytest.raises(ValueError, match="limit"):
            _svc()._validate(ScreenSpec(limit=0))

    def test_limit_over_1000_rejected(self):
        with pytest.raises(ValueError, match="limit"):
            _svc()._validate(ScreenSpec(limit=1001))

    def test_negative_offset_rejected(self):
        with pytest.raises(ValueError, match="offset"):
            _svc()._validate(ScreenSpec(offset=-1))

    def test_unknown_sort_field_rejected(self):
        with pytest.raises(ValueError, match="unknown sort field"):
            _svc()._validate(ScreenSpec(sort=SortSpec("company_id")))

    def test_valid_spec_passes(self):
        _svc()._validate(ScreenSpec(
            filters=[
                FilterClause("trailing_per", "between", (0, 15)),
                FilterClause("roe", "gte", 0.15),
                FilterClause("sector", "in", ["Technology"]),
            ],
            sort=SortSpec("market_cap"),
            limit=50,
            offset=0,
        ))
```

- [ ] **Step 3: テストを実行 — 緑確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_service.py::TestValidate -v
```
Expected: 13 PASSED。

- [ ] **Step 4: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/screening.py tests/unit/services/test_screening_service.py
```
Expected: clean。

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/screening.py tests/unit/services/test_screening_service.py
git commit -m "$(cat <<'EOF'
feat(screening): add ScreeningService schema + spec validation

中央 whitelist (SCREENING_NUMERIC_FIELDS / SCREENING_CATEGORICAL_FIELDS) と
FieldMetadata、 ScreenSpec / FilterClause / SortSpec dataclass、 spec
validation (whitelist 外 / op 不整合 / between 逆順 / limit-offset 範囲
/ sort field 不正) を追加。 13 件の validation test で網羅。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: ScreeningService.run_screen

**Goal:** filter / sort / paginate を SQL 化、 結果型 `ScreenResultItem` / `ScreenResult`、 NULL / NaN / inf の挙動を test 込で固める。

**Files:**
- Modify: `src/stock_analyze_system/services/screening.py`
- Modify: `tests/unit/services/test_screening_service.py`

- [ ] **Step 1: 戻り型 + `_resolve_column` + `run_screen` を追加**

`src/stock_analyze_system/services/screening.py` の末尾 (クラス内) に追加:

```python
@dataclass
class ScreenResultItem:
    company_id: str
    ticker: str | None
    name: str
    sector: str | None
    market: str
    metrics: dict[str, float | int | None]


@dataclass
class ScreenResult:
    items: list["ScreenResultItem"]
    total_matched: int
    spec: ScreenSpec
    limit: int
    offset: int
```

(クラス内に move) — クラス本体外、 `class ScreeningService` の前に置く。

`ScreeningService` 内に追加:

```python
    @staticmethod
    def _resolve_column(field: str):
        if field not in (set(SCREENING_NUMERIC_FIELDS) | set(SCREENING_CATEGORICAL_FIELDS)):
            raise ValueError(f"unknown field: {field!r}")
        return getattr(ScreeningCache, field)

    async def run_screen(self, spec: ScreenSpec) -> "ScreenResult":
        from sqlalchemy import select, func, and_

        from stock_analyze_system.models.company import Company

        self._validate(spec)
        where_clauses = []
        for clause in spec.filters:
            col = self._resolve_column(clause.field)
            if clause.op == "gte":
                where_clauses.append(col >= clause.value)
            elif clause.op == "lte":
                where_clauses.append(col <= clause.value)
            elif clause.op == "between":
                lo, hi = clause.value
                where_clauses.append(col.between(lo, hi))
            elif clause.op == "eq":
                where_clauses.append(col == clause.value)
            elif clause.op == "in":
                where_clauses.append(col.in_(list(clause.value)))
            if (clause.field in SCREENING_NUMERIC_FIELDS
                    and not spec.include_null):
                where_clauses.append(col.is_not(None))

        sort_field = spec.sort.field if spec.sort else "market_cap"
        sort_desc = spec.sort.desc if spec.sort else True
        sort_col = self._resolve_column(sort_field)

        base = (
            select(ScreeningCache, Company)
            .join(Company, Company.id == ScreeningCache.company_id)
            .where(*where_clauses)
            .order_by(sort_col.is_(None),
                      sort_col.desc() if sort_desc else sort_col.asc())
            .limit(spec.limit)
            .offset(spec.offset)
        )
        rows = (await self._screening_repo._session.execute(base)).all()

        count_stmt = (
            select(func.count())
            .select_from(ScreeningCache)
            .join(Company, Company.id == ScreeningCache.company_id)
            .where(*where_clauses)
        )
        total = (await self._screening_repo._session.execute(count_stmt)).scalar() or 0

        items: list[ScreenResultItem] = []
        for cache, company in rows:
            metrics = {f: getattr(cache, f) for f in SCREENING_NUMERIC_FIELDS}
            items.append(ScreenResultItem(
                company_id=company.id,
                ticker=company.ticker,
                name=company.name,
                sector=cache.sector or company.sector,
                market=company.market,
                metrics=metrics,
            ))
        return ScreenResult(
            items=items, total_matched=total, spec=spec,
            limit=spec.limit, offset=spec.offset,
        )
```

- [ ] **Step 2: 失敗テストを追加 — fixture 投入 + 基本 run**

`tests/unit/services/test_screening_service.py` に追記:

```python
import math

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.analysis_target import AnalysisTargetService
from stock_analyze_system.repositories.target import TargetRepository
from tests.fixtures.screening_universe import screening_universe_seeds


async def _seed_universe(session) -> ScreeningService:
    for seed in screening_universe_seeds():
        session.add(Company(**seed.company))
    await session.flush()
    for seed in screening_universe_seeds():
        if seed.cache is not None:
            session.add(ScreeningCache(company_id=seed.company["id"], **seed.cache))
    await session.flush()
    return ScreeningService(
        screening_repo=ScreeningRepository(session),
        company_repo=CompanyRepository(session),
        target_service=AnalysisTargetService(TargetRepository(session)),
    )


class TestRunScreen:
    @pytest.mark.asyncio
    async def test_default_sort_is_market_cap_desc(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(limit=20))
        ids = [it.company_id for it in result.items]
        assert ids[0] == "US_AAPL"   # mc=3.5T 最大
        assert ids[1] == "US_MSFT"   # mc=3.0T 次

    @pytest.mark.asyncio
    async def test_returns_full_metrics_dict(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(limit=1))
        item = result.items[0]
        assert set(item.metrics.keys()) == set(SCREENING_NUMERIC_FIELDS)

    @pytest.mark.asyncio
    async def test_excludes_null_by_default(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "gte", 0)],
        ))
        # PLTR / IZEA / CETX は trailing_per=None で除外、 BRK-A など 9 件残る
        ids = {it.company_id for it in result.items}
        assert "US_PLTR" not in ids
        assert "US_IZEA" not in ids
        assert "US_CETX" not in ids
        assert "US_AAPL" in ids

    @pytest.mark.asyncio
    async def test_includes_null_when_include_null_true(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "gte", 0)],
            include_null=True,
        ))
        ids = {it.company_id for it in result.items}
        assert "US_PLTR" in ids   # trailing_per=None でも include_null=True で残る

    @pytest.mark.asyncio
    async def test_between_inclusive_at_boundaries(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "between", (9.5, 28.4))],
        ))
        ids = {it.company_id for it in result.items}
        # BRK-A (9.5) と BRK-B (9.5) と AAPL (28.4) が含まれる (BETWEEN inclusive)
        assert {"US_BRK-A", "US_BRK-B", "US_AAPL"}.issubset(ids)

    @pytest.mark.asyncio
    async def test_handles_inf_excludes_under_lte_threshold(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("psr", "lte", 100)],
        ))
        ids = {it.company_id for it in result.items}
        assert "US_CETX" not in ids   # psr=inf で除外

    @pytest.mark.asyncio
    async def test_handles_nan_excluded(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("pbr", "gte", 0)],
        ))
        ids = {it.company_id for it in result.items}
        assert "US_CETX" not in ids   # pbr=NaN は SQL で常に false

    @pytest.mark.asyncio
    async def test_offset_beyond_total_returns_empty(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(limit=10, offset=1000))
        assert result.items == []
        assert result.total_matched > 0

    @pytest.mark.asyncio
    async def test_categorical_eq_case_sensitive(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("exchange", "eq", "nasdaq")],   # 小文字
        ))
        assert result.items == []

    @pytest.mark.asyncio
    async def test_unicode_sector_filter(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("sector", "eq", "技術")],
        ))
        ids = {it.company_id for it in result.items}
        assert ids == {"US_SONY"}

    @pytest.mark.asyncio
    async def test_negative_roe_passes_gte_negative_threshold(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("roe", "gte", -0.5)],
            limit=50,
        ))
        ids = {it.company_id for it in result.items}
        assert "US_PLTR" in ids   # roe=-0.12

    @pytest.mark.asyncio
    async def test_dash_in_ticker_preserved_in_response(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("exchange", "eq", "NYSE")],
            limit=50,
        ))
        ids = {it.company_id for it in result.items}
        assert "US_BRK-A" in ids
```

- [ ] **Step 3: テストを実行**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_service.py -v
```
Expected: 全件 PASSED。

- [ ] **Step 4: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/screening.py tests/unit/services/test_screening_service.py
```
Expected: clean。

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/screening.py tests/unit/services/test_screening_service.py
git commit -m "$(cat <<'EOF'
feat(screening): implement ScreeningService.run_screen

filter / sort / paginate を ScreeningCache JOIN Company の SQL に変換、
ScreenResultItem.metrics に全 18 numeric を含めて返す。 default sort は
market_cap desc、 NULLS LAST。 numeric filter は include_null=False で
IS NOT NULL を AND する。 NaN / inf は SQL 比較で自然に false 評価される。
12 件の test で AAPL〜CETX 16 ticker fixture を網羅。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: ScreeningService.get_distribution

**Goal:** numeric field の min/max + bucket 分割、 inf/NaN は finite filter で除外、 `non_finite_count` を別途返す。

**Files:**
- Modify: `src/stock_analyze_system/services/screening.py`
- Modify: `tests/unit/services/test_screening_service.py`

- [ ] **Step 1: `Distribution` / `Bucket` dataclass + `get_distribution` を実装**

`src/stock_analyze_system/services/screening.py` に追記 (クラス外 dataclass + クラス内メソッド):

```python
@dataclass
class Bucket:
    lower: float
    upper: float
    count: int


@dataclass
class Distribution:
    field: str
    min: float | None
    max: float | None
    null_count: int
    non_null_count: int
    non_finite_count: int
    buckets: list[Bucket]
```

`ScreeningService` 内:

```python
    async def get_distribution(
        self, field: str, buckets: int = 20,
    ) -> Distribution:
        from sqlalchemy import select, func, and_, not_, case

        if field not in SCREENING_NUMERIC_FIELDS:
            raise ValueError(f"distribution available only on numeric fields, got {field!r}")
        if not (1 <= buckets <= 100):
            raise ValueError(f"buckets must be in 1..100, got {buckets}")
        col = getattr(ScreeningCache, field)
        finite = and_(
            col.is_not(None),
            col != float("inf"),
            col != float("-inf"),
            col == col,    # NaN なら false
        )
        stat_stmt = select(
            func.min(col).filter(finite),
            func.max(col).filter(finite),
            func.count().filter(col.is_(None)),
            func.count().filter(finite),
            func.count().filter(and_(col.is_not(None), not_(finite))),
        )
        lo, hi, null_count, non_null, non_finite = (
            await self._screening_repo._session.execute(stat_stmt)
        ).one()

        if non_null == 0:
            return Distribution(
                field=field, min=None, max=None,
                null_count=null_count, non_null_count=0,
                non_finite_count=non_finite, buckets=[],
            )
        if lo == hi or lo is None or hi is None:
            return Distribution(
                field=field, min=lo, max=hi,
                null_count=null_count, non_null_count=non_null,
                non_finite_count=non_finite,
                buckets=[Bucket(lower=lo, upper=hi, count=non_null - non_finite)],
            )
        width = (hi - lo) / buckets
        case_args = [
            (
                and_(
                    col >= lo + i * width,
                    (col < lo + (i + 1) * width) if i < buckets - 1 else (col <= hi),
                ),
                i,
            )
            for i in range(buckets)
        ]
        bucket_idx = case(*case_args).label("idx")
        bucket_stmt = (
            select(bucket_idx, func.count())
            .where(finite)
            .group_by(bucket_idx)
        )
        rows = (await self._screening_repo._session.execute(bucket_stmt)).all()
        counts = {idx: cnt for idx, cnt in rows}
        return Distribution(
            field=field, min=lo, max=hi,
            null_count=null_count, non_null_count=non_null,
            non_finite_count=non_finite,
            buckets=[
                Bucket(
                    lower=lo + i * width,
                    upper=(lo + (i + 1) * width) if i < buckets - 1 else hi,
                    count=counts.get(i, 0),
                )
                for i in range(buckets)
            ],
        )
```

- [ ] **Step 2: 失敗テストを追加**

`tests/unit/services/test_screening_service.py` に追加:

```python
class TestGetDistribution:
    @pytest.mark.asyncio
    async def test_buckets_partition_correctly(self, session):
        # custom seed: roe = 0.0..0.9 in 10-step
        for i in range(10):
            session.add(Company(
                id=f"US_T{i}", ticker=f"T{i}", name=f"T{i}",
                market="Nasdaq", accounting_standard="US-GAAP",
            ))
        await session.flush()
        for i in range(10):
            session.add(ScreeningCache(
                company_id=f"US_T{i}", roe=i * 0.1,
            ))
        await session.flush()
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        dist = await svc.get_distribution("roe", buckets=5)
        assert dist.min == 0.0
        assert dist.max == 0.9
        # 10 値 / 5 buckets = 2 per bucket (last bucket is inclusive on upper)
        assert sum(b.count for b in dist.buckets) == 10
        assert all(b.count == 2 for b in dist.buckets)

    @pytest.mark.asyncio
    async def test_rejects_categorical_field(self, session):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="numeric"):
            await svc.get_distribution("sector")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("buckets", [0, 101])
    async def test_rejects_buckets_outside_1_to_100(self, session, buckets):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="buckets"):
            await svc.get_distribution("trailing_per", buckets=buckets)

    @pytest.mark.asyncio
    async def test_all_null_column_returns_zero_count(self, session):
        session.add(Company(
            id="US_X", ticker="X", name="X",
            market="Nasdaq", accounting_standard="US-GAAP",
        ))
        session.add(ScreeningCache(company_id="US_X", roe=None))
        await session.flush()
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        dist = await svc.get_distribution("roe", buckets=5)
        assert dist.min is None
        assert dist.max is None
        assert dist.non_null_count == 0
        assert dist.null_count == 1
        assert dist.buckets == []

    @pytest.mark.asyncio
    async def test_constant_column_collapses_to_single_bucket(self, session):
        for i in range(3):
            session.add(Company(
                id=f"US_C{i}", ticker=f"C{i}", name=f"C{i}",
                market="Nasdaq", accounting_standard="US-GAAP",
            ))
        await session.flush()
        for i in range(3):
            session.add(ScreeningCache(company_id=f"US_C{i}", beta=1.0))
        await session.flush()
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        dist = await svc.get_distribution("beta", buckets=5)
        assert dist.min == 1.0
        assert dist.max == 1.0
        assert len(dist.buckets) == 1
        assert dist.buckets[0].count == 3

    @pytest.mark.asyncio
    async def test_excludes_inf_from_min_max(self, session):
        svc = await _seed_universe(session)   # CETX has psr=inf, de_ratio=inf
        dist = await svc.get_distribution("psr", buckets=5)
        assert dist.max != float("inf")
        assert dist.non_finite_count >= 1   # CETX (psr=inf) counted
```

- [ ] **Step 3: テストを実行**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_service.py::TestGetDistribution -v
```
Expected: 全件 PASSED。

- [ ] **Step 4: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/screening.py
```
Expected: clean。

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/screening.py tests/unit/services/test_screening_service.py
git commit -m "$(cat <<'EOF'
feat(screening): implement ScreeningService.get_distribution

numeric field 限定の histogram (default 20 buckets)。 inf / NaN は finite
filter (col != ±inf AND col == col) で min/max・bucket から除外し、
non_finite_count として別途返す。 全 null / 単一値の degenerate case を
専用パスで処理。 6 件の test (正常 / null / 単一値 / inf 除外 / validation)
で網羅。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: ScreeningService.add_to_targets

**Goal:** dedupe + 100 件制限 + 不在 id を pre-check で skipped 計上 + AnalysisTargetService.add_from_screening に委譲。

**Files:**
- Modify: `src/stock_analyze_system/services/screening.py`
- Modify: `tests/unit/services/test_screening_service.py`

- [ ] **Step 1: `AddToTargetsResult` + `add_to_targets` を実装**

`src/stock_analyze_system/services/screening.py` 末尾の class 外:

```python
@dataclass
class AddToTargetsResult:
    requested: int
    added: int
    already_present: int
    skipped: int
```

`ScreeningService` 内:

```python
    async def add_to_targets(self, company_ids: list[str]) -> AddToTargetsResult:
        if not company_ids:
            raise ValueError("company_ids must be non-empty")
        if len(company_ids) > 100:
            raise ValueError("max 100 ids per call")
        unique = list(dict.fromkeys(company_ids))
        existing = await self._company_repo.find_existing_ids(unique)
        valid = [cid for cid in unique if cid in existing]
        skipped = len(unique) - len(valid)
        added = await self._target_service.add_from_screening(valid)
        already_present = len(valid) - added
        return AddToTargetsResult(
            requested=len(company_ids),
            added=added,
            already_present=already_present,
            skipped=skipped,
        )
```

- [ ] **Step 2: 失敗テストを追加**

`tests/unit/services/test_screening_service.py` に追加:

```python
class TestAddToTargets:
    @pytest.mark.asyncio
    async def test_rejects_empty_list(self, session):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="non-empty"):
            await svc.add_to_targets([])

    @pytest.mark.asyncio
    async def test_rejects_over_100_ids(self, session):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="max 100"):
            await svc.add_to_targets([f"US_T{i}" for i in range(101)])

    @pytest.mark.asyncio
    async def test_dedupes_duplicate_ids(self, session):
        svc = await _seed_universe(session)
        result = await svc.add_to_targets(["US_AAPL", "US_AAPL"])
        assert result.requested == 2
        assert result.added == 1
        assert result.already_present == 0

    @pytest.mark.asyncio
    async def test_skips_unknown_company_ids(self, session):
        svc = await _seed_universe(session)
        result = await svc.add_to_targets(["US_AAPL", "US_NONEXISTENT"])
        assert result.added == 1
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_counts_already_present_correctly(self, session):
        svc = await _seed_universe(session)
        first = await svc.add_to_targets(["US_AAPL"])
        assert first.added == 1
        second = await svc.add_to_targets(["US_AAPL"])
        assert second.added == 0
        assert second.already_present == 1
        assert second.skipped == 0
```

- [ ] **Step 3: テストを実行**

Run:
```
scripts/infisical-run uv run pytest tests/unit/services/test_screening_service.py::TestAddToTargets -v
```
Expected: 5 PASSED。

- [ ] **Step 4: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/screening.py
```
Expected: clean。

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/screening.py tests/unit/services/test_screening_service.py
git commit -m "$(cat <<'EOF'
feat(screening): implement ScreeningService.add_to_targets

dedupe + 100 件制限 + CompanyRepository.find_existing_ids で 不在 id を
skipped 計上した上で AnalysisTargetService.add_from_screening に委譲。
既存 add_from_screening の signature は変更しない。
already_present は valid - added で算出。 5 件の test (validation /
dedupe / skipped / already_present) で網羅。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Container wiring — 2 service に置換

**Goal:** `cli/container.py` の `screening_service: object | None` を `screening_universe_service` + `screening_service` の 2 サービスに置換。

**Files:**
- Modify: `src/stock_analyze_system/cli/container.py`
- Modify: `tests/unit/web/test_dependencies.py` (smoke 確認)

- [ ] **Step 1: `cli/container.py` の TYPE_CHECKING import に追加**

```python
    from stock_analyze_system.services.screening import ScreeningService
    from stock_analyze_system.services.screening_universe import ScreeningUniverseService
```

- [ ] **Step 2: `ServiceContainer` の field 置換**

`screening_service: object | None = None` を以下に置換:

```python
    screening_universe_service: ScreeningUniverseService | None = None
    screening_service: ScreeningService | None = None
```

- [ ] **Step 3: `setup_services` 内で 2 service を生成**

`setup_services` の return 直前に追記:

```python
    from stock_analyze_system.repositories.screening import ScreeningRepository
    from stock_analyze_system.services.screening import ScreeningService
    from stock_analyze_system.services.screening_universe import ScreeningUniverseService

    screening_repo = ScreeningRepository(session)
    screening_universe_svc = ScreeningUniverseService(
        screening_repo=screening_repo,
        company_repo=company_repo,
        sec_client=sec_client,
        yahoo_client=yahoo_client,
    )
    screening_svc = ScreeningService(
        screening_repo=screening_repo,
        company_repo=company_repo,
        target_service=target_svc,
    )
```

return の `ServiceContainer(...)` 引数に追加:

```python
        screening_universe_service=screening_universe_svc,
        screening_service=screening_svc,
```

- [ ] **Step 4: smoke で wiring 確認**

`tests/unit/web/test_dependencies.py::test_get_services_wires_container` に置き換え可能なら、 直接 print スクリプトで確認:

Run:
```
scripts/infisical-run uv run pytest tests/unit/web/test_dependencies.py -q
```
Expected: 既存全件 PASSED (Phase A 完了の 6 件 + 新追加分なし)。

- [ ] **Step 5: 全 unit test を回帰確認**

Run:
```
scripts/infisical-run uv run pytest tests/unit -q --ignore=tests/unit/services/test_pageindex_service.py --ignore=tests/unit/services/test_pypdf_compat.py
```
Expected: 全件 PASSED (pageindex 関連の pre-existing failures は除外)。

- [ ] **Step 6: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/cli/container.py
```
Expected: clean。

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/cli/container.py
git commit -m "$(cat <<'EOF'
feat(container): wire ScreeningService + ScreeningUniverseService

cli/container.py の placeholder screening_service: object | None を
screening_universe_service + screening_service の 2 service に置換し
setup_services で配線する。 これにより CLI / Web 両方から
ScreeningUniverseService.refresh_universe / enrich_with_yahoo および
ScreeningService.run_screen / get_distribution / add_to_targets が
利用可能になる。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: JSON API endpoints

**Goal:** `web/routes/screening.py` を JSON router に置換、 4 endpoint (run / distributions / fields / targets) を実装。 placeholder.html を削除。

**Files:**
- Modify: `src/stock_analyze_system/web/routes/screening.py`
- Delete: `src/stock_analyze_system/web/templates/screening/placeholder.html`
- Create: `tests/unit/web/test_screening_api.py`

- [ ] **Step 1: `web/routes/screening.py` を JSON router に書き換え**

`src/stock_analyze_system/web/routes/screening.py` を完全に置換:

```python
"""Screening JSON API endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.services.screening import (
    FIELD_METADATA,
    SCREENING_CATEGORICAL_FIELDS,
    SCREENING_NUMERIC_FIELDS,
    FilterClause,
    ScreenSpec,
    SortSpec,
)
from stock_analyze_system.web.auth import get_client_key
from stock_analyze_system.web.dependencies import get_services

router = APIRouter(prefix="/api/screening")


class FilterPayload(BaseModel):
    field: str
    op: Literal["gte", "lte", "between", "eq", "in"]
    value: float | int | tuple[float, float] | list[float] | str | list[str]


class SortPayload(BaseModel):
    field: str
    desc: bool = True


class RunRequest(BaseModel):
    filters: list[FilterPayload] = Field(default_factory=list)
    sort: SortPayload | None = None
    limit: int = 100
    offset: int = 0
    include_null: bool = False


class TargetsRequest(BaseModel):
    company_ids: list[str]


def _require_service(services: ServiceContainer):
    svc = services.screening_service
    if svc is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="screening_service unavailable",
        )
    return svc


def _enforce_heavy(request: Request, *, scope: str, detail: str) -> None:
    limiter = request.app.state.heavy_rate_limiter
    key = get_client_key(request, scope)
    if limiter.try_acquire(key) is None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


@router.post("/run")
async def run_screen(
    request: Request,
    payload: RunRequest,
    services: ServiceContainer = Depends(get_services),
):
    svc = _require_service(services)
    _enforce_heavy(
        request,
        scope=f"screening-run:{request.client.host if request.client else ''}",
        detail="Too many screening requests",
    )
    spec = ScreenSpec(
        filters=[
            FilterClause(
                field=f.field, op=f.op,
                value=tuple(f.value) if f.op == "between" and isinstance(f.value, list)
                else f.value,
            )
            for f in payload.filters
        ],
        sort=SortSpec(field=payload.sort.field, desc=payload.sort.desc)
        if payload.sort else None,
        limit=payload.limit,
        offset=payload.offset,
        include_null=payload.include_null,
    )
    try:
        result = await svc.run_screen(spec)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "items": [
            {
                "company_id": it.company_id,
                "ticker": it.ticker,
                "name": it.name,
                "sector": it.sector,
                "market": it.market,
                "metrics": it.metrics,
            }
            for it in result.items
        ],
        "total_matched": result.total_matched,
        "limit": result.limit,
        "offset": result.offset,
    }


@router.get("/distributions/{field}")
async def get_distribution(
    field: str,
    buckets: int = 20,
    services: ServiceContainer = Depends(get_services),
):
    svc = _require_service(services)
    try:
        dist = await svc.get_distribution(field, buckets=buckets)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "field": dist.field,
        "min": dist.min,
        "max": dist.max,
        "null_count": dist.null_count,
        "non_null_count": dist.non_null_count,
        "non_finite_count": dist.non_finite_count,
        "buckets": [
            {"lower": b.lower, "upper": b.upper, "count": b.count}
            for b in dist.buckets
        ],
    }


@router.get("/fields")
async def list_fields():
    return {
        "numeric": [
            {"field": m.field, "label": m.label, "format": m.format}
            for m in FIELD_METADATA
            if m.field in SCREENING_NUMERIC_FIELDS
        ],
        "categorical": [
            {"field": m.field, "label": m.label, "format": m.format}
            for m in FIELD_METADATA
            if m.field in SCREENING_CATEGORICAL_FIELDS
        ],
    }


@router.post("/targets")
async def add_targets(
    request: Request,
    payload: TargetsRequest,
    services: ServiceContainer = Depends(get_services),
):
    svc = _require_service(services)
    _enforce_heavy(
        request,
        scope=f"screening-targets:{request.client.host if request.client else ''}",
        detail="Too many target add requests",
    )
    try:
        result = await svc.add_to_targets(payload.company_ids)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "requested": result.requested,
        "added": result.added,
        "already_present": result.already_present,
        "skipped": result.skipped,
    }
```

- [ ] **Step 2: `web/templates/screening/placeholder.html` と placeholder test を削除**

Run:
```bash
rm src/stock_analyze_system/web/templates/screening/placeholder.html
rmdir src/stock_analyze_system/web/templates/screening 2>/dev/null || true
rm tests/unit/web/test_screening.py
```

- [ ] **Step 3: API テストを作成**

`tests/unit/web/test_screening_api.py`:

```python
"""/api/screening/* JSON API テスト."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestScreeningApi:
    def test_fields_returns_metadata(self, auth_client):
        resp = auth_client.get("/api/screening/fields")
        assert resp.status_code == 200
        body = resp.json()
        assert any(f["field"] == "trailing_per" for f in body["numeric"])
        assert any(f["field"] == "sector" for f in body["categorical"])

    def test_run_returns_400_on_validation_error(self, monkeypatch, auth_client):
        from stock_analyze_system.web.routes import screening as screening_routes
        mock_svc = MagicMock()
        mock_svc.run_screen = AsyncMock(side_effect=ValueError("unknown field: 'company_id'"))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.post(
            "/api/screening/run",
            json={"filters": [{"field": "company_id", "op": "gte", "value": 0}]},
        )
        assert resp.status_code == 400

    def test_run_returns_503_when_service_unavailable(self, auth_client):
        # default web_config の screening_service は None でないが、
        # ここでは monkeypatch 経由で None にする方法は無いので、
        # _require_service を直接 raise させて挙動確認
        from stock_analyze_system.web.routes import screening as screening_routes
        from fastapi import HTTPException, status

        def _raise(_services):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="screening_service unavailable",
            )

        # We monkeypatch via the route module
        import stock_analyze_system.web.routes.screening as mod
        original = mod._require_service
        mod._require_service = _raise
        try:
            resp = auth_client.post("/api/screening/run", json={})
            assert resp.status_code == 503
        finally:
            mod._require_service = original

    def test_distributions_returns_field_payload(self, monkeypatch, auth_client):
        from stock_analyze_system.web.routes import screening as screening_routes
        from stock_analyze_system.services.screening import (
            Distribution, Bucket,
        )
        mock_svc = MagicMock()
        mock_svc.get_distribution = AsyncMock(return_value=Distribution(
            field="trailing_per", min=10.0, max=30.0,
            null_count=2, non_null_count=8, non_finite_count=0,
            buckets=[Bucket(10.0, 30.0, 8)],
        ))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.get("/api/screening/distributions/trailing_per")
        assert resp.status_code == 200
        body = resp.json()
        assert body["field"] == "trailing_per"
        assert body["non_finite_count"] == 0

    def test_distributions_400_on_categorical_field(self, monkeypatch, auth_client):
        from stock_analyze_system.web.routes import screening as screening_routes
        mock_svc = MagicMock()
        mock_svc.get_distribution = AsyncMock(side_effect=ValueError("numeric only"))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.get("/api/screening/distributions/sector")
        assert resp.status_code == 400

    def test_targets_returns_added_count(self, monkeypatch, auth_client):
        from stock_analyze_system.web.routes import screening as screening_routes
        from stock_analyze_system.services.screening import AddToTargetsResult
        mock_svc = MagicMock()
        mock_svc.add_to_targets = AsyncMock(return_value=AddToTargetsResult(
            requested=2, added=2, already_present=0, skipped=0,
        ))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.post(
            "/api/screening/targets",
            json={"company_ids": ["US_AAPL", "US_MSFT"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["added"] == 2

    def test_targets_400_on_empty_list(self, monkeypatch, auth_client):
        from stock_analyze_system.web.routes import screening as screening_routes
        mock_svc = MagicMock()
        mock_svc.add_to_targets = AsyncMock(
            side_effect=ValueError("company_ids must be non-empty"),
        )
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.post("/api/screening/targets", json={"company_ids": []})
        assert resp.status_code == 400
```

- [ ] **Step 4: テストを実行**

Run:
```
scripts/infisical-run uv run pytest tests/unit/web/test_screening_api.py -v
```
Expected: 全 7 件 PASSED。

- [ ] **Step 5: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/web/routes/screening.py tests/unit/web/test_screening_api.py
```
Expected: clean。

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/web/routes/screening.py tests/unit/web/test_screening_api.py
git rm src/stock_analyze_system/web/templates/screening/placeholder.html tests/unit/web/test_screening.py
git commit -m "$(cat <<'EOF'
feat(web): replace screening placeholder with JSON API endpoints

POST /api/screening/run / GET /api/screening/distributions/{field} /
GET /api/screening/fields / POST /api/screening/targets を追加。
ValueError は HTTP 400、 service None は 503、 run / targets には
heavy rate limit を適用。 placeholder.html を削除。 Pydantic で payload
を validate し ScreenSpec / FilterClause へ変換する薄ラッパー。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: CLI commands — 旧 `screen.py` を新 `screening.py` で置換

**Goal:** `cli/screen.py` (Phase 5 スタブ) を削除し `cli/screening.py` を新規作成。 5 サブコマンド (universe refresh / refresh / run / add-targets / fields) を実装。

**Files:**
- Delete: `src/stock_analyze_system/cli/screen.py`
- Create: `src/stock_analyze_system/cli/screening.py`
- Modify: `src/stock_analyze_system/cli/app.py`
- Create: `tests/unit/cli/test_screening_cli.py`

- [ ] **Step 1: `cli/screening.py` を新規作成**

`src/stock_analyze_system/cli/screening.py`:

```python
"""screening サブコマンド."""
from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.services.screening import (
    FIELD_METADATA,
    FilterClause,
    ScreenSpec,
    SortSpec,
    SCREENING_CATEGORICAL_FIELDS,
    SCREENING_NUMERIC_FIELDS,
)

if TYPE_CHECKING:
    from stock_analyze_system.cli.container import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("screening", help="スクリーニング")
    sub = parser.add_subparsers(dest="action", required=True)

    universe = sub.add_parser("universe", help="universe 操作")
    usub = universe.add_subparsers(dest="universe_action", required=True)
    ur = usub.add_parser("refresh", help="SEC から universe を取り込み")
    ur.add_argument("--source", default="sec", choices=["sec"])

    rf = sub.add_parser("refresh", help="Yahoo enrichment")
    rf.add_argument("--limit", type=int, default=None)
    rf.add_argument("--stale-hours", type=int, default=24)
    rf.add_argument("--concurrency", type=int, default=8)

    rn = sub.add_parser("run", help="スクリーニング実行")
    rn.add_argument("--gte", action="append", default=[], metavar="FIELD=V")
    rn.add_argument("--lte", action="append", default=[], metavar="FIELD=V")
    rn.add_argument("--between", action="append", default=[], metavar="FIELD=LO,HI")
    rn.add_argument("--eq", action="append", default=[], metavar="FIELD=V")
    rn.add_argument("--in", dest="in_", action="append", default=[],
                    metavar="FIELD=V1,V2,...")
    rn.add_argument("--sort", default=None, metavar="FIELD")
    rn.add_argument("--desc", action="store_true", default=True)
    rn.add_argument("--asc", action="store_false", dest="desc")
    rn.add_argument("--limit", type=int, default=50)
    rn.add_argument("--offset", type=int, default=0)
    rn.add_argument("--include-null", action="store_true")
    rn.add_argument("--json", action="store_true", dest="json_output")

    at = sub.add_parser("add-targets", help="ターゲットに追加")
    at.add_argument("ids", nargs="+", metavar="COMPANY_ID")

    sub.add_parser("fields", help="filter 可能 field 一覧")

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: "ServiceContainer") -> None:
    universe_svc = services.screening_universe_service
    screen_svc = services.screening_service
    if universe_svc is None or screen_svc is None:
        print("ERROR: screening service is unavailable. Check container wiring.",
              file=sys.stderr)
        sys.exit(1)

    if args.action == "universe":
        if args.universe_action == "refresh":
            r = await universe_svc.refresh_universe()
            print(f"Universe refresh (source={args.source})")
            print(f"  fetched: {r.fetched}")
            print(f"  inserted: {r.inserted}, updated: {r.updated}, skipped: {r.skipped}")
        return

    if args.action == "refresh":
        r = await universe_svc.enrich_with_yahoo(
            limit=args.limit,
            stale_hours=args.stale_hours,
            max_concurrency=args.concurrency,
        )
        print(f"Enrichment (eligible={r.eligible}, attempted={r.attempted}, "
              f"concurrency={args.concurrency})")
        print(f"  succeeded: {r.succeeded}, failed: {r.failed}, skipped: {r.skipped}")
        print(f"  elapsed: {r.elapsed_seconds:.1f}s")
        return

    if args.action == "run":
        spec = _build_screen_spec(args)
        try:
            result = await screen_svc.run_screen(spec)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
        if args.json_output:
            print(json.dumps({
                "items": [
                    {
                        "company_id": it.company_id, "ticker": it.ticker,
                        "name": it.name, "sector": it.sector,
                        "market": it.market, "metrics": it.metrics,
                    }
                    for it in result.items
                ],
                "total_matched": result.total_matched,
                "limit": result.limit, "offset": result.offset,
            }, ensure_ascii=False))
        else:
            _print_screen_table(result)
        return

    if args.action == "add-targets":
        try:
            r = await screen_svc.add_to_targets(args.ids)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
        print(f"analysis_targets: requested={r.requested} added={r.added} "
              f"already_present={r.already_present} skipped={r.skipped}")
        return

    if args.action == "fields":
        for m in FIELD_METADATA:
            kind = "numeric" if m.field in SCREENING_NUMERIC_FIELDS else "categorical"
            print(f"  {m.field:<22}  [{kind}]  {m.label}  ({m.format})")
        return


def _parse_kv(item: str, *, expect_pair: bool = False) -> tuple[str, list[str]]:
    if "=" not in item:
        raise ValueError(f"expected FIELD=VALUE, got {item!r}")
    field, raw = item.split("=", 1)
    parts = [p for p in raw.split(",") if p != ""] if expect_pair else [raw]
    return field, parts


def _build_screen_spec(args: argparse.Namespace) -> ScreenSpec:
    filters: list[FilterClause] = []
    for s in args.gte:
        f, parts = _parse_kv(s)
        filters.append(FilterClause(f, "gte", float(parts[0])))
    for s in args.lte:
        f, parts = _parse_kv(s)
        filters.append(FilterClause(f, "lte", float(parts[0])))
    for s in args.between:
        f, parts = _parse_kv(s, expect_pair=True)
        if len(parts) != 2:
            raise ValueError(f"--between expects FIELD=LO,HI, got {s!r}")
        filters.append(FilterClause(f, "between",
                                    (float(parts[0]), float(parts[1]))))
    for s in args.eq:
        f, parts = _parse_kv(s)
        filters.append(FilterClause(f, "eq", parts[0]))
    for s in args.in_:
        f, parts = _parse_kv(s, expect_pair=True)
        filters.append(FilterClause(f, "in", parts))
    sort = SortSpec(field=args.sort, desc=args.desc) if args.sort else None
    return ScreenSpec(
        filters=filters, sort=sort,
        limit=args.limit, offset=args.offset,
        include_null=args.include_null,
    )


def _print_screen_table(result) -> None:
    header = f"{'ticker':<6} {'name':<28} {'sector':<22} {'market_cap':>12} {'PER':>7} {'ROE':>7}"
    print(header)
    print("-" * len(header))
    for it in result.items:
        m = it.metrics
        print(
            f"{(it.ticker or ''):<6} "
            f"{(it.name or '')[:28]:<28} "
            f"{(it.sector or '')[:22]:<22} "
            f"{_fmt_money(m.get('market_cap')):>12} "
            f"{_fmt_num(m.get('trailing_per'), 1):>7} "
            f"{_fmt_num(m.get('roe'), 2):>7}"
        )
    print(f"matched={result.total_matched}, shown={len(result.items)} "
          f"(offset={result.offset})")


def _fmt_money(v) -> str:
    if v is None or v != v:
        return "-"
    if v >= 1e12:
        return f"{v/1e12:.2f}T"
    if v >= 1e9:
        return f"{v/1e9:.2f}B"
    if v >= 1e6:
        return f"{v/1e6:.1f}M"
    return f"{v:.0f}"


def _fmt_num(v, p: int) -> str:
    if v is None or v != v:
        return "-"
    return f"{v:.{p}f}"
```

- [ ] **Step 2: `cli/app.py` の import / register を screen → screening に**

`src/stock_analyze_system/cli/app.py`:

```python
from stock_analyze_system.cli import (
    company, filings, financial, jobs, rag, screening, serve, target, valuation, watchlist,
)
```

`build_parser` 内 `screen.register_parser(subparsers)` を:

```python
    screening.register_parser(subparsers)
```

に置換。

- [ ] **Step 3: `cli/screen.py` を削除**

```bash
git rm src/stock_analyze_system/cli/screen.py
```

- [ ] **Step 4: CLI test を作成**

`tests/unit/cli/test_screening_cli.py`:

```python
"""screening CLI のテスト."""
from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli import screening as cli_screening
from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.services.screening import (
    AddToTargetsResult,
    FilterClause,
    ScreenResult,
    ScreenResultItem,
    ScreenSpec,
)


def _parse(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    cli_screening.register_parser(sub)
    return parser.parse_args(["screening", *argv])


def _make_services(*, universe=None, screen=None) -> ServiceContainer:
    return ServiceContainer(
        company_service=MagicMock(), financial_service=MagicMock(),
        valuation_service=MagicMock(), filing_service=MagicMock(),
        watchlist_service=MagicMock(), target_service=MagicMock(),
        job_service=MagicMock(), financial_sync=MagicMock(),
        filing_sync=MagicMock(),
        screening_universe_service=universe,
        screening_service=screen,
    )


class TestCli:
    @pytest.mark.asyncio
    async def test_screening_service_none_exits_1(self, capsys):
        args = _parse(["fields"])
        with pytest.raises(SystemExit) as ei:
            await cli_screening.handle(args, _make_services())
        assert ei.value.code == 1
        err = capsys.readouterr().err
        assert "unavailable" in err

    @pytest.mark.asyncio
    async def test_universe_refresh_calls_service(self, capsys):
        univ = MagicMock()
        from stock_analyze_system.services.screening_universe import RefreshUniverseResult
        univ.refresh_universe = AsyncMock(return_value=RefreshUniverseResult(
            fetched=10, inserted=8, updated=2, skipped=0,
        ))
        screen = MagicMock()
        await cli_screening.handle(
            _parse(["universe", "refresh"]),
            _make_services(universe=univ, screen=screen),
        )
        out = capsys.readouterr().out
        assert "fetched: 10" in out
        assert "inserted: 8, updated: 2" in out

    @pytest.mark.asyncio
    async def test_refresh_calls_enrich(self):
        univ = MagicMock()
        from stock_analyze_system.services.screening_universe import EnrichResult
        univ.enrich_with_yahoo = AsyncMock(return_value=EnrichResult(
            eligible=5, attempted=5, succeeded=4, failed=1, skipped=0,
            elapsed_seconds=1.2,
        ))
        screen = MagicMock()
        await cli_screening.handle(
            _parse(["refresh", "--limit", "5", "--concurrency", "2"]),
            _make_services(universe=univ, screen=screen),
        )
        univ.enrich_with_yahoo.assert_awaited_with(
            limit=5, stale_hours=24, max_concurrency=2,
        )

    @pytest.mark.asyncio
    async def test_run_parses_filters_and_calls_run_screen(self):
        univ = MagicMock()
        screen = MagicMock()
        screen.run_screen = AsyncMock(return_value=ScreenResult(
            items=[], total_matched=0, spec=ScreenSpec(), limit=50, offset=0,
        ))
        await cli_screening.handle(
            _parse([
                "run",
                "--gte", "roe=0.15",
                "--lte", "trailing_per=15",
                "--between", "market_cap=1e9,1e12",
                "--in", "exchange=Nasdaq,NYSE",
                "--sort", "market_cap", "--desc",
            ]),
            _make_services(universe=univ, screen=screen),
        )
        spec = screen.run_screen.await_args.args[0]
        ops = [(c.field, c.op) for c in spec.filters]
        assert ("roe", "gte") in ops
        assert ("trailing_per", "lte") in ops
        assert ("market_cap", "between") in ops
        assert ("exchange", "in") in ops
        assert spec.sort.field == "market_cap"
        assert spec.sort.desc is True

    @pytest.mark.asyncio
    async def test_run_json_emits_json(self, capsys):
        univ = MagicMock()
        screen = MagicMock()
        screen.run_screen = AsyncMock(return_value=ScreenResult(
            items=[
                ScreenResultItem(
                    company_id="US_AAPL", ticker="AAPL", name="Apple",
                    sector="Tech", market="Nasdaq",
                    metrics={"roe": 1.45, "market_cap": 3.5e12},
                ),
            ],
            total_matched=1, spec=ScreenSpec(), limit=50, offset=0,
        ))
        await cli_screening.handle(
            _parse(["run", "--json"]),
            _make_services(universe=univ, screen=screen),
        )
        out = capsys.readouterr().out.strip()
        import json
        body = json.loads(out)
        assert body["items"][0]["company_id"] == "US_AAPL"
        assert body["total_matched"] == 1

    @pytest.mark.asyncio
    async def test_add_targets_calls_service(self, capsys):
        univ = MagicMock()
        screen = MagicMock()
        screen.add_to_targets = AsyncMock(return_value=AddToTargetsResult(
            requested=2, added=1, already_present=1, skipped=0,
        ))
        await cli_screening.handle(
            _parse(["add-targets", "US_AAPL", "US_MSFT"]),
            _make_services(universe=univ, screen=screen),
        )
        out = capsys.readouterr().out
        assert "added=1 already_present=1" in out

    @pytest.mark.asyncio
    async def test_fields_lists_metadata(self, capsys):
        univ = MagicMock()
        screen = MagicMock()
        await cli_screening.handle(
            _parse(["fields"]),
            _make_services(universe=univ, screen=screen),
        )
        out = capsys.readouterr().out
        assert "trailing_per" in out
        assert "sector" in out
```

- [ ] **Step 5: テストを実行**

Run:
```
scripts/infisical-run uv run pytest tests/unit/cli/test_screening_cli.py -v
```
Expected: 全 7 件 PASSED。

- [ ] **Step 6: CLI smoke (`--help` が破綻しないこと)**

Run:
```
scripts/infisical-run uv run stock-analyze screening --help
```
Expected: subcommand 一覧 (universe / refresh / run / add-targets / fields) が表示。

- [ ] **Step 7: ruff チェック**

Run:
```
scripts/infisical-run uv run ruff check src/stock_analyze_system/cli/screening.py src/stock_analyze_system/cli/app.py tests/unit/cli/test_screening_cli.py
```
Expected: clean。

- [ ] **Step 8: Commit**

```bash
git add src/stock_analyze_system/cli/screening.py src/stock_analyze_system/cli/app.py tests/unit/cli/test_screening_cli.py
git rm src/stock_analyze_system/cli/screen.py
git commit -m "$(cat <<'EOF'
feat(cli): replace screen stub with screening subcommands

cli/screen.py (Phase 5 スタブ) を削除し cli/screening.py を新規実装。
universe refresh / refresh / run / add-targets / fields の 5 サブコマンドを
登録する。 run は --gte / --lte / --between / --eq / --in / --sort で
filter / sort を構築し、 --json で stdout に raw JSON を吐く。 service
未配線時は ERROR + exit 1 (stack trace 抑制)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: 最終回帰 + spec 反映確認

**Goal:** 全 unit test + ruff + warnings-as-errors を通し、 spec のセクションごとに対応 task を再確認する。

- [ ] **Step 1: 全 unit test を実行 (pageindex 既存 fail を除外)**

Run:
```
scripts/infisical-run uv run pytest tests/unit -q --ignore=tests/unit/services/test_pageindex_service.py --ignore=tests/unit/services/test_pypdf_compat.py
```
Expected: 全件 PASSED (新規 ≈70 件 + 既存)。

- [ ] **Step 2: warnings-as-errors で再走行**

Run:
```
scripts/infisical-run uv run pytest tests/unit -q -W error::DeprecationWarning -W error::RuntimeWarning --ignore=tests/unit/services/test_pageindex_service.py --ignore=tests/unit/services/test_pypdf_compat.py
```
Expected: 全件 PASSED。

- [ ] **Step 3: src + tests + scripts 全部にruff**

Run:
```
scripts/infisical-run uv run ruff check src tests scripts
```
Expected: `All checks passed!`

- [ ] **Step 4: Spec / Plan の対応確認**

`docs/superpowers/specs/2026-04-26-screening-design.md` の各セクションが下記 Task で実装されているか確認:

| spec section | implemented in |
|---|---|
| §3 Universe registration | Task 3 |
| §4 Enrichment | Task 4 |
| §5.1 / §5.2 中央スキーマ + ScreenSpec | Task 5 |
| §5.3 Validation | Task 5 |
| §5.4 / §5.5 run_screen + 結果型 | Task 6 |
| §5.6 get_distribution (inf/NaN 除外含む) | Task 7 |
| §5.7 add_to_targets | Task 8 |
| §6 JSON API endpoints | Task 10 |
| §7 CLI commands | Task 11 |
| §9.1 fixtures | Task 1 |
| §9.2 SEC mock payload | Task 1 |
| §9.3 Yahoo mock | Task 1 |
| §9.4 A〜H test categories | Task 2〜11 に分散 |
| §10 placeholder cleanup | Task 10 (HTML 削除) + Task 11 (cli/screen.py 削除) |
| §11.4 find_existing_ids 追加 | Task 2 |

- [ ] **Step 5: 既存 master.md tracker を更新するか判断**

`docs/superpowers/refactoring-2026-04-18/master.md` には Phase A〜E の記録のみ。 本 screening 機能は別 spec / plan として独立しているため tracker 更新は不要。 ただし master.md の "確定済みの out-of-scope / 今後の課題" 表で screening 言及があれば外す (確認のみ、 修正は別 PR でも可)。

- [ ] **Step 6: 最終 smoke (CLI で全 subcommand が表示されること)**

Run:
```
scripts/infisical-run uv run stock-analyze --help
```
Expected: top-level に `screening` が並んでいる。

```
scripts/infisical-run uv run stock-analyze screening --help
```
Expected: `universe / refresh / run / add-targets / fields` が並ぶ。

- [ ] **Step 7: 最終 status の取得 (Commit はしない)**

Run:
```
git log --oneline -15
```

このタスクは明示的な Commit を作らない。 Task 1〜11 の commit がすべて積まれていれば完了。

---

## まとめ

- Total tasks: 12
- Total expected commits: 11 (Task 12 は検証のみ)
- 既存 placeholder の処遇: cli/screen.py 削除 (Task 11)、 templates/screening/placeholder.html 削除 (Task 10)、 cli/container.py の object placeholder 置換 (Task 9)
- 既存 API 互換: `AnalysisTargetService.add_from_screening` は signature 変更なし (Task 2 で `find_existing_ids` を別途追加)
- 全 commit に `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` を入れる
- TDD 規律: 各 task で Red test → Green 実装 → 緑確認 → Commit を踏む
