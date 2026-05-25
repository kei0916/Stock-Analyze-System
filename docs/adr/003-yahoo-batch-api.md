# ADR-003: Yahoo Finance v7 Batch API for Screening Enrichment

## Status

Accepted (2026-05-09)

## Context

`ScreeningUniverseService.enrich_with_yahoo()` previously called
`yfinance.Ticker(t).info` once per company through an `asyncio.gather`
loop bounded by a Semaphore (`max_concurrency=8`). Wall-clock cost:

- Per-call: ~0.36s (TLS + curl_cffi impersonation + HTML scrape)
- Sequential: 10,376 tickers × 0.36s ≈ **62 minutes**
- With `max_concurrency=8`: ≈ **8 minutes**

Yahoo also exposes a v7 quote endpoint that accepts up to 1000 comma-
separated symbols per request:

    GET https://query1.finance.yahoo.com/v7/finance/quote?symbols=A,B,C,...

Per Yahoo's response shape:

- 11 batches × ~0.7s ≈ **8 seconds**
- The v7 endpoint returns `regularMarketPrice`, `marketCap`,
  `trailingPE`, `forwardPE`, `priceToBook`, `dividendYield`, `exchange`,
  `fiftyTwoWeekHigh`, `fiftyTwoWeekLow`, `averageVolume`, `trailingEps`.
- It does NOT return `sector`, `industry`, `beta`, `returnOnEquity`,
  `operatingMargins`, `profitMargins`, `revenueGrowth`,
  `earningsGrowth`, `pegRatio`, `freeCashflow`, `debtToEquity`. These
  remain available through `ScreeningMetricsService.refresh_from_sec_google()`,
  which derives them from SEC financials + quote_prices, and through
  the per-ticker `Ticker.info` path which is preserved.

## Decision

Add a new batch method on `YahooFinanceClient`,
`get_screening_info_batch(tickers, batch_size=1000)`, that calls
`/v7/finance/quote` directly via `yfinance.data.YfData`. Refactor
`enrich_with_yahoo()` to:

1. Pull all eligible tickers in one shot from
   `list_eligible_for_enrich`.
2. Fetch them via `get_screening_info_batch` in 1000-symbol batches.
3. Persist the results through a new bulk-aware method
   `ScreeningRepository.bulk_upsert_cache(payloads)` that issues one
   commit per service call.

Keep `get_screening_info()` as the per-ticker entry point. Callers that
need `sector`/`industry`/`beta` and friends continue to use it.

## Consequences

### Positive

- ~60x speed improvement on Yahoo enrichment (8 minutes → ~8 seconds).
- Far fewer HTTP requests, reducing the chance of being rate-limited or
  blocked by Yahoo.
- DB persistence collapses from 10,376 commits to 1 commit (or 1 per
  row in the fallback path).

### Risks and mitigations

- **Existing column values must be preserved.** A naive multi-row
  INSERT with `ON CONFLICT DO UPDATE SET ...=excluded.*` would expand
  any column missing from a payload to NULL and overwrite the existing
  value through `excluded.col`. `bulk_upsert_cache` therefore groups
  payloads by their key set and emits one INSERT per group, listing
  only the columns actually present in the payload. If a group has no
  updatable columns (normalize stripped everything), it falls back to
  `ON CONFLICT DO NOTHING`.
- **Bulk DB failure must not stop the world.** If the batch upsert
  raises (deadlock, constraint violation, etc.), the service rolls
  back and falls back to per-row `upsert_cache`, tracking individual
  successes and failures separately on `EnrichResult`. R7 pattern is
  preserved.
- **`max_concurrency` is now ignored** but kept on the public
  signature so the CLI (`screening enrich --max-concurrency`) does
  not break. A future cleanup can deprecate it through the CLI layer.

## Out of scope

This ADR covers Step 1 only of the design in
`docs/superpowers/specs/2026-05-09-yahoo-batch-api-design.md`.
Steps 2 (financial_data bulk fetch) and 3 (bulk metric computation)
remain in the design doc as future work.
