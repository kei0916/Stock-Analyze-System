"""非同期レートリミッター + HTTP基底クライアント"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from stock_analyze_system.exceptions import ApiConnectionError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 503}


class AsyncRateLimiter:
    """asyncio.sleep ベースのトークンバケットレートリミッター"""

    def __init__(
        self,
        rate: float,
        interval: float = 1.0,
        initial_allowance: float | None = None,
    ):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._interval = interval
        self._allowance = (
            rate if initial_allowance is None else min(initial_allowance, rate)
        )
        self._last_check = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_check
            self._last_check = now
            self._allowance += elapsed * (self._rate / self._interval)
            if self._allowance > self._rate:
                self._allowance = self._rate
            if self._allowance < 1.0:
                wait = (1.0 - self._allowance) * (self._interval / self._rate)
                await asyncio.sleep(wait)
                self._last_check = time.monotonic()
                self._allowance = 0.0
            else:
                self._allowance -= 1.0


class BaseClient:
    """全APIクライアントの基底クラス（httpx.AsyncClient + リトライ）"""

    def __init__(
        self,
        rate: float = 5.0,
        interval: float = 1.0,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
        max_backoff: float = 60.0,
        initial_allowance: float | None = None,
        headers: dict[str, str] | None = None,
    ):
        self._rate_limiter = AsyncRateLimiter(
            rate=rate,
            interval=interval,
            initial_allowance=initial_allowance,
        )
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """HTTPリクエスト + 指数バックオフリトライ。

        max_retries はリトライ回数（初回含まず）。合計試行回数 = 1 + max_retries。
        リトライ対象は RETRYABLE_STATUS_CODES (429, 503) と接続エラーのみ。
        404等の非リトライ対象エラーは即座に raise する。
        """
        client = await self._ensure_client()
        backoff = self._initial_backoff
        last_exc: Exception | None = None
        total_attempts = 1 + self._max_retries

        for attempt in range(total_attempts):
            await self._rate_limiter.acquire()
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_exc = ApiConnectionError(
                        f"Retryable status {response.status_code} from {url}"
                    )
                    logger.warning(
                        "Retryable status %d from %s (attempt %d/%d)",
                        response.status_code, url, attempt + 1, total_attempts,
                    )
                else:
                    response.raise_for_status()
                    return response
            except httpx.HTTPStatusError:
                # 非リトライ対象ステータスエラー（404等）は即座に raise
                raise
            except httpx.HTTPError as exc:
                # 接続/タイムアウトエラーはリトライ対象
                last_exc = exc
                logger.warning(
                    "HTTP error from %s (attempt %d/%d): %s",
                    url, attempt + 1, total_attempts, exc,
                )
            if attempt < total_attempts - 1:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)

        raise ApiConnectionError(
            f"Max retries ({self._max_retries}) exceeded for {url}"
        ) from last_exc

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self._ensure_client()
        return self

    async def __aexit__(self, *args):
        await self.close()
