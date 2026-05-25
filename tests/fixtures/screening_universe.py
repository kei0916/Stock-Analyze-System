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
