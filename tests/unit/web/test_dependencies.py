"""web/dependencies.py のテスト"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from stock_analyze_system.config import AppConfig
from stock_analyze_system.shared.clients import ClientBundle
from stock_analyze_system.web.dependencies import (
    AppState,
    get_session_dep,
    get_services,
)


@pytest.fixture
async def state():
    cfg = AppConfig()
    cfg.database.path = ":memory:"
    s = await AppState.create(cfg)
    try:
        yield s
    finally:
        await s.dispose()


async def test_app_state_creates_engine(state):
    assert isinstance(state.engine, AsyncEngine)


async def test_app_state_passes_sec_rate_limit(tmp_path):
    cfg = AppConfig()
    cfg.database.path = str(tmp_path / "rate.db")
    cfg.sec_edgar.email = "sec@example.com"
    cfg.sec_edgar.rate_limit_rps = 10

    with patch("stock_analyze_system.ingestion.sec_edgar.SecEdgarClient") as sec_cls:
        state = await AppState.create(cfg)

    try:
        sec_cls.assert_called_once_with(email="sec@example.com", rate=10)
    finally:
        await state.engine.dispose()


async def test_get_session_dep_yields_async_session(state):
    async for session in get_session_dep(state):
        assert isinstance(session, AsyncSession)
        break


async def test_get_services_wires_container(state):
    async for session in get_session_dep(state):
        services = await get_services(session, state)
        assert services.company_service is not None
        assert services.financial_service is not None
        break


async def test_get_services_wires_rag_when_pageindex_enabled(tmp_path):
    cfg = AppConfig()
    cfg.database.path = str(tmp_path / "rag-enabled.db")
    cfg.pageindex.enabled = True
    state = await AppState.create(cfg)
    try:
        async for session in get_session_dep(state):
            services = await get_services(session, state)
            assert services.rag_service is not None
            assert services.rag_service._qa_history_repo is not None
            assert (
                services.rag_service._filing_content_service
                is services.filing_content_service
            )
            break
    finally:
        await state.dispose()


def _make_state(client_close_side_effects=None):
    """テスト用 AppState を組み立てる。close は AsyncMock で差し替え."""
    side_effects = client_close_side_effects or {}

    def _make_client(name):
        client = MagicMock()
        client.close = AsyncMock(side_effect=side_effects.get(name))
        return client

    bundle = ClientBundle(
        sec=_make_client("sec"),
        edinet=_make_client("edinet"),
        yahoo=_make_client("yahoo"),
        fmp=_make_client("fmp"),
    )
    engine = MagicMock()
    engine.dispose = AsyncMock(side_effect=side_effects.get("engine"))
    return AppState(
        config=MagicMock(),
        engine=engine,
        clients=bundle,
        session_factory=MagicMock(),
        analysis_queue=MagicMock(),
    )


@pytest.mark.asyncio
async def test_dispose_invokes_gather_with_all_close_calls():
    """dispose は共有 client の close を 1 回の gather に渡し、engine.dispose も呼ぶ."""
    state = _make_state()
    with patch(
        "stock_analyze_system.shared.clients.asyncio.gather",
        wraps=asyncio.gather,
    ) as gather_spy:
        await state.dispose()

    assert gather_spy.call_count == 1
    call_args = gather_spy.call_args
    assert len(call_args.args) == 4
    assert call_args.kwargs.get("return_exceptions") is True
    assert state.clients.sec.close.await_count == 1
    assert state.clients.edinet.close.await_count == 1
    assert state.clients.yahoo.close.await_count == 1
    assert state.clients.fmp.close.await_count == 1
    assert state.engine.dispose.await_count == 1


@pytest.mark.asyncio
async def test_dispose_continues_when_one_client_close_raises(caplog):
    """1 client の close が例外でも他 3 op が呼ばれ、warning ログが出る."""
    state = _make_state(client_close_side_effects={"edinet": RuntimeError("boom")})
    with caplog.at_level("WARNING", logger="stock_analyze_system.shared.clients"):
        await state.dispose()
    assert state.clients.sec.close.await_count == 1
    assert state.clients.edinet.close.await_count == 1
    assert state.clients.yahoo.close.await_count == 1
    assert state.clients.fmp.close.await_count == 1
    assert state.engine.dispose.await_count == 1
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("edinet" in r.getMessage() and "boom" in r.getMessage() for r in warnings)


@pytest.mark.asyncio
async def test_dispose_warning_preserves_exc_info(caplog):
    """例外発生時の warning にトレースバックが exc_info として保存される."""
    boom = RuntimeError("boom")
    state = _make_state(client_close_side_effects={"edinet": boom})
    with caplog.at_level("WARNING", logger="stock_analyze_system.shared.clients"):
        await state.dispose()
    failing = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "edinet" in r.getMessage()
    ]
    assert failing, "edinet 用の warning が見つからない"
    record = failing[0]
    assert record.exc_info is not None
    exc_type, exc_value, _ = record.exc_info
    assert exc_type is RuntimeError
    assert exc_value is boom
