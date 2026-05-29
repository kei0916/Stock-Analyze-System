"""ASGI middleware for request-level web security checks."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse

_HOST_HEADER_RE = re.compile(r"[A-Za-z0-9.\-:\[\]]+")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class HostHeaderGuardMiddleware:
    """Reject malformed Host headers before Starlette builds request URLs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        hosts = _header_values(scope, b"host")
        if len(hosts) != 1 or not _is_safe_host_header(hosts[0]):
            response = PlainTextResponse("Invalid Host header", status_code=400)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class StateChangeOriginGuardMiddleware:
    """Reject cross-origin unsafe requests before state-changing routes run."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        hosts = _header_values(scope, b"host")
        origins = _header_values(scope, b"origin")
        referers = _header_values(scope, b"referer")

        host = _decode_ascii_header(hosts[0]) if len(hosts) == 1 else ""
        if _has_conflicting_source_headers(origins, referers) or not _is_allowed_request_origin(
            host,
            origins,
            referers,
        ):
            response = PlainTextResponse("Cross-origin state change rejected", status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _header_values(scope, header_name: bytes) -> list[bytes]:
    return [
        value
        for name, value in scope.get("headers", [])
        if name.lower() == header_name
    ]


def _is_safe_host_header(raw: bytes) -> bool:
    host = _decode_ascii_header(raw)
    return bool(host and _HOST_HEADER_RE.fullmatch(host))


def _has_conflicting_source_headers(origins: list[bytes], referers: list[bytes]) -> bool:
    return len(origins) > 1 or len(referers) > 1


def _is_allowed_request_origin(
    host: str,
    origins: list[bytes],
    referers: list[bytes],
) -> bool:
    if origins:
        return _origin_or_referer_matches_host(_decode_ascii_header(origins[0]), host)
    if referers:
        return _origin_or_referer_matches_host(_decode_ascii_header(referers[0]), host)
    return True


def _origin_or_referer_matches_host(value: str, host: str) -> bool:
    if not value or not host:
        return False
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return parsed.netloc.lower() == host.lower()


def _decode_ascii_header(raw: bytes) -> str:
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return ""
