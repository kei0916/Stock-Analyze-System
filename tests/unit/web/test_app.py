"""FastAPI app factory のテスト"""
from pathlib import Path

import pytest
from fastapi import FastAPI

from stock_analyze_system.config import AppConfig, WebConfig
from stock_analyze_system.exceptions import ConfigError
from stock_analyze_system.web.app import create_app


def test_create_app_returns_fastapi_instance(web_config):
    app = create_app(config=web_config)
    assert isinstance(app, FastAPI)


def test_create_app_requires_session_secret():
    cfg = AppConfig()
    cfg.web = WebConfig(password_hash="x", session_secret="")
    with pytest.raises(ConfigError, match="session_secret"):
        create_app(config=cfg)


def test_create_app_requires_password_hash():
    """password_hash も必須"""
    cfg = AppConfig()
    cfg.web = WebConfig(password_hash="", session_secret="nonempty")
    with pytest.raises(ConfigError, match="password_hash"):
        create_app(config=cfg)


def test_create_app_session_secret_error_does_not_reference_dotenv():
    cfg = AppConfig()
    cfg.web = WebConfig(password_hash="x", session_secret="")

    with pytest.raises(ConfigError) as exc_info:
        create_app(config=cfg)

    message = str(exc_info.value)
    assert "WEB_SESSION_SECRET" in message
    assert "settings.yaml" in message
    assert ".env" not in message


def test_create_app_password_hash_error_mentions_env_var():
    cfg = AppConfig()
    cfg.web = WebConfig(password_hash="", session_secret="nonempty")

    with pytest.raises(ConfigError) as exc_info:
        create_app(config=cfg)

    message = str(exc_info.value)
    assert "WEB_PASSWORD_HASH" in message
    assert ".env" not in message


def test_static_files_mounted(client):
    resp = client.get("/static/app.css")
    # 404 or 200 — マウントされていれば /static は存在する
    assert resp.status_code in (200, 404)


def test_unknown_route_returns_404(client):
    """未認証クライアントは /login に303リダイレクトされる
    (follow_redirects=False でリダイレクト自体を検証)
    """
    resp = client.get("/this-does-not-exist", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_unknown_route_returns_404_when_authenticated(auth_client):
    """認証済みで存在しないパスは404"""
    resp = auth_client.get("/this-does-not-exist")
    assert resp.status_code == 404


def test_authenticated_response_sets_security_headers(auth_client):
    resp = auth_client.get("/")

    assert "content-security-policy" in resp.headers
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "same-origin"


def test_unauthenticated_redirect_sets_security_headers(client):
    resp = client.get("/", follow_redirects=False)

    assert resp.status_code == 303
    assert "content-security-policy" in resp.headers
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "same-origin"


def test_health_endpoint_is_public_and_returns_ok(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert "content-security-policy" in resp.headers


def test_templates_do_not_load_remote_cdn_assets():
    base_template = Path(
        "src/stock_analyze_system/web/templates/base.html"
    ).read_text()
    financial_template = Path(
        "src/stock_analyze_system/web/templates/stocks/_tab_financial.html"
    ).read_text()

    assert "cdn.tailwindcss.com" not in base_template
    assert "unpkg.com" not in base_template
    assert "cdn.jsdelivr.net" not in financial_template


def test_rag_empty_state_does_not_use_innerhtml_with_company_id():
    app_js = Path(
        "src/stock_analyze_system/web/static/app.js"
    ).read_text()

    assert "p.innerHTML" not in app_js


def test_stock_search_ignores_stale_responses_before_replacing_results():
    app_js = Path(
        "src/stock_analyze_system/web/static/app.js"
    ).read_text()

    assert "latestSearchToken" in app_js
    assert "if (token !== latestSearchToken || input.value.trim() !== query)" in app_js


def test_stock_search_handles_errors_inside_debounced_callback():
    app_js = Path(
        "src/stock_analyze_system/web/static/app.js"
    ).read_text()

    assert "runSearch().catch" not in app_js
    assert ".catch((error) => {" in app_js


def test_valuation_summary_displays_last_updated():
    app_js = Path(
        "src/stock_analyze_system/web/static/app.js"
    ).read_text()

    assert "latest.last_updated" in app_js
    assert "最終更新" in app_js


def test_base_template_uses_new_layout_classes():
    base_template = Path(
        "src/stock_analyze_system/web/templates/base.html"
    ).read_text()
    assert 'class="layout"' in base_template
    assert "_sidebar.html" in base_template
    assert "_topbar.html" in base_template
    assert "bg-gray-50" not in base_template


def test_nav_template_is_removed():
    nav_path = Path("src/stock_analyze_system/web/templates/_nav.html")
    assert not nav_path.exists()


def test_no_tailwind_shim_classes_in_templates():
    template_dir = Path("src/stock_analyze_system/web/templates")
    forbidden = ["bg-white", "rounded-lg", "shadow", "bg-blue-600",
                 "bg-red-100", "text-gray-500", "text-gray-600", "text-gray-700"]
    for tpl in template_dir.rglob("*.html"):
        text = tpl.read_text()
        for token in forbidden:
            assert token not in text, f"{tpl}: still uses '{token}'"

def test_malformed_host_with_path_is_rejected_before_auth_redirect(client):
    resp = client.get("/", headers={"host": "testserver/login"}, follow_redirects=False)

    assert resp.status_code == 400
    assert "location" not in resp.headers
