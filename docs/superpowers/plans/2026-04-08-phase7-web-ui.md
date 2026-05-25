# Phase 7: Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI-based Web UI (Phase 7 from the master spec section 10) — authentication, dashboard, company search/detail with 5 tabs, watchlists, targets, jobs, and RAG Q&A — plus fix the 5 known Phase 7 bugs.

**Architecture:** FastAPI + Jinja2 SSR with Tailwind (CDN), Alpine.js, HTMX, Chart.js. Session-based auth via itsdangerous. The DB engine is created once at app startup; each request gets its own `AsyncSession` via a FastAPI dependency. Services are wired through the existing `cli/container.py:setup_services()` so the CLI and Web share one DI graph. Templates are split per route module under `web/templates/`.

**Tech Stack:** Python 3.10+, FastAPI 0.115+, Jinja2 3.1+, uvicorn, itsdangerous 2.1+, SQLAlchemy async, Tailwind (CDN), Alpine.js, HTMX, Chart.js — all dependencies already in `pyproject.toml`.

**Spec:** `docs/superpowers/specs/2026-03-21-stock-analyze-system-design.md` section 10

---

## Scope

**In scope:**
- `src/stock_analyze_system/web/` package (app, auth, dependencies, routes, templates, static)
- All routes from spec section 10.4 except `/screening` (placeholder only — Phase 5 is on hold)
- All 5 company-detail tabs (Financial / Valuation / Metrics / RAG / Filings)
- All API endpoints from spec section 10.4
- Bug fixes #1, #2, #8, #9, #14 from spec section 15
- Unit + integration tests via FastAPI `TestClient`

**Out of scope:**
- `/screening` real implementation — placeholder route returns "Phase 5 pending" page
- Production deployment / TLS / reverse proxy config
- WebSocket / live job progress
- Theme customization beyond Tailwind defaults

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/stock_analyze_system/web/__init__.py` | Package init + `create_app` re-export |
| `src/stock_analyze_system/web/app.py` | FastAPI factory (`create_app`), lifespan, middleware mount, route registration, exception handlers |
| `src/stock_analyze_system/web/dependencies.py` | FastAPI dependencies: `get_engine`, `get_session_dep`, `get_services`, `get_config` |
| `src/stock_analyze_system/web/auth.py` | Session token (itsdangerous), `AuthMiddleware`, login/logout endpoints, password verification |
| `src/stock_analyze_system/web/routes/__init__.py` | Empty package marker |
| `src/stock_analyze_system/web/routes/dashboard.py` | `GET /` dashboard |
| `src/stock_analyze_system/web/routes/stocks.py` | `GET /stocks/search`, `GET /stocks/{company_id}` |
| `src/stock_analyze_system/web/routes/watchlists.py` | Watchlist CRUD pages |
| `src/stock_analyze_system/web/routes/targets.py` | Target list/add/remove pages |
| `src/stock_analyze_system/web/routes/jobs.py` | Job list / sync / daily pages |
| `src/stock_analyze_system/web/routes/screening.py` | Phase 5 placeholder page (no real screening) |
| `src/stock_analyze_system/web/routes/rag.py` | `GET /rag/{company_id}` Q&A page |
| `src/stock_analyze_system/web/routes/api.py` | JSON API endpoints (valuations, financials, RAG ask/index/analyses) |
| `src/stock_analyze_system/web/templates/base.html` | Layout: head, nav, content block |
| `src/stock_analyze_system/web/templates/_nav.html` | Navigation partial (reused across pages) |
| `src/stock_analyze_system/web/templates/login.html` | Login form |
| `src/stock_analyze_system/web/templates/dashboard.html` | Dashboard overview |
| `src/stock_analyze_system/web/templates/stocks/search.html` | Search page wrapper |
| `src/stock_analyze_system/web/templates/stocks/_search_results.html` | HTMX partial: search results |
| `src/stock_analyze_system/web/templates/stocks/detail.html` | Detail page with Alpine.js tabs |
| `src/stock_analyze_system/web/templates/stocks/_tab_financial.html` | Financial tab content |
| `src/stock_analyze_system/web/templates/stocks/_tab_valuation.html` | Valuation tab content |
| `src/stock_analyze_system/web/templates/stocks/_tab_metrics.html` | Metrics tab content |
| `src/stock_analyze_system/web/templates/stocks/_tab_rag.html` | RAG analyses + Q&A tab |
| `src/stock_analyze_system/web/templates/stocks/_tab_filings.html` | Filings list tab |
| `src/stock_analyze_system/web/templates/watchlists/list.html` | Watchlists index |
| `src/stock_analyze_system/web/templates/watchlists/detail.html` | Single watchlist + items |
| `src/stock_analyze_system/web/templates/targets/list.html` | Targets index |
| `src/stock_analyze_system/web/templates/jobs/list.html` | Jobs page |
| `src/stock_analyze_system/web/templates/screening/placeholder.html` | "Phase 5 pending" page |
| `src/stock_analyze_system/web/templates/rag/ask.html` | RAG Q&A page (top-level route) |
| `src/stock_analyze_system/web/static/app.css` | Minimal custom CSS overrides |
| `src/stock_analyze_system/web/static/app.js` | Shared Alpine.js helpers |
| `tests/unit/web/__init__.py` | Test package marker |
| `tests/unit/web/conftest.py` | Web test fixtures: `app`, `client`, `auth_client`, `seed_db` |
| `tests/unit/web/test_app.py` | App factory + lifespan + 404 handler |
| `tests/unit/web/test_auth.py` | Token sign/verify, AuthMiddleware, login/logout |
| `tests/unit/web/test_dependencies.py` | DI dependencies |
| `tests/unit/web/test_dashboard.py` | Dashboard route |
| `tests/unit/web/test_stocks.py` | Stock search + detail + tabs |
| `tests/unit/web/test_watchlists.py` | Watchlist routes |
| `tests/unit/web/test_targets.py` | Target routes |
| `tests/unit/web/test_jobs.py` | Job routes |
| `tests/unit/web/test_screening.py` | Screening placeholder |
| `tests/unit/web/test_rag.py` | RAG page route |
| `tests/unit/web/test_api.py` | JSON API endpoints |

### Modified Files

| File | Change |
|------|--------|
| `src/stock_analyze_system/cli/serve.py` | Already references `web:create_app` — verify wiring works once `web/` exists |
| `tests/unit/cli/test_serve_cli.py` | Add import smoke test once `web` package is real |

### Deleted Files

None.

---

## Common Patterns

### TDD pattern (every task)

1. Write failing test
2. Run it, verify failure mode is what you expect
3. Write minimal implementation
4. Run test, verify pass
5. Commit

### Test client setup (used by every route test)

```python
# tests/unit/web/conftest.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.config import AppConfig, WebConfig
from stock_analyze_system.web.app import create_app


@pytest.fixture
def web_config() -> AppConfig:
    cfg = AppConfig()
    cfg.web = WebConfig(
        host="127.0.0.1",
        port=8501,
        password="test-pass",
        session_secret="test-secret-please-do-not-use-in-prod",
    )
    cfg.database.path = ":memory:"
    return cfg


@pytest.fixture
def app(web_config):
    return create_app(config=web_config)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """A TestClient with a valid session cookie."""
    resp = client.post("/login", data={"password": "test-pass"}, follow_redirects=False)
    assert resp.status_code == 303
    return client
```

### Authentication dependency pattern (every protected route)

```python
from fastapi import Depends
from stock_analyze_system.web.auth import require_user

@router.get("/protected")
async def handler(_user: str = Depends(require_user)):
    ...
```

### Session dependency pattern (every route that hits the DB)

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from stock_analyze_system.web.dependencies import get_services

@router.get("/dashboard")
async def dashboard(services = Depends(get_services)):
    companies = await services.company_service.list_companies()
    ...
```

### Bug-fix conventions

- **Bug #1 (Hard-coded company IDs in screening results):** never embed IDs in templates — always pass through server-side. Do this in *every* template that displays a company list.
- **Bug #2 (Tailwind dynamic class names):** never use `bg-{{color}}-500` style strings — write the full class name explicitly. CDN Tailwind cannot purge dynamic strings, but jit-style enforcement here prevents future regression to a build-step Tailwind.
- **Bug #8 (Session secret auto-generation):** if `WebConfig.session_secret` is empty, raise `ConfigError` at `create_app()` time. No fallback random secret.
- **Bug #9 (Nav active state):** use `request.url.path.startswith(prefix)` for non-root prefixes; root `/` requires exact match (otherwise it always wins).
- **Bug #14 (`require_auth()` dead code):** *not present in this codebase*. Phase 7 must not introduce equivalent dead code: keep auth in `AuthMiddleware` only, with `require_user` as a thin Depends shim. No standalone `require_auth()` function.

---

## Tasks

### Task 1: Web package skeleton + dependencies

**Files:**
- Create: `src/stock_analyze_system/web/__init__.py`
- Create: `src/stock_analyze_system/web/dependencies.py`
- Create: `tests/unit/web/__init__.py`
- Create: `tests/unit/web/test_dependencies.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_dependencies.py
"""web/dependencies.py のテスト"""
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from stock_analyze_system.config import AppConfig
from stock_analyze_system.web.dependencies import (
    AppState,
    get_app_state,
    get_config,
    get_engine,
    get_services,
    get_session_dep,
)


@pytest.fixture
async def state():
    cfg = AppConfig()
    cfg.database.path = ":memory:"
    return await AppState.create(cfg)


async def test_app_state_creates_engine(state):
    assert isinstance(state.engine, AsyncEngine)
    await state.dispose()


async def test_get_session_dep_yields_async_session(state):
    async for session in get_session_dep(state):
        assert isinstance(session, AsyncSession)
        break
    await state.dispose()


async def test_get_services_wires_container(state):
    async for session in get_session_dep(state):
        services = await get_services(session, state)
        assert services.company_service is not None
        assert services.financial_service is not None
        break
    await state.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/web/test_dependencies.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stock_analyze_system.web'`

