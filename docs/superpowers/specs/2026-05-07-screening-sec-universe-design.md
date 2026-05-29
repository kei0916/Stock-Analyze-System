# Screening SEC Universe Design

## Goal

Screening should use all companies present in the SEC ticker universe, not the
analysis target list. The first refresh should add the current SEC universe, and
later refreshes should add newly listed SEC filers as they appear in SEC data.

## Approach

Use the existing SEC `company_tickers_exchange.json` ingestion path as the
screening universe source. `ScreeningUniverseService.refresh_universe()` already
upserts SEC ticker entries into `companies` and preserves existing accounting
standards. The change is to make metric refresh flows call this universe refresh
before selecting companies to enrich.

## Scope

- `screening refresh --source yahoo` runs SEC universe refresh first, then Yahoo
  enrichment.
- `screening refresh --source sec-google` runs SEC universe refresh first, then
  SEC financials plus Google Sheets quote metric computation.
- The screening query path remains unchanged. It already reads from
  `screening_cache` joined to `companies`, not `analysis_targets`.
- `screening add-targets` remains an explicit action for adding selected results
  to analysis targets.

## Error Handling

If SEC universe refresh fails, the refresh command should fail rather than
silently running against a stale or partial universe. This avoids presenting an
old universe as current.

## Persistence

SEC ticker universe payloads are large enough to exceed SQLite's bound variable
limit when inserted as one statement. Native bulk upserts must split rows into
safe batches before executing.

## Tests

- CLI test verifies Yahoo refresh calls `refresh_universe()` before
  `enrich_with_yahoo()`.
- CLI test verifies `sec-google` refresh calls `refresh_universe()` before
  `refresh_from_sec_google()`.
- Service test verifies `ScreeningMetricsService.refresh_from_sec_google()`
  accepts an optional universe refresher and calls it before listing companies.
- Repository test verifies large insert-only upserts are chunked and can insert
  SEC-universe-scale company rows.
