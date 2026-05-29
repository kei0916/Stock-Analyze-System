# SEC EDGAR Daily Filing-Based Update Design

## Status

Approved by user on 2026-04-28.

## Goal

Change the US daily update path so SEC EDGAR work is driven by filings whose
SEC `filingDate` is the target date. The job should stop doing daily
all-company SEC EDGAR financial synchronization and all-company SEC EDGAR filing
polling.

The daily update should:

- Fetch only SEC filings for the target `filingDate`.
- Register filings only for companies that already exist in `companies`.
- Update SEC financial data only for existing companies that had a financial
  reporting filing on that date.
- Respect SEC EDGAR's 10 requests/second fair-access ceiling.

## Non-Goals

- Auto-register companies that appear in the daily SEC feed but are not already
  present in `companies`.
- Change JP/EDINET daily update behavior.
- Replace manual or single-company SEC synchronization paths.
- Download and store complete filing documents.
- Build a new scheduler. Existing `jobs daily --market us` and
  `scripts/cron-daily-update.sh` remain the entry points.

## Current Behavior

`JobService.run_daily_update(market="us")` filters all registered companies by
the `US_` prefix, then calls `sync_company()` for each one.

For every US company with a CIK, `sync_company()` currently:

1. Calls `FinancialSyncService.update_from_sec()`, which fetches SEC
   `companyfacts` and upserts annual and quarterly financial records.
2. Calls `FilingSyncService.update_from_sec()`, which fetches the company's SEC
   `submissions` history and registers recent filings.
3. Updates valuation data from Yahoo Finance.

This means daily US updates can make SEC EDGAR requests for every registered US
company even if no filing was submitted on that date.

## External SEC Constraints

The implementation should follow SEC public guidance:

- SEC fair access currently allows a maximum of 10 requests/second.
- SEC submissions and XBRL APIs are updated throughout the day as filings are
  disseminated.
- EDGAR daily/latest filing sources expose CIK, form type, filing date, company
  name, and filing path or accession metadata.

Primary references:

- https://www.sec.gov/os/accessing-edgar-data
- https://www.sec.gov/edgar/sec-api-documentation
- https://www.sec.gov/about/developer-resources

## Proposed Behavior

For `jobs daily --market us`:

1. Fetch SEC filings for the target SEC `filingDate`.
2. Filter the feed to target form types:
   - Filing registration default: `10-K`, `10-Q`, `20-F`, `40-F`, `8-K`, `6-K`
   - Financial refresh triggers: `10-K`, `10-Q`, `20-F`, `40-F`
3. Match each SEC filing to an existing company by normalized CIK.
4. Skip filings whose CIK does not match any existing company.
5. Register new filings through the existing filing repository path, preserving
   accession-based idempotency.
6. For each matched company with at least one financial refresh trigger filing,
   call `FinancialSyncService.update_from_sec()` once.
7. Continue valuation updates for companies that were actually processed by the
   filing-driven US daily path.

For `jobs daily --market jp`, keep the current EDINET behavior.

## Date Semantics

The target date is SEC `filingDate`, not local machine date and not report
period end date. Add an optional `--filing-date YYYY-MM-DD` argument to
`jobs daily --market us`. If the argument is not supplied, derive the default
from the current date in the `America/New_York` timezone so the default aligns
with SEC filing-date semantics rather than the server's local timezone.

Keep the service API explicit: `run_daily_update()` should accept a
`target_date` argument for deterministic tests and scheduler control.

## SEC Filing Feed Abstraction

Add a SEC client method that returns daily filing records from a SEC daily/latest
filings source. Each normalized record should contain:

- `cik`
- `companyName`
- `form`
- `filingDate`
- `accessionNumber`
- `primaryDocument` when available
- `primaryDocDescription` when available
- `documentUrl` when enough metadata is available

The service layer should depend on this normalized shape rather than on the raw
SEC feed payload.

## Company Matching

Company matching is CIK-only:

- Normalize SEC feed CIK and `Company.cik` to 10-digit zero-padded strings.
- Match only existing `Company` rows.
- If multiple companies share a CIK, process each matching registered company.
  This is unlikely for the current US ticker-based model, but it avoids silently
  dropping user-maintained aliases.

