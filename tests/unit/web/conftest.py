"""Webテスト共通フィクスチャ"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from fastapi.testclient import TestClient

from stock_analyze_system.config import AppConfig, WebConfig
from stock_analyze_system.models.base import create_db_engine, get_session
from stock_analyze_system.models.company import Company
from stock_analyze_system.web.app import create_app
from stock_analyze_system.web.auth import hash_password

# bcrypt は遅いので 1 度だけ計算してテスト全体で使い回す。
TEST_PASSWORD = "test-pass"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture
def web_config(tmp_path) -> AppConfig:
    cfg = AppConfig()
    cfg.web = WebConfig(
        host="127.0.0.1",
        port=8501,
        password_hash=TEST_PASSWORD_HASH,
        session_secret="test-secret-please-do-not-use-in-prod",
        heavy_rate_limit_attempts=3,
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
    )
    # ファイルDBを使う — :memory:はTestClientのlifespanスレッドと
    # テストスレッドでDBが共有されないため
    cfg.database.path = str(tmp_path / "test.db")
    return cfg


@pytest.fixture
def app(web_config):
    return create_app(config=web_config)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    """有効なセッションクッキー付きのTestClient"""
    resp = client.post("/login", data={"password": "test-pass"}, follow_redirects=False)
    assert resp.status_code == 303
    return client


@pytest.fixture
def db_writer(web_config) -> Callable[..., Awaitable[None]]:
    """web_config のDBに任意のSQLAlchemyモデル行を追加するヘルパ"""

    async def _write(*rows) -> None:
        engine = await create_db_engine(web_config.database.path)
        try:
            async with get_session(engine) as session:
                for row in rows:
                    session.add(row)
        finally:
            await engine.dispose()

    return _write


@pytest.fixture
async def seeded_aapl_client(auth_client, db_writer):
    """Apple 1社だけseed済みの auth_client を返す"""
    await db_writer(
        Company(
            id="US_AAPL",
            ticker="AAPL",
            name="Apple Inc",
            market="NASDAQ",
            accounting_standard="US-GAAP",
        )
    )
    return auth_client
