"""AsyncRateLimiter + BaseClient のテスト"""
import time

import pytest

from stock_analyze_system.ingestion.base import AsyncRateLimiter, BaseClient


class TestAsyncRateLimiter:
    async def test_first_acquire_immediate(self):
        limiter = AsyncRateLimiter(rate=10, interval=1.0)
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    async def test_rate_limiting_delays(self):
        limiter = AsyncRateLimiter(rate=2, interval=1.0)
        await limiter.acquire()
        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.3  # should wait ~0.5s

    async def test_wait_updates_schedule_for_next_caller(self, monkeypatch):
        """待機後すぐの次呼び出しも次トークンまで待つこと"""
        now = 0.0
        sleeps: list[float] = []

        def fake_monotonic():
            return now

        async def fake_sleep(seconds: float):
            nonlocal now
            sleeps.append(seconds)
            now += seconds

        monkeypatch.setattr(
            "stock_analyze_system.ingestion.base.time.monotonic",
            fake_monotonic,
        )
        monkeypatch.setattr(
            "stock_analyze_system.ingestion.base.asyncio.sleep",
            fake_sleep,
        )

        limiter = AsyncRateLimiter(rate=2, interval=1.0)
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

        assert sleeps == [pytest.approx(0.5), pytest.approx(0.5)]

    async def test_initial_allowance_can_prevent_initial_burst(self, monkeypatch):
        """初期 allowance を 1 にすると初回以外は rate 間隔で待つこと"""
        now = 0.0
        sleeps: list[float] = []

        def fake_monotonic():
            return now

        async def fake_sleep(seconds: float):
            nonlocal now
            sleeps.append(seconds)
            now += seconds

        monkeypatch.setattr(
            "stock_analyze_system.ingestion.base.time.monotonic",
            fake_monotonic,
        )
        monkeypatch.setattr(
            "stock_analyze_system.ingestion.base.asyncio.sleep",
            fake_sleep,
        )

        limiter = AsyncRateLimiter(rate=10, interval=1.0, initial_allowance=1.0)
        for _ in range(11):
            await limiter.acquire()

        assert sleeps == [pytest.approx(0.1) for _ in range(10)]

    async def test_zero_rate_raises(self):
        with pytest.raises(ValueError):
            AsyncRateLimiter(rate=0, interval=1.0)


class TestBaseClient:
    async def test_get_success(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", json={"ok": True})
        async with BaseClient(rate=10) as client:
            resp = await client._get("https://example.com/api")
            assert resp.status_code == 200
            assert resp.json() == {"ok": True}

    async def test_retry_on_429(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        httpx_mock.add_response(url="https://example.com/api", json={"ok": True})
        async with BaseClient(rate=10, max_retries=2, initial_backoff=0.01) as client:
            resp = await client._get("https://example.com/api")
            assert resp.status_code == 200

    async def test_retry_on_503(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", status_code=503)
        httpx_mock.add_response(url="https://example.com/api", json={"ok": True})
        async with BaseClient(rate=10, max_retries=2, initial_backoff=0.01) as client:
            resp = await client._get("https://example.com/api")
            assert resp.status_code == 200

    async def test_max_retries_exceeded(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        from stock_analyze_system.exceptions import ApiConnectionError
        async with BaseClient(rate=10, max_retries=2, initial_backoff=0.01) as client:
            with pytest.raises(ApiConnectionError):
                await client._get("https://example.com/api")

    async def test_no_retry_on_404(self, httpx_mock):
        """404等の非リトライ対象ステータスはリトライしない"""
        httpx_mock.add_response(url="https://example.com/api", status_code=404)
        import httpx as httpx_lib
        async with BaseClient(rate=10, max_retries=3, initial_backoff=0.01) as client:
            with pytest.raises(httpx_lib.HTTPStatusError):
                await client._get("https://example.com/api")

    async def test_custom_headers(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api")
        async with BaseClient(rate=10, headers={"User-Agent": "TestBot"}) as client:
            await client._get("https://example.com/api")
        request = httpx_mock.get_request()
        assert request.headers["User-Agent"] == "TestBot"

    async def test_context_manager(self):
        client = BaseClient(rate=10)
        async with client:
            assert client._client is not None
