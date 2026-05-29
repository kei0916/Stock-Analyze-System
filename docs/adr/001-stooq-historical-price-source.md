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
- Must respect stooq rate limits (1 req / 1 sec) to avoid being blocked
- API key may expire; manual re-acquisition may be needed
- User-Agent must identify the system for terms compliance
- Invalid API key is a global failure (fail-fast), not per-ticker