Build an in-memory CIK map from the existing `CompanyService.list_companies()`
result already used by `run_daily_update()`. This keeps the first change small
and avoids adding repository surface area for a lookup that the daily job can
perform from its existing company list.

## Filing Registration

Add a `FilingSyncService` entry point that accepts pre-fetched SEC daily feed
records grouped by company and writes them through the existing bulk upsert
behavior. The new path must avoid calling per-company SEC `submissions` when
the daily feed already contains the needed accession metadata.

Filing rows should continue to use:

- `source="SEC"`
- `filing_type` from SEC form type
- `period_type="annual"` for `10-K`, `20-F`, and `40-F`
- `period_type="quarterly"` for other registered SEC forms
- `fiscal_year` derived from `reportDate` when present, otherwise from
  `filingDate`
- `accession_no` from SEC accession number
- `filed_at` from SEC `filingDate`

If `reportDate` is absent from the daily feed for forms such as `8-K`, filing
registration should still proceed using `filingDate` for fiscal-year fallback
and leaving `period_end` empty.

## Financial Refresh

Financial refresh is per company, not per filing. If a company has multiple
financial trigger filings on the target date, call
`FinancialSyncService.update_from_sec()` once.

Default financial trigger forms:

- `10-K`
- `10-Q`
- `20-F`
- `40-F`

Default non-financial filing-only forms:

- `8-K`
- `6-K`

The financial refresh remains the existing SEC `companyfacts` based path. This
keeps parser and repository behavior unchanged while preventing daily
all-company companyfacts polling.

## Rate Limit Design

Set SEC EDGAR default and configured request rate to 10 requests/second:

- `SecEdgarConfig.rate_limit_rps` default: `10`
- `config/settings.yaml.example` `sec_edgar.rate_limit_rps`: `10`
- CLI and web service construction pass `config.sec_edgar.rate_limit_rps` into
  `SecEdgarClient`
- `SecEdgarClient` constructor default: `10.0`

The shared `AsyncRateLimiter` remains the enforcement mechanism. The daily
filing-driven workflow also reduces request volume by avoiding per-company SEC
requests when no filing exists.

## Error Handling

- SEC daily feed fetch failure should be recorded as a US daily update error and
  should not fall back to all-company SEC polling.
- Invalid or incomplete feed rows should be skipped with a warning.
- A filing registration failure for one company should be isolated from other
  companies where the existing repository/service boundaries make that practical.
- Financial refresh errors should be captured on that company's `SyncResult`
  without stopping the rest of the daily run.
- Unknown CIKs are expected and should be skipped without an error count.

## Reporting

`DailyUpdateResult` should remain compatible with existing callers. The US
filing-driven path should populate `SyncResult` entries for matched companies
that were processed. Skipped unknown CIKs do not require a `SyncResult` because
they are outside the registered universe.

Useful log fields:

- target filing date
- SEC feed row count
- filtered filing count
- unknown CIK skip count
- matched company count
- filing insert/update count
- financial refresh company count

## Testing

Unit tests should cover:

- SEC daily feed normalization.
- 10 req/s SEC rate configuration propagation.
- US daily update does not call all-company `sync_company()`.
- Existing registered company receives filing registration from the target
  `filingDate`.
- Unknown CIK is skipped.
- `8-K` registers filing but does not call financial refresh.
- `10-K`, `10-Q`, `20-F`, and `40-F` register filing and call financial refresh
  once per company.
- Duplicate accessions remain idempotent.
- JP daily update behavior remains unchanged.

## Acceptance Criteria

- Running `jobs daily --market us` no longer performs SEC financial and filing
  sync for every registered US company.
- US daily SEC work is based on SEC `filingDate`.
- SEC daily filings for existing companies are registered.
- SEC financial data is refreshed only for existing companies with financial
  trigger filings on the target date.
- SEC EDGAR request rate is configured at 10 requests/second.
- Existing single-company sync remains available for explicit manual use.
