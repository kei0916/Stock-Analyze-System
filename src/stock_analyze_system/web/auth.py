"""Session-based authentication: signer, middleware, login/logout helpers."""
from __future__ import annotations

import heapq
import logging
import time
from collections.abc import Awaitable, Callable
from collections import deque
from dataclasses import dataclass
from threading import Lock

import bcrypt
from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

SESSION_COOKIE = "stock_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 1 week
PUBLIC_PATHS = frozenset({"/login", "/logout", "/health"})
PUBLIC_PREFIXES = ("/static/",)
# bcrypt 仕様で 72 byte を超える部分は無視される。安全のためアプリ側で
# 明示的に truncate して silent ignore を避ける。
_BCRYPT_MAX_BYTES = 72


class SessionSigner:
    """itsdangerous wrapper that embeds iat for revocation."""

    def __init__(self, secret: str):
        self._serializer = URLSafeTimedSerializer(secret, salt="stock-session")

    def sign(self, user_id: str) -> str:
        return self._serializer.dumps({"u": user_id, "iat": int(time.time())})

    def unsign(self, token: str, *, max_age_seconds: int) -> dict:
        payload = self._serializer.loads(token, max_age=max_age_seconds)
        if isinstance(payload, str):
            # Legacy tokens without iat — treat as issued at epoch 0 so
            # session_issued_after > 0 invalidates them on next request.
            return {"u": payload, "iat": 0}
        return payload


def _truncate(plaintext: str) -> bytes:
    return plaintext.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(submitted: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_truncate(submitted), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(_truncate(plaintext), bcrypt.gensalt()).decode("utf-8")


@dataclass(frozen=True)
class RateLimitLease:
    """Reservation returned when a limiter admits one request."""

    key: str
    token: int


@dataclass(frozen=True)
class _RateLimitEvent:
    token: int
    at: float


class InMemoryRateLimiter:
    """固定ウィンドウ相当の軽量 in-memory rate limiter."""

    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        *,
        now_fn: Callable[[], float] | None = None,
    ):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._events: dict[str, deque[_RateLimitEvent]] = {}
        self._expiry_heap: list[tuple[float, int, str]] = []
        self._bucket_versions: dict[str, int] = {}
        self._lock = Lock()
        self._now_fn = now_fn or time.monotonic
        self._next_token = 0

    def _schedule_expiry(self, key: str, bucket: deque[_RateLimitEvent]) -> None:
        version = self._bucket_versions.get(key, 0) + 1
        self._bucket_versions[key] = version
        heapq.heappush(
            self._expiry_heap,
            (bucket[0].at + self._window_seconds, version, key),
        )

    def _trim(self, key: str, now: float) -> deque[_RateLimitEvent] | None:
        bucket = self._events.get(key)
        if bucket is None:
            return None
        trimmed = False
        while bucket and (now - bucket[0].at) >= self._window_seconds:
            bucket.popleft()
            trimmed = True
        if not bucket:
            self._events.pop(key, None)
            self._bucket_versions.pop(key, None)
            return None
        if trimmed:
            self._schedule_expiry(key, bucket)
        return bucket

    def _prune_expired(self, now: float) -> None:
        while self._expiry_heap and self._expiry_heap[0][0] <= now:
            _, version, key = heapq.heappop(self._expiry_heap)
            if self._bucket_versions.get(key) != version:
                continue
            self._trim(key, now)

    def try_acquire(self, key: str) -> RateLimitLease | None:
        """Atomically trim, check capacity, and reserve one slot."""
        now = self._now_fn()
        with self._lock:
            self._prune_expired(now)
            bucket = self._trim(key, now)
            if bucket is None:
                bucket = deque()
                self._events[key] = bucket
            if len(bucket) >= self._max_attempts:
                return None
            token = self._next_token
            self._next_token += 1
            was_empty = not bucket
            bucket.append(_RateLimitEvent(token=token, at=now))
            if was_empty:
                self._schedule_expiry(key, bucket)
            return RateLimitLease(key=key, token=token)

    def release(self, lease: RateLimitLease) -> None:
        """Release one previously-acquired slot."""
        now = self._now_fn()
        with self._lock:
            self._prune_expired(now)
            bucket = self._trim(lease.key, now)
            if bucket is None:
                return
            removed_oldest = bool(bucket and bucket[0].token == lease.token)
            remaining = deque(
                event for event in bucket if event.token != lease.token
            )
            if len(remaining) == len(bucket):
                return
            if remaining:
                self._events[lease.key] = remaining
                if removed_oldest:
                    self._schedule_expiry(lease.key, remaining)
            else:
                self._events.pop(lease.key, None)
                self._bucket_versions.pop(lease.key, None)


def _get_effective_client_host(request: Request) -> str:
    host = request.client.host if request.client is not None else "unknown"
    app_state = getattr(request.app.state, "app_state", None)
    config = getattr(app_state, "config", None)
    web_config = getattr(config, "web", None)
    if web_config is None or not getattr(web_config, "trust_proxy_headers", False):
        return host

    trusted_proxy_hosts = set(getattr(web_config, "trusted_proxy_hosts", []))
    if host not in trusted_proxy_hosts:
        return host

    hops = max(1, int(getattr(web_config, "trusted_proxy_hops", 1)))
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        chain = [c.strip() for c in forwarded_for.split(",") if c.strip()]
        # Pick the right-most untrusted hop: chain ends with the most-recent
        # proxy; skip `hops - 1` trusted proxies, then take the next-left entry.
        idx = len(chain) - hops
        if 0 <= idx < len(chain):
            return chain[idx]

    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip

    return host


def get_client_key(request: Request, scope: str) -> str:
    return f"{scope}:{_get_effective_client_host(request)}"


def enforce_heavy_request_limit(
    request: Request, *, scope: str, detail: str,
) -> None:
    limiter = request.app.state.heavy_rate_limiter
    key = get_client_key(request, scope)
    if limiter.try_acquire(key) is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """未認証リクエストを /login にリダイレクトする"""

    def __init__(self, app, signer: SessionSigner):
        super().__init__(app)
        self._signer = signer

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if _is_public(request.url.path):
            request.state.user = None
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return RedirectResponse(
                url="/login", status_code=status.HTTP_303_SEE_OTHER,
            )

        try:
            payload = self._signer.unsign(token, max_age_seconds=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            logger.info("Rejected invalid session for %s", request.url.path)
            return RedirectResponse(
                url="/login", status_code=status.HTTP_303_SEE_OTHER,
            )

        app_state = getattr(request.app.state, "app_state", None)
        invalidated_after = getattr(
            getattr(getattr(app_state, "config", None), "web", None),
            "session_issued_after",
            0,
        )
        if payload.get("iat", 0) < invalidated_after:
            logger.info("Rejected pre-revoke session for %s", request.url.path)
            return RedirectResponse(
                url="/login", status_code=status.HTTP_303_SEE_OTHER,
            )

        request.state.user = payload.get("u")
        return await call_next(request)


def require_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