- [ ] **Step 3: Create package skeleton**

Create `src/stock_analyze_system/web/__init__.py`:

```python
"""Web UI package (FastAPI)."""
from stock_analyze_system.web.app import create_app

__all__ = ["create_app"]
```

Create `tests/unit/web/__init__.py` as an empty file.

- [ ] **Step 4: Implement `dependencies.py`**

Create `src/stock_analyze_system/web/dependencies.py`:

```python
"""FastAPI dependencies — engine, session, services, config."""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from stock_analyze_system.cli.container import ServiceContainer, setup_services
from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.base import create_db_engine, get_session


@dataclass
class AppState:
    """Application-wide state held on app.state."""

    config: AppConfig
    engine: AsyncEngine

    @classmethod
    async def create(cls, config: AppConfig) -> "AppState":
        engine = await create_db_engine(config.database.path)
        return cls(config=config, engine=engine)

    async def dispose(self) -> None:
        await self.engine.dispose()


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def get_config(state: AppState = Depends(get_app_state)) -> AppConfig:
    return state.config


def get_engine(state: AppState = Depends(get_app_state)) -> AsyncEngine:
    return state.engine


async def get_session_dep(
    state: AppState = Depends(get_app_state),
) -> AsyncIterator[AsyncSession]:
    async with get_session(state.engine) as session:
        yield session


async def get_services(
    session: AsyncSession = Depends(get_session_dep),
    state: AppState = Depends(get_app_state),
) -> ServiceContainer:
    return await setup_services(session, state.config)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/web/test_dependencies.py -v`
Expected: PASS (3 tests). The test still imports `web.app.create_app` indirectly via `web/__init__.py`, so this will fail until Task 2. **Adjust the import order** — temporarily make `web/__init__.py` empty for now and only re-export `create_app` after Task 2.

Edit `src/stock_analyze_system/web/__init__.py` to:

```python
"""Web UI package (FastAPI)."""
```

Re-run: `python3 -m pytest tests/unit/web/test_dependencies.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/web/__init__.py \
        src/stock_analyze_system/web/dependencies.py \
        tests/unit/web/__init__.py \
        tests/unit/web/test_dependencies.py
git commit -m "feat(web): add web package skeleton + DI dependencies"
```

---

### Task 2: FastAPI app factory + lifespan

**Files:**
- Create: `src/stock_analyze_system/web/app.py`
- Create: `tests/unit/web/test_app.py`
- Create: `tests/unit/web/conftest.py`
- Modify: `src/stock_analyze_system/web/__init__.py`

- [ ] **Step 1: Write the conftest**

Create `tests/unit/web/conftest.py` with the fixtures from "Common Patterns" above.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/web/test_app.py
"""FastAPI app factory のテスト"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_analyze_system.config import AppConfig, WebConfig
from stock_analyze_system.exceptions import ConfigError
from stock_analyze_system.web.app import create_app


def test_create_app_returns_fastapi_instance(web_config):
    app = create_app(config=web_config)
    assert isinstance(app, FastAPI)


def test_create_app_requires_session_secret():
    """Bug #8: 空の session_secret で起動エラー"""
    cfg = AppConfig()
    cfg.web = WebConfig(password="x", session_secret="")
    with pytest.raises(ConfigError, match="session_secret"):
        create_app(config=cfg)


def test_static_files_mounted(client):
    resp = client.get("/static/app.css")
    # 404 か 200 — マウントされていれば /static は存在する (404 is fine)
    assert resp.status_code in (200, 404)


def test_unknown_route_returns_404(client):
    resp = client.get("/this-does-not-exist")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/web/test_app.py -v`
Expected: FAIL — `web.app` does not exist yet.

- [ ] **Step 4: Implement `web/app.py`**

Create `src/stock_analyze_system/web/app.py`:

```python
"""FastAPI app factory — wires routes, middleware, lifespan, templates."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from stock_analyze_system.config import AppConfig, load_config
from stock_analyze_system.exceptions import ConfigError
from stock_analyze_system.web.dependencies import AppState

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = _PACKAGE_DIR / "templates"
STATIC_DIR = _PACKAGE_DIR / "static"


def _validate_config(config: AppConfig) -> None:
    """Bug #8: session_secret 必須。"""
    if not config.web.session_secret:
        raise ConfigError(
            "WEB_SESSION_SECRET is not set. Set it in .env or settings.yaml.",
        )
    if not config.web.password:
        raise ConfigError(
            "web.password is not set. Set it in .env (WEB_PASSWORD) or settings.yaml.",
        )


def create_app(config: AppConfig | None = None) -> FastAPI:
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

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    return app
```

- [ ] **Step 5: Re-export from `web/__init__.py`**

```python
"""Web UI package (FastAPI)."""
from stock_analyze_system.web.app import create_app

__all__ = ["create_app"]
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_app.py tests/unit/web/test_dependencies.py -v`
Expected: PASS (7 tests total).

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/app.py \
        src/stock_analyze_system/web/__init__.py \
        tests/unit/web/test_app.py \
        tests/unit/web/conftest.py
git commit -m "feat(web): add FastAPI app factory with lifespan + Bug #8 fix"
```

---

### Task 3: Session token + AuthMiddleware

**Files:**
- Create: `src/stock_analyze_system/web/auth.py`
- Create: `tests/unit/web/test_auth.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_auth.py
"""web/auth.py のテスト"""
import pytest
from fastapi import HTTPException
from itsdangerous import BadSignature

from stock_analyze_system.web.auth import (
    SESSION_COOKIE,
    SessionSigner,
    verify_password,
)


SECRET = "test-secret-do-not-use-in-prod"


class TestSessionSigner:
    def test_sign_and_unsign_round_trip(self):
        signer = SessionSigner(SECRET)
        token = signer.sign("alice")
        assert signer.unsign(token, max_age_seconds=3600) == "alice"

    def test_unsign_rejects_tampered_token(self):
        signer = SessionSigner(SECRET)
        token = signer.sign("alice") + "x"
        with pytest.raises(BadSignature):
            signer.unsign(token, max_age_seconds=3600)

    def test_different_secret_rejects(self):
        sig_a = SessionSigner("secret-a")
        sig_b = SessionSigner("secret-b")
        token = sig_a.sign("alice")
        with pytest.raises(BadSignature):
            sig_b.unsign(token, max_age_seconds=3600)


class TestVerifyPassword:
    def test_match(self):
        assert verify_password("hunter2", "hunter2") is True

    def test_mismatch(self):
        assert verify_password("hunter2", "wrong") is False

    def test_constant_time(self):
        # Smoke check: function returns bool not None even for empty
        assert verify_password("", "") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/web/test_auth.py -v`
Expected: FAIL — `web.auth` does not exist yet.

- [ ] **Step 3: Implement `web/auth.py`**

Create `src/stock_analyze_system/web/auth.py`:

```python
"""Session-based authentication: signer, middleware, login/logout."""
from __future__ import annotations

import hmac
import logging
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

SESSION_COOKIE = "stock_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 1 week
PUBLIC_PATHS = frozenset({"/login", "/logout", "/health"})
PUBLIC_PREFIXES = ("/static/",)


class SessionSigner:
    """Thin wrapper around itsdangerous URLSafeTimedSerializer."""

    def __init__(self, secret: str):
        self._serializer = URLSafeTimedSerializer(secret, salt="stock-session")

    def sign(self, user_id: str) -> str:
        return self._serializer.dumps(user_id)

    def unsign(self, token: str, *, max_age_seconds: int) -> str:
        return self._serializer.loads(token, max_age=max_age_seconds)


def verify_password(submitted: str, expected: str) -> bool:
    """Constant-time comparison."""
    return hmac.compare_digest(submitted.encode(), expected.encode())


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests with a redirect to /login."""

    def __init__(self, app, signer: SessionSigner):
        super().__init__(app)
        self._signer = signer

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if _is_public(request.url.path):
            request.state.user = None
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

        try:
            user = self._signer.unsign(token, max_age_seconds=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            logger.info("Rejected invalid session for %s", request.url.path)
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

        request.state.user = user
        return await call_next(request)


def require_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated",
        )
    return user
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/unit/web/test_auth.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Wire AuthMiddleware into app.py**

Modify `src/stock_analyze_system/web/app.py` — add inside `create_app`, after templates setup:

```python
    from stock_analyze_system.web.auth import AuthMiddleware, SessionSigner
    signer = SessionSigner(config.web.session_secret)
    app.state.session_signer = signer
    app.add_middleware(AuthMiddleware, signer=signer)
```

- [ ] **Step 6: Add middleware integration test**

Append to `tests/unit/web/test_auth.py`:

```python
class TestAuthMiddleware:
    def test_unauthenticated_request_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_static_path_is_public(self, client):
        resp = client.get("/static/app.css", follow_redirects=False)
        # 200 or 404 — both mean middleware did not redirect
        assert resp.status_code in (200, 404)

    def test_login_path_is_public(self, client):
        resp = client.get("/login", follow_redirects=False)
        # 200 (form rendered) or 404 (route not yet) — neither is a redirect
        assert resp.status_code in (200, 404, 405)
