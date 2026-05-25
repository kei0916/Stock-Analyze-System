"""Yahoo Finance クライアント (yfinance同期API → asyncio.to_thread ラップ)"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

import yfinance
from yfinance.data import YfData

from stock_analyze_system.ingestion.base import AsyncRateLimiter
from stock_analyze_system.shared.financial import derive_fcf

_V7_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_V7_BATCH_SIZE = 1000

_BATCH_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("market_cap", "marketCap"),
    ("trailing_per", "trailingPE"),
    ("forward_per", "forwardPE"),
    ("pbr", "priceToBook"),
    ("dividend_yield", "dividendYield"),
    ("exchange", "exchange"),
    ("fifty_two_week_high", "fiftyTwoWeekHigh"),
    ("fifty_two_week_low", "fiftyTwoWeekLow"),
    ("volume", "averageVolume"),
    ("eps", "trailingEps"),
)

logger = logging.getLogger(__name__)


def _epoch_to_date(epoch: int | float) -> str:
    """Unixエポックを ISO日付文字列に変換"""
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d")


def _extract_price(quote: dict) -> float | None:
    """Yahoo quote dict から現在株価を取得 (regularMarketPrice 優先, currentPrice fallback)."""
    return quote.get("regularMarketPrice") or quote.get("currentPrice")


class YahooFinanceClient:
    """yfinance ラッパー（asyncio.to_thread で非同期化）

    M3注記: BaseClient を継承しない。yfinance は同期ライブラリであり
    httpx.AsyncClient は不要。AsyncRateLimiter のみ使用して
    asyncio.to_thread() でスレッドプールに委譲する設計。
    """

    def __init__(self, rate: float = 2.0):
        self._rate_limiter = AsyncRateLimiter(rate=rate)

    async def get_stock_price(self, ticker: str) -> dict | None:
        """現在の株価情報を取得"""
        await self._rate_limiter.acquire()
        try:
            info = await asyncio.to_thread(self._fetch_info, ticker)
            price = _extract_price(info)
            if price is None:
                return None
            return {
                "price": price,
                "market_cap": info.get("marketCap"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "currency": info.get("currency"),
            }
        except Exception as e:
            logger.warning("Yahoo Finance error for %s: %s", ticker, e, exc_info=True)
            return None

    async def get_screening_info(self, ticker: str) -> dict | None:
        """スクリーニング用の総合情報を取得"""
        await self._rate_limiter.acquire()
        try:
            info = await asyncio.to_thread(self._fetch_info, ticker)
            price = _extract_price(info)
            if price is None:
                return None

            mcap = info.get("marketCap")
            fcf = info.get("freeCashflow")
            fcf_yield = (fcf / mcap) if (fcf is not None and mcap) else None

            de = info.get("debtToEquity")
            de_ratio = de / 100.0 if de is not None else None

            mrq = info.get("mostRecentQuarter")
            lfy = info.get("lastFiscalYearEnd")
            mrq_str = _epoch_to_date(mrq) if mrq else None
            lfy_str = _epoch_to_date(lfy) if lfy else None

            return {
                "stock_price": price,
                "market_cap": mcap,
                "trailing_per": info.get("trailingPE"),
                "eps": info.get("trailingEps"),
                "forward_per": info.get("forwardPE"),
                "pbr": info.get("priceToBook"),
                "psr": info.get("priceToSalesTrailing12Months"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "dividend_yield": info.get("dividendYield"),
                "roe": info.get("returnOnEquity"),
                "operating_margin": info.get("operatingMargins"),
                "net_margin": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "de_ratio": de_ratio,
                "peg_ratio": info.get("pegRatio"),
                "fcf_yield": fcf_yield,
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "exchange": info.get("exchange"),
                "beta": info.get("beta"),
                "volume": info.get("averageVolume"),
                "most_recent_quarter": mrq_str,
                "last_fiscal_year_end": lfy_str,
                "trailing_eps_date": f"TTM ending {mrq_str}" if mrq_str else "TTM",
            }
        except Exception as e:
            logger.warning("Yahoo Finance screening error for %s: %s", ticker, e, exc_info=True)
            return None

    async def get_screening_info_batch(
        self,
        tickers: list[str],
        batch_size: int = _V7_BATCH_SIZE,
    ) -> dict[str, dict]:
        """Yahoo Finance v7 batch API で複数銘柄の情報を一括取得.

        Args:
            tickers: ティッカーシンボルリスト.
            batch_size: 1リクエストの最大銘柄数 (default 1000).

        Returns:
            {ticker: screening_info_dict}. 取得失敗銘柄は含まれない.
        """
        if not tickers:
            return {}

        results: dict[str, dict] = {}
        data = YfData()

        for start in range(0, len(tickers), batch_size):
            batch = tickers[start : start + batch_size]
            symbols = ",".join(batch)

            await self._rate_limiter.acquire()
            try:
                response = await asyncio.to_thread(
                    data.get_raw_json,
                    _V7_QUOTE_URL,
                    params={"symbols": symbols, "formatted": "false"},
                )
            except Exception as exc:  # noqa: BLE001 (R7: warn + 続行)
                logger.warning(
                    "Yahoo batch error for batch %d-%d: %s",
                    start, start + len(batch) - 1, exc,
                )
                continue

            if not response or "quoteResponse" not in response:
                logger.warning(
                    "Yahoo batch empty response for batch %d-%d",
                    start, start + len(batch) - 1,
                )
                continue

            quotes = response["quoteResponse"].get("result") or []
            for quote in quotes:
                parsed = self._parse_batch_quote(quote)
                if parsed is None:
                    continue
                symbol, info = parsed
                results[symbol] = info

        return results

    @staticmethod
    def _parse_batch_quote(quote: dict) -> tuple[str, dict] | None:
        symbol = quote.get("symbol")
        if not symbol:
            return None
        price = _extract_price(quote)
        if price is None:
            return None
        info: dict = {"stock_price": price}
        for local_key, yahoo_key in _BATCH_FIELD_MAP:
            value = quote.get(yahoo_key)
            if value is not None:
                info[local_key] = value
        return symbol, info

    async def get_quarterly_financials(self, ticker: str) -> list[dict]:
        """四半期財務データを取得"""
        await self._rate_limiter.acquire()
        try:
            return await asyncio.to_thread(self._fetch_quarterly, ticker)
        except Exception as e:
            logger.warning("Yahoo Finance quarterly error for %s: %s", ticker, e, exc_info=True)
            return []

    async def get_price_history(
        self, ticker: str, period: str = "10y",
    ) -> list[dict]:
        """株価履歴を取得"""
        await self._rate_limiter.acquire()
        try:
            return await asyncio.to_thread(self._fetch_history, ticker, period)
        except Exception as e:
            logger.warning("Yahoo Finance history error for %s: %s", ticker, e, exc_info=True)
            return []

    @staticmethod
    def _fetch_info(ticker: str) -> dict:
        return yfinance.Ticker(ticker).info or {}

    @staticmethod
    def _fetch_quarterly(ticker: str) -> list[dict]:
        t = yfinance.Ticker(ticker)
        income = t.quarterly_income_stmt
        balance = t.quarterly_balance_sheet
        cashflow = t.quarterly_cashflow

        if income is None or income.empty:
            return []

        def _yf_val(df, col, *row_labels) -> float | None:
            if df is None or df.empty or col not in df.columns:
                return None
            for label in row_labels:
                if label in df.index:
                    val = df.at[label, col]
                    if isinstance(val, float) and math.isnan(val):
                        return None
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return None
            return None

        records = []
        for col in income.columns:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)

            rev = _yf_val(income, col, "Total Revenue", "Revenue")
            op_inc = _yf_val(income, col, "Operating Income", "Operating Revenue")
            ni = _yf_val(income, col, "Net Income", "Net Income Common Stockholders")
            ebitda_val = _yf_val(income, col, "EBITDA", "Normalized EBITDA")
            eps_val = _yf_val(income, col, "Diluted EPS", "Basic EPS")
            cogs_val = _yf_val(income, col, "Cost Of Revenue")
            tax_val = _yf_val(income, col, "Tax Provision", "Income Tax Expense")
            ibt = _yf_val(income, col, "Pretax Income")

            ta = _yf_val(balance, col, "Total Assets")
            eq = _yf_val(balance, col, "Stockholders Equity", "Total Equity Gross Minority Interest")
            ca = _yf_val(balance, col, "Current Assets")
            cl = _yf_val(balance, col, "Current Liabilities")
            td = _yf_val(balance, col, "Total Debt")
            cash_val = _yf_val(balance, col, "Cash And Cash Equivalents")
            inv = _yf_val(balance, col, "Inventory")
            shares = _yf_val(balance, col, "Share Issued", "Ordinary Shares Number")

            op_cf = _yf_val(cashflow, col, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
            capex_val = _yf_val(cashflow, col, "Capital Expenditure")
            fcf_val = _yf_val(cashflow, col, "Free Cash Flow")
            div_paid = _yf_val(cashflow, col, "Common Stock Dividend Paid", "Cash Dividends Paid")
            repurch = _yf_val(cashflow, col, "Repurchase Of Capital Stock")

            rec = {
                "fiscal_year_end": date_str,
                "revenue": rev, "operating_income": op_inc, "net_income": ni,
                "total_assets": ta, "equity": eq, "current_assets": ca,
                "current_liabilities": cl, "total_debt": td, "cash": cash_val,
                "inventory": inv, "cogs": cogs_val,
                "operating_cf": op_cf, "capex": capex_val, "fcf": fcf_val,
                "ebitda": ebitda_val, "eps": eps_val,
                "tax_expense": tax_val, "income_before_tax": ibt,
                "shares_outstanding": shares,
                "dividends_paid": div_paid, "share_repurchases": repurch,
                "dps": None,
            }
            derive_fcf(rec)
            records.append(rec)

        return records

    @staticmethod
    def _fetch_history(ticker: str, period: str) -> list[dict]:
        hist = yfinance.Ticker(ticker).history(period=period)
        if hist is None or hist.empty:
            return []
        records = []
        for idx, row in hist.iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })
        return records
