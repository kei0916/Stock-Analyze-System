# src/stock_analyze_system/ingestion/stooq.py
from __future__ import annotations

import csv
import io
import logging
from datetime import date as date_type
from datetime import timedelta

import httpx

from stock_analyze_system.ingestion.base import AsyncRateLimiter

logger = logging.getLogger(__name__)

_STOOQ_CSV_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d&apikey={apikey}"
_DEFAULT_TIMEOUT = 30.0
_USER_AGENT = "Stock-Analyze-System/1.0 (research-only)"


class StooqPriceClient:
    """stooq.com から株価履歴CSVを取得するクライアント."""

    def __init__(self, api_key: str, rate: float = 1.0):
        self._api_key = api_key
        self._rate_limiter = AsyncRateLimiter(rate=rate)
        self._client = httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )

    async def fetch_history(
        self, ticker: str, years: int | None = 10,
    ) -> list[dict]:
        """指定tickerの履歴を取得し、yearsでフィルタしてdictリストを返す.

        Args:
            ticker: 大文字のティッカー（e.g. AAPL）
            years: 何年分まで保持するか。Noneなら全履歴。

        Returns:
            古い順（昇順）の dict リスト。

        Raises:
            StooqNotFoundError: 404 returned by stooq
            StooqRateLimitError: Daily hit limit reached
            StooqAuthError: Invalid API key response (global failure)
            StooqParseError: Invalid CSV or HTML response
            httpx.TimeoutException: Request timeout
        """
        await self._rate_limiter.acquire()
        symbol = f"{ticker.lower()}.us"
        url = _STOOQ_CSV_URL.format(symbol=symbol, apikey=self._api_key)
        
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("stooq: ticker not found: %s", ticker)
                raise StooqNotFoundError(ticker) from exc
            raise
        except httpx.TimeoutException:
            logger.warning("stooq: timeout for %s", ticker)
            raise
        
        text = resp.text
        if not text or not text.strip().startswith("Date"):
            # Check rate limit first (exact phrase match)
            if "Exceeded the daily hits limit" in text:
                logger.error("stooq: daily hit limit exceeded for %s", ticker)
                raise StooqRateLimitError(ticker, "daily hit limit exceeded")
            # Then check auth (exact phrase match)
            if "Get your apikey:" in text:
                logger.warning("stooq: invalid API key for %s", ticker)
                raise StooqAuthError(ticker, "invalid API key response")
            # Everything else is parse error
            logger.warning("stooq: invalid response for %s (length=%d)", ticker, len(text))
            raise StooqParseError(ticker, f"invalid response: length={len(text)}")
        
        rows = self._parse_csv(text, ticker, years)
        logger.info("stooq: fetched %d rows for %s", len(rows), ticker)
        return rows

    def _parse_csv(
        self, text: str, ticker: str, years: int | None,
    ) -> list[dict]:
        cutoff: date_type | None = None
        if years is not None:
            cutoff = date_type.today() - timedelta(days=years * 365)
        
        rows: list[dict] = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                row_date = date_type.fromisoformat(row["Date"])
            except (KeyError, ValueError):
                continue
            
            if cutoff is not None and row_date < cutoff:
                continue
            
            rows.append({
                "company_id": None,  # filled by caller
                "ticker": ticker,
                "date": row_date,
                "open": self._to_float(row.get("Open")),
                "high": self._to_float(row.get("High")),
                "low": self._to_float(row.get("Low")),
                "close": self._to_float(row.get("Close")),
                "volume": self._to_float(row.get("Volume")),
                "source": "stooq",
            })
        
        # stooq CSV is newest-first; reverse to oldest-first (ascending)
        rows.reverse()
        return rows

    @staticmethod
    def _to_float(val: str | None) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except ValueError:
            return None

    async def close(self):
        await self._client.aclose()


class StooqError(Exception):
    pass


class StooqNotFoundError(StooqError):
    pass


class StooqAuthError(StooqError):
    pass


class StooqParseError(StooqError):
    pass


class StooqRateLimitError(StooqError):
    """stooq daily hit limit reached."""
    pass