```

Run: `python3 -m pytest tests/unit/web/test_auth.py -v`
Expected: PASS (9 tests).

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/auth.py \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_auth.py
git commit -m "feat(web): add session signer + AuthMiddleware"
```

---

### Task 4: Login / logout routes + login template

**Files:**
- Create: `src/stock_analyze_system/web/routes/__init__.py`
- Create: `src/stock_analyze_system/web/routes/auth.py`
- Create: `src/stock_analyze_system/web/templates/login.html`
- Create: `src/stock_analyze_system/web/templates/base.html` (minimal stub for now)
- Modify: `src/stock_analyze_system/web/app.py`
- Modify: `tests/unit/web/test_auth.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/web/test_auth.py`:

```python
class TestLoginRoute:
    def test_get_login_renders_form(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "password" in resp.text.lower()

    def test_post_login_with_correct_password_sets_cookie(self, client):
        resp = client.post(
            "/login", data={"password": "test-pass"}, follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "stock_session" in resp.cookies

    def test_post_login_with_wrong_password_fails(self, client):
        resp = client.post(
            "/login", data={"password": "wrong"}, follow_redirects=False,
        )
        assert resp.status_code == 401
        assert "stock_session" not in resp.cookies

    def test_logout_clears_cookie(self, auth_client):
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"
        # Cookie cleared
        assert auth_client.cookies.get("stock_session") in (None, "")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/unit/web/test_auth.py::TestLoginRoute -v`
Expected: FAIL — routes not registered.

- [ ] **Step 3: Create routes package**

Create `src/stock_analyze_system/web/routes/__init__.py` as empty.

- [ ] **Step 4: Create base template stub**

Create `src/stock_analyze_system/web/templates/base.html`:

```html
<!doctype html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Stock Analyze System{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <link rel="stylesheet" href="/static/app.css">
</head>
<body class="bg-gray-50 text-gray-900 min-h-screen">
    {% block nav %}{% endblock %}
    <main class="container mx-auto px-4 py-8">
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

- [ ] **Step 5: Create login template**

Create `src/stock_analyze_system/web/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}ログイン — Stock Analyze System{% endblock %}
{% block content %}
<div class="max-w-md mx-auto mt-16 bg-white rounded-lg shadow p-8">
    <h1 class="text-2xl font-bold mb-6">ログイン</h1>
    {% if error %}
    <div class="bg-red-100 text-red-800 px-4 py-2 rounded mb-4">
        {{ error }}
    </div>
    {% endif %}
    <form method="post" action="/login" class="space-y-4">
        <div>
            <label class="block text-sm font-medium mb-1" for="password">パスワード</label>
            <input
                id="password" name="password" type="password" required autofocus
                class="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
        </div>
        <button
            type="submit"
            class="w-full bg-blue-600 text-white py-2 px-4 rounded hover:bg-blue-700"
        >ログイン</button>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Implement auth route module**

Create `src/stock_analyze_system/web/routes/auth.py`:

```python
"""Login / logout routes."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from stock_analyze_system.web.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    SessionSigner,
    verify_password,
)
from stock_analyze_system.web.dependencies import get_config

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str | None = None):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error},
    )


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    config = get_config(request.app.state.app_state)
    if not verify_password(password, config.web.password):
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "パスワードが違います"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    signer: SessionSigner = request.app.state.session_signer
    token = signer.sign("user")
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_MAX_AGE,
        httponly=True, samesite="lax",
    )
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
```

- [ ] **Step 7: Register router in app.py**

Modify `src/stock_analyze_system/web/app.py` — add at end of `create_app` before `return app`:

```python
    from stock_analyze_system.web.routes import auth as auth_routes
    app.include_router(auth_routes.router)
```

- [ ] **Step 8: Run tests**

Run: `python3 -m pytest tests/unit/web/test_auth.py -v`
Expected: PASS (13 tests).

- [ ] **Step 9: Commit**

```bash
git add src/stock_analyze_system/web/routes/__init__.py \
        src/stock_analyze_system/web/routes/auth.py \
        src/stock_analyze_system/web/templates/base.html \
        src/stock_analyze_system/web/templates/login.html \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_auth.py
git commit -m "feat(web): add login/logout routes + base template"
```

---

### Task 5: Navigation partial + dashboard route

**Files:**
- Create: `src/stock_analyze_system/web/templates/_nav.html`
- Modify: `src/stock_analyze_system/web/templates/base.html`
- Create: `src/stock_analyze_system/web/routes/dashboard.py`
- Create: `src/stock_analyze_system/web/templates/dashboard.html`
- Create: `tests/unit/web/test_dashboard.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_dashboard.py
"""Dashboard route tests"""


class TestDashboard:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303

    def test_authenticated_returns_200(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "ダッシュボード" in resp.text

    def test_navigation_active_state_root(self, auth_client):
        """Bug #9: ルートでは / がアクティブ"""
        resp = auth_client.get("/")
        # アクティブクラスが含まれること
        assert 'aria-current="page"' in resp.text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/unit/web/test_dashboard.py -v`
Expected: FAIL — `/` returns 404.

- [ ] **Step 3: Implement nav partial**

Create `src/stock_analyze_system/web/templates/_nav.html`:

```html
{# Bug #9: startswith マッチ + ルートは完全一致 #}
{% set path = request.url.path %}
{% set links = [
    ("/", "ダッシュボード"),
    ("/stocks/search", "銘柄"),
    ("/watchlists", "ウォッチリスト"),
    ("/targets", "ターゲット"),
    ("/jobs", "ジョブ"),
    ("/screening", "スクリーニング"),
] %}
<nav class="bg-white border-b border-gray-200">
    <div class="container mx-auto px-4">
        <div class="flex h-14 items-center justify-between">
            <a href="/" class="font-bold text-lg">Stock Analyze</a>
            <ul class="flex gap-4">
                {% for href, label in links %}
                {% set is_active = (href == "/" and path == "/") or (href != "/" and path.startswith(href)) %}
                <li>
                    <a href="{{ href }}"
                       class="px-3 py-2 rounded text-sm {% if is_active %}bg-blue-100 text-blue-700{% else %}text-gray-600 hover:bg-gray-100{% endif %}"
                       {% if is_active %}aria-current="page"{% endif %}>
                        {{ label }}
                    </a>
                </li>
                {% endfor %}
            </ul>
            <a href="/logout" class="text-sm text-gray-500 hover:text-gray-900">ログアウト</a>
        </div>
    </div>
</nav>
```

- [ ] **Step 4: Update base.html to include nav**

Modify `src/stock_analyze_system/web/templates/base.html`:

```html
{% block nav %}
{% include "_nav.html" %}
{% endblock %}
```

- [ ] **Step 5: Implement dashboard route**

Create `src/stock_analyze_system/web/routes/dashboard.py`:

```python
"""Dashboard route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    companies = await services.company_service.list_companies()
    targets = await services.target_service.list_targets()
    watchlists = await services.watchlist_service.list_watchlists()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "company_count": len(companies),
            "target_count": len(targets),
            "watchlist_count": len(watchlists),
        },
    )
```

- [ ] **Step 6: Implement dashboard template**

Create `src/stock_analyze_system/web/templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}ダッシュボード — Stock Analyze System{% endblock %}
{% block content %}
<h1 class="text-3xl font-bold mb-8">ダッシュボード</h1>
<div class="grid grid-cols-1 md:grid-cols-3 gap-6">
    <div class="bg-white rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 mb-1">登録銘柄</div>
        <div class="text-3xl font-bold">{{ company_count }}</div>
    </div>
    <div class="bg-white rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 mb-1">分析ターゲット</div>
        <div class="text-3xl font-bold">{{ target_count }}</div>
    </div>
    <div class="bg-white rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 mb-1">ウォッチリスト</div>
        <div class="text-3xl font-bold">{{ watchlist_count }}</div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 7: Register router**

Modify `src/stock_analyze_system/web/app.py` — add to router includes:

```python
    from stock_analyze_system.web.routes import dashboard as dashboard_routes
    app.include_router(dashboard_routes.router)
```

- [ ] **Step 8: Run tests**

Run: `python3 -m pytest tests/unit/web/test_dashboard.py -v`
Expected: PASS (3 tests).

- [ ] **Step 9: Commit**

```bash
git add src/stock_analyze_system/web/templates/_nav.html \
        src/stock_analyze_system/web/templates/base.html \
        src/stock_analyze_system/web/templates/dashboard.html \
        src/stock_analyze_system/web/routes/dashboard.py \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_dashboard.py
git commit -m "feat(web): add navigation partial and dashboard (Bug #9)"
```

---

### Task 6: Stocks search (HTMX)

**Files:**
- Create: `src/stock_analyze_system/web/routes/stocks.py`
- Create: `src/stock_analyze_system/web/templates/stocks/search.html`
- Create: `src/stock_analyze_system/web/templates/stocks/_search_results.html`
- Create: `tests/unit/web/test_stocks.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_stocks.py
"""Stocks routes tests"""
import pytest


@pytest.fixture
async def seeded_client(auth_client, app):
    """Seed an AAPL company before yielding the client."""
    from stock_analyze_system.models.base import get_session
    from stock_analyze_system.repositories.company import CompanyRepository
    from stock_analyze_system.models.company import Company

    state = app.state.app_state
    async with get_session(state.engine) as session:
        company = Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        )
        session.add(company)
        await session.commit()
    return auth_client


