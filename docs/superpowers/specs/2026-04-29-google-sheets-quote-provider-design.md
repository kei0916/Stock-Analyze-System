# Google Sheets Quote Provider Design (2026-04-29)

## 1. Purpose

SEC 提出企業 universe のスクリーニングを安定して回すため、株価取得を Yahoo Finance
直叩きから切り離し、Google Sheets `GOOGLEFINANCE` を価格取得 provider の一つとして
組み込む。財務データは SEC EDGAR `companyfacts` 由来を正とし、株価だけを Google
Finance 経由で補い、DB 内で valuation / screening 指標を計算する。

この設計の狙いは次の通り。

- SEC 提出企業約 8,000 件に対して、yfinance の 429 / throttling リスクを下げる。
- 株価取得を `QuoteProvider` 境界に分離し、将来 FMP / Polygon / IEX などへ切り替え可能にする。
- `valuations` と `screening_cache` の両方が同じ価格キャッシュを参照できるようにする。
- 欠損・未対応 ticker・計算遅延を記録し、全件処理を途中で止めない。

## 2. Non-Goals

- Google Sheets を財務データの正規保存先にはしない。
- `GOOGLEFINANCE` から PER / EPS / marketcap などを主取得しない。価格のみを使う。
- リアルタイム売買用途、約定判断用途、金融業務用途の精度保証はしない。
- Google Sheets を Web UI から直接操作する機能は作らない。
- 既存 Yahoo Finance クライアントを即削除しない。fallback / 比較用に残す。

## 3. External Constraints

Google 公式仕様では `GOOGLEFINANCE` の `"price"` は最大 20 分遅延し、全市場の quote を
網羅せず、一部属性が銘柄によって返らない。Google Sheets API は read/write ともに
300 requests/minute/project、60 requests/minute/user の per-minute quota を持つ。
本設計では 8,000 銘柄をセルに展開しても Sheets API は batch update / batch get に寄せるため、
Sheets API quota よりも `GOOGLEFINANCE` の再計算速度・欠損率が主な制約になる。

`GOOGLEFINANCE` は exchange prefix 付き ticker が推奨されるため、SEC の `exchange`
値から Google Finance の symbol 表記へ変換する。例: `Nasdaq + AAPL` -> `NASDAQ:AAPL`。
Google 側で認識できない ticker は `unsupported_symbol` として記録する。

## 4. Existing System Context

現在の価格・valuation 経路は二つある。

- `JobService._update_valuation_for_company()` は `YahooFinanceClient.get_stock_price()`
  から価格と market cap を取得し、`financial_data` と合わせて `valuations` を更新する。
- `ScreeningUniverseService.enrich_with_yahoo()` は `YahooFinanceClient.get_screening_info()`
  から価格、PER、ROE、sector などをまとめて取得し、`screening_cache` を更新する。

この構造では yfinance が全件取得の単一点になり、SEC 財務データがあっても
スクリーニング指標を Yahoo に依存する。新構成では価格取得と指標計算を分離し、
Google Sheets 価格キャッシュから `valuations` と `screening_cache` を再構築する。

## 5. Proposed Architecture

```
SEC company_tickers_exchange.json
        |
        v
companies
        |
        +--------------------+
        |                    |
        v                    v
SEC companyfacts       Google Sheets Quote Sheet
        |                    |
        v                    v
financial_data         quote_prices
        |                    |
        +---------+----------+
                  |
                  v
        valuation / screening computation
                  |
        +---------+----------+
        v                    v
valuations          screening_cache
```

### 5.1 New Components

#### `QuotePrice` model

New table: `quote_prices`

Columns:

- `id`
- `company_id`
- `provider` (`google_sheets`, later `yahoo`, `fmp`, etc.)
- `provider_symbol` (`NASDAQ:AAPL`)
- `price`
- `currency`
- `data_delay_minutes`
- `as_of`
- `fetched_at`
- `status` (`ok`, `missing`, `unsupported_symbol`, `formula_error`, `stale`, `not_ready`)
- `error_message`
- `raw_value`

Natural key:

- Latest-cache use case: unique `(company_id, provider)`

Rationale: screening needs latest values, not historical price series. Historical valuation rows remain in
`valuations` keyed by `(company_id, date)`.

#### `QuotePriceRepository`

Responsibilities:

- Upsert latest quote per `(company_id, provider)`.
- List latest quotes by company IDs.
- List stale / failed quotes for retry.
- Count statuses for CLI reporting.

#### `GoogleSheetsQuoteClient`

Responsibilities:

