"""Provider symbol mapping for quote services."""
from __future__ import annotations


_GOOGLE_EXCHANGE_PREFIXES = {
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "AMEX": "NYSEAMERICAN",
    "NYSE AMERICAN": "NYSEAMERICAN",
    "NYSE ARCA": "NYSEARCA",
    "CBOE BZX": "BATS",
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
    prefix = _GOOGLE_EXCHANGE_PREFIXES.get(exchange.strip().upper())
    if prefix is None:
        return None
    return f"{prefix}:{normalized_ticker}"