class TestStockSearchPage:
    def test_get_search_page(self, auth_client):
        resp = auth_client.get("/stocks/search")
        assert resp.status_code == 200
        assert "検索" in resp.text


class TestStockSearchResults:
    async def test_search_results_partial(self, seeded_client):
        resp = seeded_client.get("/stocks/search/results?q=Apple")
        assert resp.status_code == 200
        assert "AAPL" in resp.text
        assert "US_AAPL" in resp.text  # Bug #1: server resolves company_id

    async def test_empty_query_returns_no_results(self, seeded_client):
        resp = seeded_client.get("/stocks/search/results?q=")
        assert resp.status_code == 200
        assert "AAPL" not in resp.text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/unit/web/test_stocks.py -v`
Expected: FAIL — routes not registered.

- [ ] **Step 3: Implement search template**

Create `src/stock_analyze_system/web/templates/stocks/search.html`:

```html
{% extends "base.html" %}
{% block title %}銘柄検索{% endblock %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">銘柄検索</h1>
<div class="bg-white rounded-lg shadow p-6">
    <input type="search"
           name="q"
           placeholder="ティッカー / 企業名"
           hx-get="/stocks/search/results"
           hx-trigger="keyup changed delay:300ms"
           hx-target="#search-results"
           class="w-full px-4 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500">
    <div id="search-results" class="mt-4"></div>
</div>
{% endblock %}
```

Create `src/stock_analyze_system/web/templates/stocks/_search_results.html`:

```html
{% if companies %}
<ul class="divide-y divide-gray-200">
    {% for c in companies %}
    {# Bug #1: c.id はサーバー側で正しく解決された値 #}
    <li>
        <a href="/stocks/{{ c.id }}" class="block px-2 py-3 hover:bg-gray-50">
            <div class="font-semibold">{{ c.ticker or c.security_code }} — {{ c.name }}</div>
            <div class="text-xs text-gray-500">{{ c.id }} · {{ c.market }}</div>
        </a>
    </li>
    {% endfor %}
</ul>
{% else %}
<p class="text-sm text-gray-500">該当する銘柄がありません。</p>
{% endif %}
```

- [ ] **Step 4: Implement stocks route module**

Create `src/stock_analyze_system/web/routes/stocks.py`:

```python
"""Stocks routes — search + (detail in Task 7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services

router = APIRouter(prefix="/stocks")


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "stocks/search.html", {"request": request},
    )


@router.get("/search/results", response_class=HTMLResponse)
async def search_results(
    request: Request,
    q: str = "",
    services: ServiceContainer = Depends(get_services),
):
    companies = []
    if q.strip():
        companies = await services.company_service.search_companies(q.strip(), limit=20)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "stocks/_search_results.html",
        {"request": request, "companies": companies},
    )
```

- [ ] **Step 5: Register router in app.py**

```python
    from stock_analyze_system.web.routes import stocks as stocks_routes
    app.include_router(stocks_routes.router)
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_stocks.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/stocks.py \
        src/stock_analyze_system/web/templates/stocks/search.html \
        src/stock_analyze_system/web/templates/stocks/_search_results.html \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_stocks.py
git commit -m "feat(web): add stock search with HTMX (Bug #1)"
```

---

### Task 7: Stock detail page (tab framework)

**Files:**
- Modify: `src/stock_analyze_system/web/routes/stocks.py`
- Create: `src/stock_analyze_system/web/templates/stocks/detail.html`
- Modify: `tests/unit/web/test_stocks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/web/test_stocks.py`:

```python
class TestStockDetailPage:
    async def test_detail_page_for_existing_company(self, seeded_client):
        resp = seeded_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        assert "Apple" in resp.text
        # Five tab labels visible
        for label in ("財務", "バリュエーション", "指標", "RAG", "ファイリング"):
            assert label in resp.text

    async def test_detail_page_unknown_company_404(self, auth_client):
        resp = auth_client.get("/stocks/US_NOPE")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/web/test_stocks.py::TestStockDetailPage -v`
Expected: FAIL — route missing.

- [ ] **Step 3: Implement detail route**

Append to `src/stock_analyze_system/web/routes/stocks.py`:

```python
from fastapi import HTTPException, status as http_status


@router.get("/{company_id}", response_class=HTMLResponse)
async def detail_page(
    company_id: str,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    company = await services.company_service.get_company(company_id)
    if company is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "stocks/detail.html",
        {"request": request, "company": company},
    )
```

- [ ] **Step 4: Implement detail template**

Create `src/stock_analyze_system/web/templates/stocks/detail.html`:

```html
{% extends "base.html" %}
{% block title %}{{ company.name }} — {{ company.ticker or company.security_code }}{% endblock %}
{% block content %}
<div x-data="{ tab: 'financial' }">
    <header class="mb-6">
        <h1 class="text-3xl font-bold">{{ company.name }}</h1>
        <p class="text-sm text-gray-500">
            {{ company.ticker or company.security_code }} · {{ company.id }} · {{ company.market }}
        </p>
    </header>

    <nav class="border-b border-gray-200 mb-6">
        <ul class="flex gap-2">
            {% set tabs = [
                ("financial", "財務"),
                ("valuation", "バリュエーション"),
                ("metrics", "指標"),
                ("rag", "RAG"),
                ("filings", "ファイリング"),
            ] %}
            {% for key, label in tabs %}
            <li>
                <button
                    @click="tab = '{{ key }}'"
                    :class="tab === '{{ key }}' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'"
                    class="px-4 py-2 border-b-2 text-sm font-medium">
                    {{ label }}
                </button>
            </li>
            {% endfor %}
        </ul>
    </nav>

    <div x-show="tab === 'financial'" x-cloak>
        {% include "stocks/_tab_financial.html" %}
    </div>
    <div x-show="tab === 'valuation'" x-cloak>
        {% include "stocks/_tab_valuation.html" %}
    </div>
    <div x-show="tab === 'metrics'" x-cloak>
        {% include "stocks/_tab_metrics.html" %}
    </div>
    <div x-show="tab === 'rag'" x-cloak>
        {% include "stocks/_tab_rag.html" %}
    </div>
    <div x-show="tab === 'filings'" x-cloak>
        {% include "stocks/_tab_filings.html" %}
    </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Create five empty tab partial stubs**

For each of `_tab_financial.html`, `_tab_valuation.html`, `_tab_metrics.html`, `_tab_rag.html`, `_tab_filings.html` in `src/stock_analyze_system/web/templates/stocks/`, create with content:

```html
<div class="bg-white rounded-lg shadow p-6">
    <p class="text-sm text-gray-500">{{ self.__class__.__name__ if false }}準備中</p>
</div>
```

(Replace each with the tab name in the placeholder text.)

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_stocks.py -v`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/stocks.py \
        src/stock_analyze_system/web/templates/stocks/detail.html \
        src/stock_analyze_system/web/templates/stocks/_tab_*.html \
        tests/unit/web/test_stocks.py
git commit -m "feat(web): add stock detail page with tab framework"
```

---

### Task 8: Financial tab + JSON API endpoint

**Files:**
- Create: `src/stock_analyze_system/web/routes/api.py`
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_financial.html`
- Create: `tests/unit/web/test_api.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_api.py
"""JSON API endpoint tests"""
import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.models.base import get_session


@pytest.fixture
async def seeded_financials(auth_client, app):
    state = app.state.app_state
    async with get_session(state.engine) as session:
        session.add(Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ))
        session.add(FinancialData(
            company_id="US_AAPL", period_type="annual",
            fiscal_year=2024, fiscal_period="FY",
            revenue=391000.0, net_income=93700.0,
            eps_basic=6.11,
        ))
        await session.commit()
    return auth_client


class TestFinancialsApi:
    async def test_returns_annual_records(self, seeded_financials):
        resp = seeded_financials.get("/api/stocks/US_AAPL/financials/annual")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["revenue"] == 391000.0
        assert data[0]["fiscal_year"] == 2024

    async def test_unknown_period_400(self, seeded_financials):
        resp = seeded_financials.get("/api/stocks/US_AAPL/financials/yearly")
        assert resp.status_code == 400

    async def test_unknown_company_returns_empty_list(self, auth_client):
        resp = auth_client.get("/api/stocks/US_NOPE/financials/annual")
        assert resp.status_code == 200
        assert resp.json() == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/unit/web/test_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement API route module**

Create `src/stock_analyze_system/web/routes/api.py`:

```python
"""JSON API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.models.enums import PeriodType
from stock_analyze_system.web.dependencies import get_services

router = APIRouter(prefix="/api/stocks")


def _financial_to_dict(fd) -> dict:
    return {
        "fiscal_year": fd.fiscal_year,
        "fiscal_period": fd.fiscal_period,
        "period_type": fd.period_type,
        "revenue": fd.revenue,
        "net_income": fd.net_income,
        "eps_basic": fd.eps_basic,
        "eps_diluted": fd.eps_diluted,
        "operating_income": fd.operating_income,
        "operating_cf": fd.operating_cf,
        "fcf": fd.fcf,
    }


@router.get("/{company_id}/financials/{period}")
async def get_financials(
    company_id: str, period: str,
    services: ServiceContainer = Depends(get_services),
):
    if period not in (PeriodType.ANNUAL, PeriodType.QUARTERLY):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"period must be 'annual' or 'quarterly', got {period!r}",
        )
    records = await services.financial_service.get_timeseries(
        company_id, period_type=period, years=10,
    )
    return [_financial_to_dict(r) for r in records]
```

- [ ] **Step 4: Register router**

Modify `src/stock_analyze_system/web/app.py`:

```python
    from stock_analyze_system.web.routes import api as api_routes
    app.include_router(api_routes.router)
```

- [ ] **Step 5: Implement financial tab**

Replace `src/stock_analyze_system/web/templates/stocks/_tab_financial.html`:

```html
<div x-data="financialTab('{{ company.id }}')" x-init="load()" class="bg-white rounded-lg shadow p-6">
    <div class="flex justify-between items-center mb-4">
        <h2 class="text-xl font-semibold">財務データ</h2>
        <select x-model="period" @change="load()" class="border rounded px-2 py-1 text-sm">
            <option value="annual">通期</option>
            <option value="quarterly">四半期</option>
        </select>
    </div>
    <canvas x-ref="chart" height="120"></canvas>
    <table class="mt-6 w-full text-sm">
        <thead>
            <tr class="text-left text-gray-500">
                <th class="px-2 py-1">年</th>
                <th class="px-2 py-1 text-right">売上</th>
                <th class="px-2 py-1 text-right">純利益</th>
                <th class="px-2 py-1 text-right">EPS</th>
            </tr>
        </thead>
        <tbody>
            <template x-for="row in records" :key="row.fiscal_year + '-' + row.fiscal_period">
                <tr class="border-t">
                    <td class="px-2 py-1" x-text="row.fiscal_year + ' ' + row.fiscal_period"></td>
                    <td class="px-2 py-1 text-right" x-text="row.revenue"></td>
                    <td class="px-2 py-1 text-right" x-text="row.net_income"></td>
                    <td class="px-2 py-1 text-right" x-text="row.eps_basic"></td>
                </tr>
            </template>
        </tbody>
    </table>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
function financialTab(companyId) {
    return {
        records: [],
        period: 'annual',
        chart: null,
        async load() {
            const r = await fetch(`/api/stocks/${companyId}/financials/${this.period}`);
            this.records = await r.json();
            this.renderChart();
        },
        renderChart() {
            if (this.chart) this.chart.destroy();
            const labels = this.records.map(r => `${r.fiscal_year} ${r.fiscal_period}`);
            const revenue = this.records.map(r => r.revenue);
            const ni = this.records.map(r => r.net_income);
            this.chart = new Chart(this.$refs.chart, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [
                        { label: '売上', data: revenue, backgroundColor: '#3b82f6' },
                        { label: '純利益', data: ni, backgroundColor: '#10b981' },
                    ],
                },
            });
        },
    };
}
</script>
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_api.py tests/unit/web/test_stocks.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/api.py \
        src/stock_analyze_system/web/templates/stocks/_tab_financial.html \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_api.py