- Write ticker rows and formulas to a configured worksheet.
- Poll calculated values until ready or timeout.
- Read calculated values in bulk.
- Normalize cell errors and empty values into typed results.

The client should not know SQLAlchemy models. It returns plain dataclasses:

- `QuoteRequest(company_id, provider_symbol)`
- `QuoteResult(company_id, provider_symbol, price, currency, data_delay_minutes, status, error_message, raw_value)`

#### `QuoteService`

Responsibilities:

- Build quote requests from `companies`.
- Convert SEC exchange/ticker to Google Finance symbol.
- Use `GoogleSheetsQuoteClient` to refresh prices.
- Persist results through `QuotePriceRepository`.
- Expose summary counts and failed rows.

#### `ValuationRefreshService` or `JobService` extension

Responsibilities:

- Read latest `financial_data` and latest `quote_prices`.
- Compute valuation metrics with existing `compute_valuation_from_financials()`.
- Upsert `valuations`.
- Avoid direct dependency on Yahoo for default path.

#### `ScreeningMetricsService`

Responsibilities:

- Read `companies`, latest annual and optionally previous annual `financial_data`, and latest `quote_prices`.
- Compute `screening_cache` fields from first-party data:
  - `stock_price`
  - `market_cap` when shares outstanding exists
  - `trailing_per`
  - `pbr`
  - `psr`
  - `ev_ebitda`
  - `fcf_yield`
  - `roe`
  - `operating_margin`
  - `net_margin`
  - `revenue_growth`
  - `earnings_growth`
  - `de_ratio`
- Leave unavailable fields as `None`:
  - `forward_per`
  - `dividend_yield`
  - `peg_ratio`
  - `beta`
  - `volume`
  - `most_recent_quarter`
  - `last_fiscal_year_end`
  - `trailing_eps_date` unless derivable from latest financial row

## 6. Google Sheet Layout

Dedicated worksheet, default name: `quotes`.

Columns:

| Column | Name | Source |
|---|---|---|
| A | company_id | DB |
| B | ticker | DB |
| C | exchange | DB |
| D | provider_symbol | mapped |
| E | price_formula | `=GOOGLEFINANCE(D2,"price")` |
| F | currency_formula | `=GOOGLEFINANCE(D2,"currency")` |
| G | delay_formula | `=GOOGLEFINANCE(D2,"datadelay")` |
| H | price_value | read from E |
| I | currency_value | read from F |
| J | delay_value | read from G |
| K | status | local interpretation |

Implementation detail: formulas and values do not need separate physical columns if values are read directly
from formula cells with `valueRenderOption=UNFORMATTED_VALUE`. Keeping the layout explicit helps debugging.

## 7. Symbol Mapping

Initial mapping:

| SEC exchange | Google Finance prefix |
|---|---|
| `Nasdaq` | `NASDAQ` |
| `NYSE` | `NYSE` |
| `NYSE American` | `NYSEAMERICAN` |
| `NYSE Arca` | `NYSEARCA` |
| `Cboe BZX` | `BATS` |

Ticker normalization:

- Preserve class-share punctuation from SEC where Google accepts it.
- If Google rejects a symbol, do not mutate aggressively in the same pass.
- Record failure and allow explicit overrides later.

Future override table:

- Add `quote_symbol_overrides` only if initial run shows material failures.
- Columns would be `company_id`, `provider`, `provider_symbol`, `active`, `note`.

## 8. Configuration

Add config section:

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

Secrets:

- Prefer service account JSON in an environment variable for managed secrets.
- Path-based credentials are allowed for local development.
- The target spreadsheet must be shared with the service account.

## 9. CLI Surface

Add `quotes` command group:

```bash
stock-analyze quotes sheets refresh --market us --limit 8000
stock-analyze quotes sheets status --market us
stock-analyze quotes retry-failed --provider google_sheets --limit 500
```

Adjust screening:

```bash
stock-analyze screening refresh --source sec-google --limit 8000
```

Keep existing Yahoo path initially:

```bash
stock-analyze screening refresh --source yahoo
```

Adjust jobs:

```bash
stock-analyze jobs valuations --market us --quote-provider google_sheets
```

Default provider can become `google_sheets` only when config is enabled. Otherwise fall back to Yahoo for
backward compatibility.

## 10. Data Flow

### Full Refresh

1. `screening universe refresh`
   - SEC universe -> `companies`
2. Financial refresh
   - SEC `companyfacts` -> `financial_data`
3. `quotes sheets refresh`
   - `companies` -> Google sheet formulas -> calculated values -> `quote_prices`
