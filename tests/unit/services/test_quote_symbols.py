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
        ("AMEX", "LNG", "NYSEAMERICAN:LNG"),
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