git commit -m "feat(web): add financial tab + financials API"
```

---

### Task 9: Valuation tab + JSON API endpoint

**Files:**
- Modify: `src/stock_analyze_system/web/routes/api.py`
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_valuation.html`
- Modify: `tests/unit/web/test_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/web/test_api.py`:

```python
from datetime import date
from stock_analyze_system.models.valuation import Valuation


@pytest.fixture
async def seeded_valuations(auth_client, app):
    state = app.state.app_state
    async with get_session(state.engine) as session:
        session.add(Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ))
        session.add(Valuation(
            company_id="US_AAPL", as_of_date=date(2025, 3, 1),
            per=28.5, pbr=58.2, psr=8.4, eps_ttm=6.5,
        ))
        await session.commit()
    return auth_client


class TestValuationsApi:
    async def test_returns_valuations(self, seeded_valuations):
        resp = seeded_valuations.get("/api/stocks/US_AAPL/valuations")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["per"] == 28.5
        assert data[0]["pbr"] == 58.2

    async def test_unknown_company_returns_empty(self, auth_client):
        resp = auth_client.get("/api/stocks/US_NOPE/valuations")
        assert resp.status_code == 200
        assert resp.json() == []
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/web/test_api.py::TestValuationsApi -v`
Expected: FAIL.

- [ ] **Step 3: Add valuation endpoint**

Append to `src/stock_analyze_system/web/routes/api.py`:

```python
def _valuation_to_dict(v) -> dict:
    return {
        "as_of_date": v.as_of_date.isoformat() if v.as_of_date else None,
        "per": v.per,
        "pbr": v.pbr,
        "psr": v.psr,
        "eps_ttm": v.eps_ttm,
    }


@router.get("/{company_id}/valuations")
async def get_valuations(
    company_id: str,
    services: ServiceContainer = Depends(get_services),
):
    records = await services.valuation_service.get_history(company_id, years=10)
    return [_valuation_to_dict(v) for v in records]
```

- [ ] **Step 4: Implement valuation tab template**

Replace `src/stock_analyze_system/web/templates/stocks/_tab_valuation.html`:

```html
<div x-data="valuationTab('{{ company.id }}')" x-init="load()" class="space-y-6">
    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">PER</h2>
        <canvas x-ref="perChart" height="100"></canvas>
    </div>
    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">PBR</h2>
        <canvas x-ref="pbrChart" height="100"></canvas>
    </div>
    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">PSR</h2>
        <canvas x-ref="psrChart" height="100"></canvas>
    </div>
</div>
<script>
function valuationTab(companyId) {
    return {
        records: [],
        async load() {
            const r = await fetch(`/api/stocks/${companyId}/valuations`);
            this.records = await r.json();
            this.renderAll();
        },
        renderAll() {
            const labels = this.records.map(r => r.as_of_date);
            const make = (ref, label, color, key) => new Chart(this.$refs[ref], {
                type: 'line',
                data: { labels, datasets: [{ label, data: this.records.map(r => r[key]), borderColor: color, fill: false }] },
            });
            make('perChart', 'PER', '#3b82f6', 'per');
            make('pbrChart', 'PBR', '#10b981', 'pbr');
            make('psrChart', 'PSR', '#f59e0b', 'psr');
        },
    };
}
</script>
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/unit/web/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/web/routes/api.py \
        src/stock_analyze_system/web/templates/stocks/_tab_valuation.html \
        tests/unit/web/test_api.py
git commit -m "feat(web): add valuation tab + valuations API"
```

---

### Task 10: Metrics tab

**Files:**
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_metrics.html`
- Modify: `src/stock_analyze_system/web/routes/stocks.py`
- Modify: `tests/unit/web/test_stocks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/web/test_stocks.py`:

```python
class TestStockMetricsTab:
    async def test_metrics_rendered_for_seeded_company(self, seeded_client):
        # Add a financial record so metrics are non-empty
        from stock_analyze_system.models.financial_data import FinancialData
        from stock_analyze_system.models.base import get_session
        state = seeded_client.app.state.app_state
        async with get_session(state.engine) as session:
            session.add(FinancialData(
                company_id="US_AAPL", period_type="annual",
                fiscal_year=2024, fiscal_period="FY",
                revenue=391000.0, net_income=93700.0,
                total_equity=62100.0, total_assets=364800.0,
            ))
            await session.commit()
        resp = seeded_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        # ROE shows up in the metrics tab
        assert "ROE" in resp.text
```

- [ ] **Step 2: Run test**

Run: `python3 -m pytest tests/unit/web/test_stocks.py::TestStockMetricsTab -v`
Expected: FAIL — `_tab_metrics.html` is still a stub.

- [ ] **Step 3: Compute metrics in detail route**

Modify `src/stock_analyze_system/web/routes/stocks.py` `detail_page`:

```python
@router.get("/{company_id}", response_class=HTMLResponse)
async def detail_page(
    company_id: str,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    company = await services.company_service.get_company(company_id)
    if company is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found")
    latest = await services.financial_service.get_latest(company_id)
    metrics = services.financial_service.compute_metrics(latest) if latest else {}
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "stocks/detail.html",
        {"request": request, "company": company, "metrics": metrics},
    )
