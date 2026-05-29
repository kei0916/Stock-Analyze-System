"""Financial Modeling Prep API クライアント (async)"""
from __future__ import annotations

import logging
from typing import Any

from stock_analyze_system.exceptions import ApiConnectionError, ApiResponseError
from stock_analyze_system.ingestion.base import BaseClient
from stock_analyze_system.models.enums import PeriodType

logger = logging.getLogger(__name__)


class FmpClient(BaseClient):
    """FMP API クライアント（無料プラン: 250 req/day, 5 req/s）"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://financialmodelingprep.com/stable",
        rate: float = 5.0,
    ):
        super().__init__(rate=rate)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def _get_json(self, path: str, params: dict | None = None) -> Any:
        """内部GET + 認証 + エラーチェック"""
        url = f"{self._base_url}/{path.lstrip('/')}"
        params = params or {}
        params["apikey"] = self._api_key
        resp = await self._get(url, params=params)
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            raise ApiResponseError(data["Error Message"])
        return data

    async def quote(self, ticker: str) -> dict | None:
        """株価クオートを取得"""
        data = await self._get_json(f"/quote/{ticker}")
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    async def profile(self, ticker: str) -> dict | None:
        """企業プロファイルを取得"""
        data = await self._get_json(f"/profile/{ticker}")
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    async def search_name(
        self, query: str, exchange: str | None = None, limit: int = 50,
    ) -> list[dict]:
        """企業名検索"""
        params: dict[str, Any] = {"query": query, "limit": limit}
        if exchange:
            params["exchange"] = exchange
        data = await self._get_json("/search-name", params=params)
        return data if isinstance(data, list) else []

    async def get_financial_statements(self, ticker: str) -> dict | None:
        """財務諸表を取得"""
        data = await self._get_json(f"/income-statement/{ticker}", {"period": PeriodType.ANNUAL})
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    async def get_company_profile(self, ticker: str) -> dict | None:
        """企業プロファイルを取得（profileのエイリアス）"""
        return await self.profile(ticker)

    async def get_stock_news(
        self, ticker: str, limit: int = 10,
    ) -> list[dict]:
        """株式ニュースを取得"""
        data = await self._get_json(
            "/stock_news", params={"tickers": ticker, "limit": limit},
        )
        return data if isinstance(data, list) else []

    async def is_available(self) -> bool:
        """APIキーが有効かチェック"""
        if not self._api_key:
            return False
        try:
            await self.quote("AAPL")
            return True
        except (OSError, ApiConnectionError, ApiResponseError, ValueError, KeyError):
            return False