4. `jobs valuations --quote-provider google_sheets`
   - `financial_data + quote_prices` -> `valuations`
5. `screening refresh --source sec-google`
   - `financial_data + quote_prices` -> `screening_cache`
6. `/screening`
   - existing API filters `screening_cache`

### Incremental Refresh

- Refresh only stale quote rows daily after market close.
- Refresh SEC financials via existing daily filings flow.
- Recompute valuations and screening rows for companies whose financials or quotes changed.

## 11. Error Handling

Per-row failures must not fail the whole run.

Statuses:

- `ok`: numeric price was read.
- `not_ready`: formula output was empty during polling.
- `formula_error`: cell contains `#N/A`, `#VALUE!`, or another sheet error.
- `unsupported_symbol`: no mapped provider symbol could be produced.
- `missing`: no price after max polls.
- `stale`: existing cached quote is older than configured max age.

Run-level failures:

- Missing config or credentials: fail fast.
- Sheets API quota / 429: retry with exponential backoff, then fail run with partial DB writes preserved.
- Spreadsheet permission error: fail fast with actionable message.

## 12. Performance Estimates

For 8,000 companies:

- Sheet write: chunked batch update, roughly 16 chunks at batch size 500.
- Sheet read: chunked batch get, roughly 16 chunks at batch size 500.
- API quota is not the expected bottleneck.
- Formula calculation is the bottleneck and has no public SLA.

Operational assumption:

- First full run should be treated as a batch job that may take minutes to tens of minutes.
- The CLI should report polling attempts, ready count, missing count, and final status distribution.

## 13. Testing Strategy

### Unit Tests

- Symbol mapping:
  - Nasdaq / NYSE / unknown exchange.
  - class-share tickers.
- `GoogleSheetsQuoteClient`:
  - successful values.
  - empty values then success after polling.
  - formula error.
  - quota retry.
- `QuoteService`:
  - persists `ok`.
  - records unsupported symbol.
  - preserves existing quote when new run fails, while marking latest status.
- Valuation computation:
  - price + shares -> market cap.
  - missing shares -> market-cap-dependent metrics are `None`.
  - existing annual financial row -> valuation upsert.
- Screening computation:
  - SEC-derived fields filled.
  - unavailable Yahoo-only fields remain `None`.
  - per-company failures do not stop the batch.

### CLI Tests

- `quotes sheets refresh` summary output.
- `quotes sheets status` status counts.
- `screening refresh --source sec-google`.
- `jobs valuations --quote-provider google_sheets`.

### Integration / Manual Tests

Marked as manual or integration:

1. Small sheet with 5 known tickers.
2. Medium run with 100 tickers.
3. Full run with all SEC universe tickers.

Metrics to record:

- total rows
- ready rows
- failed rows by status
- elapsed formula wait time
- API read/write request count
- valuation rows updated
- screening rows updated

## 14. Rollout Plan

Phase 1: Infrastructure

- Add config.
- Add `QuotePrice` model / repository.
- Add symbol mapping utilities.
- Add mocked `GoogleSheetsQuoteClient`.

Phase 2: Quote Refresh

- Add `QuoteService`.
- Add `quotes` CLI.
- Verify with unit tests and mocked Sheets API.

Phase 3: Valuation Integration

- Add quote-provider path to valuation update.
- Keep Yahoo fallback.
- Update job tests.

Phase 4: Screening Integration

- Add SEC + Google price screening computation.
- Keep Yahoo enrichment as optional source.
- Update screening CLI and service tests.

Phase 5: Manual End-to-End Run

- Run 5 tickers, then 100, then full universe.
- Inspect status distribution.
- Add override support only if failure rate requires it.

## 15. Open Decisions

These decisions are fixed for initial implementation:

- `quote_prices` stores latest quote per provider, not full history.
- Google Sheets provider uses only price, currency, and data delay.
- Market cap is computed as `price * shares_outstanding` when shares are available.
- Missing market cap leaves PBR / PSR / EV/EBITDA / FCF yield as `None`.
- Yahoo fallback remains available but is no longer the default full-universe path when Google Sheets is enabled.

## 16. Acceptance Criteria

- A user can refresh Google Sheets prices for SEC universe companies from CLI.
- Quote refresh persists successful and failed per-company statuses.
- Valuation update can run using cached Google Sheets prices without calling Yahoo.
- Screening cache can be populated from SEC financials plus cached prices.
- Existing screening API can filter populated `screening_cache` without API changes.
- Existing Yahoo-based path still works for targeted or fallback use.
- Tests cover success, partial failure, missing price, missing shares, and unsupported symbols.