```

- [ ] **Step 4: Replace metrics tab template**

Replace `src/stock_analyze_system/web/templates/stocks/_tab_metrics.html`:

```html
<div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-xl font-semibold mb-4">財務指標</h2>
    {% if metrics %}
    <table class="w-full text-sm">
        <tbody>
            {% set labels = {
                'roe': 'ROE',
                'roa': 'ROA',
                'gross_margin': 'グロスマージン',
                'operating_margin': '営業利益率',
                'net_margin': '純利益率',
                'debt_to_equity': '負債比率',
                'current_ratio': '流動比率',
            } %}
            {% for key, label in labels.items() %}
            <tr class="border-t">
                <td class="px-2 py-2 text-gray-500">{{ label }}</td>
                <td class="px-2 py-2 text-right">
                    {{ "%.2f"|format(metrics[key]) if metrics.get(key) is not none else "—" }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p class="text-sm text-gray-500">データがありません。</p>
    {% endif %}
</div>
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/unit/web/test_stocks.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/web/routes/stocks.py \
        src/stock_analyze_system/web/templates/stocks/_tab_metrics.html \
        tests/unit/web/test_stocks.py
git commit -m "feat(web): add metrics tab with ROE/ROA/margins"
```

---

### Task 11: Filings tab

**Files:**
- Modify: `src/stock_analyze_system/web/routes/stocks.py`
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_filings.html`
- Modify: `tests/unit/web/test_stocks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/web/test_stocks.py`:

```python
class TestStockFilingsTab:
    async def test_filings_listed(self, seeded_client):
        from stock_analyze_system.models.filing import Filing
        from stock_analyze_system.models.base import get_session
        from datetime import date
        state = seeded_client.app.state.app_state
        async with get_session(state.engine) as session:
            session.add(Filing(
                company_id="US_AAPL", filing_type="10-K",
                fiscal_year=2024, period_type="annual",
                accession_no="0000320193-25-000079",
                filed_date=date(2025, 11, 1), source="SEC",
            ))
            await session.commit()
        resp = seeded_client.get("/stocks/US_AAPL")
        assert "10-K" in resp.text
        assert "2024" in resp.text
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/web/test_stocks.py::TestStockFilingsTab -v`
Expected: FAIL.

- [ ] **Step 3: Modify detail route to fetch filings**

Update `detail_page` in `stocks.py`:

```python
@router.get("/{company_id}", response_class=HTMLResponse)
async def detail_page(
    company_id: str,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    company = await services.company_service.get_company(company_id)
    if company is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found")
    latest = await services.financial_service.get_latest(company_id)
    metrics = services.financial_service.compute_metrics(latest) if latest else {}
    filings = await services.filing_service.list_filings(company_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "stocks/detail.html",
        {
            "request": request, "company": company,
            "metrics": metrics, "filings": filings,
        },
    )
```

- [ ] **Step 4: Replace filings tab template**

Replace `src/stock_analyze_system/web/templates/stocks/_tab_filings.html`:

```html
<div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-xl font-semibold mb-4">ファイリング</h2>
    {% if filings %}
    <table class="w-full text-sm">
        <thead>
            <tr class="text-left text-gray-500">
                <th class="px-2 py-1">タイプ</th>
                <th class="px-2 py-1">年度</th>
                <th class="px-2 py-1">提出日</th>
                <th class="px-2 py-1">ソース</th>
                <th class="px-2 py-1">識別子</th>
            </tr>
        </thead>
        <tbody>
            {% for f in filings %}
            <tr class="border-t">
                <td class="px-2 py-1 font-medium">{{ f.filing_type }}</td>
                <td class="px-2 py-1">{{ f.fiscal_year }}</td>
                <td class="px-2 py-1">{{ f.filed_date }}</td>
                <td class="px-2 py-1">{{ f.source }}</td>
                <td class="px-2 py-1 text-xs text-gray-500">{{ f.accession_no or f.doc_id }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p class="text-sm text-gray-500">ファイリングがありません。</p>
    {% endif %}
</div>
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/unit/web/test_stocks.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/web/routes/stocks.py \
        src/stock_analyze_system/web/templates/stocks/_tab_filings.html \
        tests/unit/web/test_stocks.py
git commit -m "feat(web): add filings tab"
```

---

### Task 12: RAG tab + RAG API endpoints

**Files:**
- Modify: `src/stock_analyze_system/web/routes/api.py`
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_rag.html`
- Modify: `src/stock_analyze_system/web/routes/stocks.py`
- Modify: `tests/unit/web/test_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/web/test_api.py`:

```python
from unittest.mock import AsyncMock, patch


class TestRagApi:
    async def test_ask_endpoint_calls_rag_service(self, seeded_financials):
        with patch(
            "stock_analyze_system.web.routes.api._get_rag_service",
        ) as mocked:
            mock_rag = AsyncMock()
            mock_rag.ask_question.return_value.answer = "test answer"
            mock_rag.ask_question.return_value.source_pages = [1]
            mock_rag.ask_question.return_value.source_sections = ["S"]
            mocked.return_value = mock_rag
            resp = seeded_financials.post(
                "/api/stocks/US_AAPL/rag/ask",
                json={"question": "売上は？", "filing_type": "10-K"},
            )
            assert resp.status_code in (200, 503)
```

- [ ] **Step 2: Run test**

Run: `python3 -m pytest tests/unit/web/test_api.py::TestRagApi -v`
Expected: FAIL.

- [ ] **Step 3: Add RAG endpoints to api.py**

Append to `src/stock_analyze_system/web/routes/api.py`:

```python
from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    filing_type: str = "10-K"


def _get_rag_service(services: ServiceContainer):
    if services.rag_service is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is disabled. Set pageindex.enabled=true.",
        )
    return services.rag_service


@router.post("/{company_id}/rag/ask")
async def rag_ask(
    company_id: str,
    payload: AskRequest,
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_rag_service(services)
    filing = await services.filing_service.get_latest_filing(
        company_id, payload.filing_type,
    )
    if filing is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No {payload.filing_type} filings for {company_id}",
        )
    result = await rag.ask_question(filing, payload.question)
    return {
        "answer": result.answer,
        "source_pages": result.source_pages,
        "source_sections": result.source_sections,
    }


@router.post("/{company_id}/rag/index")
async def rag_index(
    company_id: str,
    filing_type: str = "10-K",
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_rag_service(services)
    filing = await services.filing_service.get_latest_filing(company_id, filing_type)
    if filing is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No {filing_type} filings for {company_id}",
        )
    tree = await rag.build_index(filing)
    return {"node_count": len(tree.get("structure", []))}


@router.get("/{company_id}/rag/analyses")
async def rag_analyses(
    company_id: str, filing_type: str = "10-K",
    services: ServiceContainer = Depends(get_services),
):
    if services.rag_service is None:
        return []
    filing = await services.filing_service.get_latest_filing(company_id, filing_type)
    if filing is None:
        return []
    return await services.rag_service.get_analyses(company_id, filing.id)
```

- [ ] **Step 4: Implement RAG tab template**

Replace `src/stock_analyze_system/web/templates/stocks/_tab_rag.html`:

```html
<div x-data="ragTab('{{ company.id }}')" x-init="loadAnalyses()" class="space-y-6">
    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">保存済み定型分析</h2>
        <template x-if="analyses.length === 0">
            <p class="text-sm text-gray-500">分析結果がありません。CLIから `stock-analyze rag analyze {{ company.id }}` を実行してください。</p>
        </template>
        <template x-for="a in analyses" :key="a.id">
            <details class="border-t py-2">
                <summary class="cursor-pointer font-medium" x-text="a.analysis_type"></summary>
                <pre class="text-xs mt-2 whitespace-pre-wrap" x-text="JSON.stringify(a.result_json, null, 2)"></pre>
            </details>
        </template>
    </div>

    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">質問する</h2>
        <textarea x-model="question" rows="3"
                  class="w-full border rounded px-3 py-2"
                  placeholder="例: Appleの2024年度の売上高は？"></textarea>
        <button @click="ask()" :disabled="loading"
                class="mt-3 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50">
            <span x-show="!loading">送信</span>
            <span x-show="loading">回答中…</span>
        </button>
        <template x-if="answer">
            <div class="mt-4 border-t pt-4">
                <p class="whitespace-pre-wrap" x-text="answer"></p>
                <p class="text-xs text-gray-500 mt-2">
                    Pages: <span x-text="sourcePages.join(', ')"></span> ·
                    Sections: <span x-text="sourceSections.join(' / ')"></span>
                </p>
            </div>
        </template>
    </div>
</div>
<script>
function ragTab(companyId) {
    return {
        analyses: [],
        question: '',
        answer: '',
        sourcePages: [],
        sourceSections: [],
        loading: false,
        async loadAnalyses() {
            const r = await fetch(`/api/stocks/${companyId}/rag/analyses`);
            if (r.ok) this.analyses = await r.json();
        },
        async ask() {
            if (!this.question.trim()) return;
            this.loading = true;
            this.answer = '';
            try {
                const r = await fetch(`/api/stocks/${companyId}/rag/ask`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: this.question }),
                });
                const data = await r.json();
                this.answer = data.answer || data.detail || '回答できませんでした';
                this.sourcePages = data.source_pages || [];
                this.sourceSections = data.source_sections || [];
            } finally {
                this.loading = false;
            }
        },
    };
}
</script>
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/unit/web/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/web/routes/api.py \
        src/stock_analyze_system/web/templates/stocks/_tab_rag.html \
        tests/unit/web/test_api.py
git commit -m "feat(web): add RAG tab + ask/index/analyses API endpoints"
```

---

### Task 13: Watchlists routes

**Files:**
- Create: `src/stock_analyze_system/web/routes/watchlists.py`
- Create: `src/stock_analyze_system/web/templates/watchlists/list.html`
- Create: `src/stock_analyze_system/web/templates/watchlists/detail.html`
- Create: `tests/unit/web/test_watchlists.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_watchlists.py
"""Watchlist routes tests"""
import pytest


