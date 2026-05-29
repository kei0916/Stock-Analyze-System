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
        "most_recent_quarter": "2026-03-31",
        "last_fiscal_year_end": "2025-12-31",
        "trailing_eps_date": "TTM ending 2026-03-31",
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
