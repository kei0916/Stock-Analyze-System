"""FastAPI app factory — wires routes, middleware, lifespan, templates."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from stock_analyze_system.config import AppConfig, load_config
from stock_analyze_system.exceptions import ConfigError
from stock_analyze_system.web.dependencies import AppState
from stock_analyze_system.web.security import (
    HostHeaderGuardMiddleware,
    StateChangeOriginGuardMiddleware,
)

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = _PACKAGE_DIR / "templates"
STATIC_DIR = _PACKAGE_DIR / "static"


_DESIGN_PREVIEW_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://unpkg.com",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def _add_security_headers(
    response,
    *,
    path: str = "",
    secure_cookies: bool = False,
    hsts_max_age: int = 31536000,
):
    """レスポンスに OWASP 推奨のセキュリティヘッダ群を冪等に付与する。

    Args:
        response: FastAPI レスポンスオブジェクト。
        path: リクエストパス。`/static/design-preview/` 配下のみ React/Babel
            CDN を読み込めるよう CSP を緩める。
        secure_cookies: True のとき HSTS ヘッダを付与する (HTTPS 運用想定)。
        hsts_max_age: HSTS max-age 秒数。

    Returns:
        ヘッダを追加した同オブジェクト。
    """
    if path.startswith("/static/design-preview/") or path == "/design-preview":
        csp = _DESIGN_PREVIEW_CSP
    else:
        csp = "; ".join([
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data:",
            "connect-src 'self'",
            "font-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ])
    response.headers.setdefault("Content-Security-Policy", csp)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    if secure_cookies:
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={hsts_max_age}; includeSubDomains",
        )
    return response


def _validate_config(config: AppConfig) -> None:
    """session_secret と admin password_hash が設定済みか検証する。

    未設定・空文字列の場合は `ConfigError` を送出して起動を停止する。
    """
    if not config.web.session_secret:
        raise ConfigError(
            "web.session_secret is not set (env: WEB_SESSION_SECRET). "
            "Set WEB_SESSION_SECRET in the process environment or "
            "configure web.session_secret in settings.yaml.",
        )
    if not config.web.password_hash:
        raise ConfigError(
            "web.password_hash is not set (env: WEB_PASSWORD_HASH). "
            "Generate a bcrypt hash with `stock-analyze auth hash-password` "
            "and set WEB_PASSWORD_HASH in the process environment.",
        )


def create_app(config: AppConfig | None = None) -> FastAPI:
    """FastAPI アプリのファクトリ。設定検証・lifespan・middleware・ルーティングを組み立てる。

    Args:
        config: アプリ設定。`None` の場合は `load_config()` で読み込む。

    Returns:
        起動可能な FastAPI インスタンス。
    """
    if config is None:
        config = load_config()
    _validate_config(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state = await AppState.create(config)
        app.state.app_state = state
        try:
            yield
        finally:
            await state.dispose()

    app = FastAPI(title="Stock Analyze System", lifespan=lifespan)

    allowed_hosts = list(config.web.allowed_hosts or ["localhost", "127.0.0.1"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    # キャッシュ無効化用バージョン: app.js / app.css 更新後の再読込で確実に新版を取得させる
    import time as _time
    templates.env.globals["asset_version"] = str(int(_time.time()))
    app.state.templates = templates

    from stock_analyze_system.web.auth import AuthMiddleware, InMemoryRateLimiter, SessionSigner
    signer = SessionSigner(config.web.session_secret)
    app.state.session_signer = signer
    app.state.login_rate_limiter = InMemoryRateLimiter(
        max_attempts=config.web.login_rate_limit_attempts,
        window_seconds=config.web.login_rate_limit_window_seconds,
    )
    app.state.heavy_rate_limiter = InMemoryRateLimiter(
        max_attempts=config.web.heavy_rate_limit_attempts,
        window_seconds=config.web.heavy_rate_limit_window_seconds,
    )
    app.add_middleware(AuthMiddleware, signer=signer)

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        return _add_security_headers(
            response,
            path=request.url.path,
            secure_cookies=config.web.secure_cookies,
            hsts_max_age=config.web.hsts_max_age,
        )

    app.add_middleware(StateChangeOriginGuardMiddleware)
    app.add_middleware(HostHeaderGuardMiddleware)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @app.get("/design-preview")
    async def design_preview():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/static/design-preview/ui_kits/web/index.html")

    from stock_analyze_system.web.routes import analysis_jobs as analysis_jobs_routes
    from stock_analyze_system.web.routes import api as api_routes
    from stock_analyze_system.web.routes import auth as auth_routes
    from stock_analyze_system.web.routes import dashboard as dashboard_routes
    from stock_analyze_system.web.routes import jobs as job_routes
    from stock_analyze_system.web.routes import rag as rag_routes
    from stock_analyze_system.web.routes import screening as screening_routes
    from stock_analyze_system.web.routes import stocks as stocks_routes
    from stock_analyze_system.web.routes import targets as target_routes
    from stock_analyze_system.web.routes import watchlists as watchlist_routes
    app.include_router(auth_routes.router)
    app.include_router(dashboard_routes.router)
    app.include_router(stocks_routes.router)
    app.include_router(watchlist_routes.router)
    app.include_router(target_routes.router)
    app.include_router(job_routes.router)
    app.include_router(screening_routes.page_router)
    app.include_router(screening_routes.router)
    app.include_router(rag_routes.router)
    app.include_router(analysis_jobs_routes.router)
    app.include_router(api_routes.router)

    return app