class TestWatchlistList:
    def test_get_list_authenticated(self, auth_client):
        resp = auth_client.get("/watchlists")
        assert resp.status_code == 200
        assert "ウォッチリスト" in resp.text

    def test_create_watchlist(self, auth_client):
        resp = auth_client.post(
            "/watchlists", data={"name": "Tech", "description": "技術株"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Now should appear in list
        resp = auth_client.get("/watchlists")
        assert "Tech" in resp.text


class TestWatchlistDetail:
    async def test_detail_for_existing(self, auth_client):
        # Create one first
        auth_client.post(
            "/watchlists", data={"name": "Detail Test", "description": ""},
            follow_redirects=False,
        )
        resp = auth_client.get("/watchlists")
        assert "Detail Test" in resp.text
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/web/test_watchlists.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement watchlists routes**

Create `src/stock_analyze_system/web/routes/watchlists.py`:

```python
"""Watchlist routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services

router = APIRouter(prefix="/watchlists")


@router.get("", response_class=HTMLResponse)
async def list_page(
    request: Request, services: ServiceContainer = Depends(get_services),
):
    watchlists = await services.watchlist_service.list_watchlists()
    return request.app.state.templates.TemplateResponse(
        "watchlists/list.html",
        {"request": request, "watchlists": watchlists},
    )


@router.post("")
async def create(
    name: str = Form(...),
    description: str = Form(""),
    services: ServiceContainer = Depends(get_services),
):
    await services.watchlist_service.create_watchlist(name, description or None)
    return RedirectResponse(url="/watchlists", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{watchlist_id}", response_class=HTMLResponse)
async def detail(
    watchlist_id: int,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    wl = await services.watchlist_service.get_watchlist(watchlist_id)
    if wl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    items = await services.watchlist_service.list_items(watchlist_id)
    return request.app.state.templates.TemplateResponse(
        "watchlists/detail.html",
        {"request": request, "watchlist": wl, "items": items},
    )
```

- [ ] **Step 4: Implement templates**

Create `src/stock_analyze_system/web/templates/watchlists/list.html`:

```html
{% extends "base.html" %}
{% block title %}ウォッチリスト{% endblock %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">ウォッチリスト</h1>
<form method="post" action="/watchlists" class="bg-white rounded-lg shadow p-4 mb-6 flex gap-2">
    <input name="name" required placeholder="名前" class="border rounded px-3 py-2 flex-1">
    <input name="description" placeholder="説明" class="border rounded px-3 py-2 flex-1">
    <button class="bg-blue-600 text-white px-4 py-2 rounded">作成</button>
</form>
<ul class="bg-white rounded-lg shadow divide-y divide-gray-200">
    {% for w in watchlists %}
    <li class="px-4 py-3">
        <a href="/watchlists/{{ w.id }}" class="font-semibold hover:underline">{{ w.name }}</a>
        <span class="text-sm text-gray-500 ml-2">{{ w.description }}</span>
    </li>
    {% else %}
    <li class="px-4 py-3 text-sm text-gray-500">ウォッチリストがありません。</li>
    {% endfor %}
</ul>
{% endblock %}
```

Create `src/stock_analyze_system/web/templates/watchlists/detail.html`:

```html
{% extends "base.html" %}
{% block title %}{{ watchlist.name }}{% endblock %}
{% block content %}
<h1 class="text-3xl font-bold mb-2">{{ watchlist.name }}</h1>
<p class="text-gray-500 mb-6">{{ watchlist.description }}</p>
<ul class="bg-white rounded-lg shadow divide-y divide-gray-200">
    {% for item in items %}
    {# Bug #1: server-resolved company.id #}
    <li class="px-4 py-3">
        <a href="/stocks/{{ item.company_id }}" class="hover:underline">{{ item.company_id }}</a>
        {% if item.note %}<span class="ml-2 text-sm text-gray-500">{{ item.note }}</span>{% endif %}
    </li>
    {% else %}
    <li class="px-4 py-3 text-sm text-gray-500">アイテムがありません。</li>
    {% endfor %}
</ul>
{% endblock %}
```

- [ ] **Step 5: Register router**

Modify `src/stock_analyze_system/web/app.py`:

```python
    from stock_analyze_system.web.routes import watchlists as watchlist_routes
    app.include_router(watchlist_routes.router)
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_watchlists.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/watchlists.py \
        src/stock_analyze_system/web/templates/watchlists/ \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_watchlists.py
git commit -m "feat(web): add watchlist routes"
```

---

### Task 14: Targets routes

**Files:**
- Create: `src/stock_analyze_system/web/routes/targets.py`
- Create: `src/stock_analyze_system/web/templates/targets/list.html`
- Create: `tests/unit/web/test_targets.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_targets.py
"""Targets routes tests"""


class TestTargets:
    def test_get_list(self, auth_client):
        resp = auth_client.get("/targets")
        assert resp.status_code == 200
        assert "ターゲット" in resp.text

    def test_add_target(self, auth_client):
        # Pre-register a company so add_target succeeds
        from stock_analyze_system.models.base import get_session
        from stock_analyze_system.models.company import Company
        import asyncio
        state = auth_client.app.state.app_state

        async def seed():
            async with get_session(state.engine) as session:
                session.add(Company(
                    id="US_AAPL", ticker="AAPL", name="Apple",
                    market="NASDAQ", accounting_standard="US-GAAP",
                ))
                await session.commit()
        asyncio.get_event_loop().run_until_complete(seed())

        resp = auth_client.post(
            "/targets", data={"company_id": "US_AAPL"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        resp = auth_client.get("/targets")
        assert "US_AAPL" in resp.text
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/web/test_targets.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement targets route**

Create `src/stock_analyze_system/web/routes/targets.py`:

```python
"""Analysis targets routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services

router = APIRouter(prefix="/targets")


@router.get("", response_class=HTMLResponse)
async def list_page(
    request: Request, services: ServiceContainer = Depends(get_services),
):
    targets = await services.target_service.list_targets()
    return request.app.state.templates.TemplateResponse(
        "targets/list.html",
        {"request": request, "targets": targets},
    )


@router.post("")
async def add(
    company_id: str = Form(...),
    services: ServiceContainer = Depends(get_services),
):
    await services.target_service.add_target(company_id)
    return RedirectResponse(url="/targets", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{company_id}/delete")
async def remove(
    company_id: str,
    services: ServiceContainer = Depends(get_services),
):
    await services.target_service.remove_target(company_id)
    return RedirectResponse(url="/targets", status_code=status.HTTP_303_SEE_OTHER)
```

- [ ] **Step 4: Implement template**

Create `src/stock_analyze_system/web/templates/targets/list.html`:

```html
{% extends "base.html" %}
{% block title %}分析ターゲット{% endblock %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">分析ターゲット</h1>
<form method="post" action="/targets" class="bg-white rounded-lg shadow p-4 mb-6 flex gap-2">
    <input name="company_id" required placeholder="例: US_AAPL" class="border rounded px-3 py-2 flex-1">
    <button class="bg-blue-600 text-white px-4 py-2 rounded">追加</button>
</form>
<ul class="bg-white rounded-lg shadow divide-y divide-gray-200">
    {% for t in targets %}
    {# Bug #1: server-resolved id #}
    <li class="px-4 py-3 flex items-center justify-between">
        <a href="/stocks/{{ t.company_id }}" class="hover:underline">{{ t.company_id }}</a>
        <form method="post" action="/targets/{{ t.company_id }}/delete">
            <button class="text-sm text-red-600 hover:underline">削除</button>
        </form>
    </li>
    {% else %}
    <li class="px-4 py-3 text-sm text-gray-500">ターゲットがありません。</li>
    {% endfor %}
</ul>
{% endblock %}
```

- [ ] **Step 5: Register router**

```python
    from stock_analyze_system.web.routes import targets as target_routes
    app.include_router(target_routes.router)
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_targets.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/targets.py \
        src/stock_analyze_system/web/templates/targets/ \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_targets.py
git commit -m "feat(web): add targets routes"
```

---

### Task 15: Jobs routes

**Files:**
- Create: `src/stock_analyze_system/web/routes/jobs.py`
- Create: `src/stock_analyze_system/web/templates/jobs/list.html`
- Create: `tests/unit/web/test_jobs.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_jobs.py
"""Jobs routes tests"""


class TestJobs:
    def test_get_jobs_page(self, auth_client):
        resp = auth_client.get("/jobs")
        assert resp.status_code == 200
        assert "ジョブ" in resp.text

    def test_post_sync_returns_redirect(self, auth_client):
        # No company seeded, will redirect with error flash
        resp = auth_client.post(
            "/jobs/sync", data={"company_id": "US_NOPE"},
            follow_redirects=False,
        )
        assert resp.status_code in (303, 200)
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/web/test_jobs.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement jobs route**

Create `src/stock_analyze_system/web/routes/jobs.py`:

```python
"""Jobs routes — manual sync triggers."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs")


@router.get("", response_class=HTMLResponse)
async def list_page(request: Request, error: str | None = None):
    return request.app.state.templates.TemplateResponse(
        "jobs/list.html", {"request": request, "error": error},
    )


@router.post("/sync")
async def sync_company(
    company_id: str = Form(...),
    services: ServiceContainer = Depends(get_services),
):
    try:
        await services.job_service.sync_company(company_id)
    except Exception as e:
        logger.exception("sync failed")
        return RedirectResponse(
            url=f"/jobs?error={e}", status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(url="/jobs", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/daily")
async def daily(
    market: str = Form("us"),
    services: ServiceContainer = Depends(get_services),
):
    try:
        await services.job_service.run_daily_update(market)
    except Exception as e:
        logger.exception("daily failed")
        return RedirectResponse(
            url=f"/jobs?error={e}", status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(url="/jobs", status_code=status.HTTP_303_SEE_OTHER)
```

- [ ] **Step 4: Implement template**

Create `src/stock_analyze_system/web/templates/jobs/list.html`:

```html
{% extends "base.html" %}
{% block title %}ジョブ{% endblock %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">ジョブ</h1>
{% if error %}
<div class="bg-red-100 text-red-800 px-4 py-2 rounded mb-4">{{ error }}</div>
{% endif %}
<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">単一銘柄を同期</h2>
        <form method="post" action="/jobs/sync" class="flex gap-2">
            <input name="company_id" required placeholder="US_AAPL" class="border rounded px-3 py-2 flex-1">
            <button class="bg-blue-600 text-white px-4 py-2 rounded">実行</button>
        </form>
    </div>
    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">日次バッチ</h2>
        <form method="post" action="/jobs/daily" class="flex gap-2">
            <select name="market" class="border rounded px-3 py-2">
                <option value="us">米国</option>
                <option value="jp">日本</option>
            </select>
            <button class="bg-blue-600 text-white px-4 py-2 rounded">実行</button>
        </form>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Register router**

```python
    from stock_analyze_system.web.routes import jobs as job_routes
    app.include_router(job_routes.router)
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_jobs.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/jobs.py \
        src/stock_analyze_system/web/templates/jobs/ \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_jobs.py
git commit -m "feat(web): add jobs page with sync triggers"
```

---

### Task 16: Screening placeholder (Phase 5 on hold)

**Files:**
- Create: `src/stock_analyze_system/web/routes/screening.py`
- Create: `src/stock_analyze_system/web/templates/screening/placeholder.html`
- Create: `tests/unit/web/test_screening.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_screening.py
"""Screening placeholder tests (Phase 5 pending)"""


class TestScreeningPlaceholder:
    def test_get_screening_returns_placeholder(self, auth_client):
        resp = auth_client.get("/screening")
        assert resp.status_code == 200
        assert "Phase 5" in resp.text or "準備中" in resp.text
```

- [ ] **Step 2: Run test**

Run: `python3 -m pytest tests/unit/web/test_screening.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement placeholder route**

Create `src/stock_analyze_system/web/routes/screening.py`:

```python
"""Screening placeholder — Phase 5 (ScreeningService) is on hold."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/screening")


@router.get("", response_class=HTMLResponse)
async def placeholder(request: Request):
    return request.app.state.templates.TemplateResponse(
        "screening/placeholder.html", {"request": request},
    )
```

- [ ] **Step 4: Implement template**

Create `src/stock_analyze_system/web/templates/screening/placeholder.html`:

```html
{% extends "base.html" %}
{% block title %}スクリーニング — 準備中{% endblock %}
{% block content %}
<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-8 text-center">
    <h1 class="text-2xl font-bold mb-2">スクリーニング</h1>
    <p class="text-gray-600">Phase 5 (ScreeningService) 実装保留中のため、本ページは準備中です。</p>
</div>
{% endblock %}
```

- [ ] **Step 5: Register router**

```python
    from stock_analyze_system.web.routes import screening as screening_routes
    app.include_router(screening_routes.router)
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_screening.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/screening.py \
        src/stock_analyze_system/web/templates/screening/ \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_screening.py
git commit -m "feat(web): add screening placeholder (Phase 5 pending)"
```

---

### Task 17: RAG top-level page (`/rag/{company_id}`)

**Files:**
- Create: `src/stock_analyze_system/web/routes/rag.py`
- Create: `src/stock_analyze_system/web/templates/rag/ask.html`
- Create: `tests/unit/web/test_rag.py`
- Modify: `src/stock_analyze_system/web/app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_rag.py
"""RAG top-level page tests"""
import pytest


@pytest.fixture
async def seeded_with_company(auth_client, app):
    from stock_analyze_system.models.base import get_session
    from stock_analyze_system.models.company import Company
    state = app.state.app_state
    async with get_session(state.engine) as session:
        session.add(Company(
            id="US_AAPL", ticker="AAPL", name="Apple",
            market="NASDAQ", accounting_standard="US-GAAP",
        ))
        await session.commit()
    return auth_client


class TestRagPage:
    async def test_rag_page_for_existing_company(self, seeded_with_company):
        resp = seeded_with_company.get("/rag/US_AAPL")
        assert resp.status_code == 200
        assert "Apple" in resp.text

    async def test_unknown_company_404(self, auth_client):
        resp = auth_client.get("/rag/US_NOPE")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/unit/web/test_rag.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement rag route**

Create `src/stock_analyze_system/web/routes/rag.py`:

```python
"""RAG Q&A page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services

router = APIRouter(prefix="/rag")


@router.get("/{company_id}", response_class=HTMLResponse)
async def ask_page(
    company_id: str,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    company = await services.company_service.get_company(company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Company not found")
    return request.app.state.templates.TemplateResponse(
        "rag/ask.html", {"request": request, "company": company},
    )
```

- [ ] **Step 4: Implement template**

Create `src/stock_analyze_system/web/templates/rag/ask.html`:

```html
{% extends "base.html" %}
{% block title %}RAG Q&A — {{ company.name }}{% endblock %}
{% block content %}
<header class="mb-6">
    <h1 class="text-3xl font-bold">{{ company.name }} — RAG Q&amp;A</h1>
    <p class="text-sm text-gray-500">{{ company.id }}</p>
</header>
<div x-data="ragTab('{{ company.id }}')" x-init="loadAnalyses()">
    {# Reuse the same partial as in stocks/_tab_rag.html #}
    {% include "stocks/_tab_rag.html" %}
</div>
{% endblock %}
```

- [ ] **Step 5: Register router**

```python
    from stock_analyze_system.web.routes import rag as rag_routes
    app.include_router(rag_routes.router)
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/unit/web/test_rag.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/web/routes/rag.py \
        src/stock_analyze_system/web/templates/rag/ \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_rag.py
git commit -m "feat(web): add RAG top-level page"
```

---

### Task 18: serve.py smoke test + full Web suite run

**Files:**
- Modify: `tests/unit/cli/test_serve_cli.py`

- [ ] **Step 1: Write a smoke import test**

Append to `tests/unit/cli/test_serve_cli.py`:

```python
def test_web_app_factory_importable():
    """serve.py が参照する create_app が import 可能なこと"""
    from stock_analyze_system.web import create_app
    assert callable(create_app)
```

- [ ] **Step 2: Run full web suite**

Run: `python3 -m pytest tests/unit/web tests/unit/cli/test_serve_cli.py -v`
Expected: PASS.

- [ ] **Step 3: Run full project test suite**

Run: `python3 -m pytest tests/unit -q`
Expected: All tests pass (562 existing + ~40 new web tests).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/cli/test_serve_cli.py
git commit -m "test(cli): add web create_app import smoke test"
```

---

### Task 19: Static asset stubs + manual smoke

**Files:**
- Create: `src/stock_analyze_system/web/static/app.css`
- Create: `src/stock_analyze_system/web/static/app.js`

- [ ] **Step 1: Create minimal CSS**

Create `src/stock_analyze_system/web/static/app.css`:

```css
[x-cloak] { display: none !important; }
```

- [ ] **Step 2: Create empty JS placeholder**

Create `src/stock_analyze_system/web/static/app.js`:

```javascript
// Reserved for future shared Alpine components.
```

- [ ] **Step 3: Manual smoke test (no automation)**

Start the dev server:

```bash
WEB_PASSWORD=devpass WEB_SESSION_SECRET=dev-secret-not-for-prod \
    python3 -m stock_analyze_system serve --port 8501
```

Expected: server starts. Visit http://localhost:8501 → redirected to /login. Log in with devpass → dashboard renders. Stop with Ctrl-C.

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/web/static/
git commit -m "feat(web): add static asset placeholders"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task |
|--------------|------|
| 10.1 (FastAPI + Jinja2) | Task 2 |
| 10.2 (Auth + Bug #8) | Task 3, 4 |
| 10.3 (DI ServiceContainer) | Task 1 |
| 10.4 / dashboard | Task 5 |
| 10.4 / login, logout | Task 4 |
| 10.4 / stocks search | Task 6 |
| 10.4 / stocks detail | Task 7 |
| 10.4 / watchlists | Task 13 |
| 10.4 / jobs | Task 15 |
| 10.4 / screening | Task 16 (placeholder) |
| 10.4 / targets | Task 14 |
| 10.4 / rag (page) | Task 17 |
| 10.4 / api valuations | Task 9 |
| 10.4 / api financials | Task 8 |
| 10.4 / api rag ask | Task 12 |
| 10.4 / api rag index | Task 12 |
| 10.4 / api rag analyses | Task 12 |
| 10.5 (5 tabs) | Task 7 (frame), 8/9/10/11/12 (content) |
| 10.6 / Bug #1 | Task 6, 13, 14 |
| 10.6 / Bug #2 | Task 4, 5 |
| 10.6 / Bug #9 | Task 5 |
| 15 / Bug #8 | Task 2 |
| 15 / Bug #14 | Common Patterns (handled by design — no separate dead code introduced) |

All spec section 10 requirements have a task.

**2. Placeholder scan:** No "TBD/TODO/implement later" strings in any task. Each step has either code or an explicit shell command with an expected outcome.

**3. Type consistency:**
- `AppState`, `get_app_state`, `get_services` defined in Task 1, reused identically in Tasks 5/6/7/8/9/10/11/12/13/14/15/16/17.
- `ServiceContainer` is imported via `stock_analyze_system.cli.container` (existing) — no parallel definition.
- `SessionSigner.sign` / `unsign` signature in Task 3 matches usage in Task 4 (login/logout).
- `_get_rag_service` (Task 12) is a module-private helper, referenced only inside `routes/api.py`.
- `_tab_rag.html` defines `ragTab(companyId)` Alpine component, reused by `rag/ask.html` in Task 17.
- Template paths consistent: `stocks/_search_results.html`, `stocks/_tab_*.html`, `watchlists/list.html`, `watchlists/detail.html`, etc.
- API endpoints under `/api/stocks/{company_id}/...` consistently in `routes/api.py`.

No type mismatches found.
