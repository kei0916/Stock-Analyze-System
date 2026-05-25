"""Topbar analysis-status badge rendering tests."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


CSS_PATH = Path("src/stock_analyze_system/web/static/app.css")
APP_JS_PATH = Path("src/stock_analyze_system/web/static/app.js")


class ElementByIdParser(HTMLParser):
    def __init__(self, element_id: str) -> None:
        super().__init__()
        self.element_id = element_id
        self.attrs: dict[str, str | None] | None = None

    def handle_starttag(
        self,
        tag: str,  # noqa: ARG002
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attr_map = dict(attrs)
        if attr_map.get("id") == self.element_id:
            self.attrs = attr_map


def find_element_attrs(html: str, element_id: str) -> dict[str, str | None]:
    parser = ElementByIdParser(element_id)
    parser.feed(html)
    assert parser.attrs is not None
    return parser.attrs


def test_topbar_badge_present_on_dashboard(auth_client):
    response = auth_client.get("/")

    assert response.status_code == 200
    badge = find_element_attrs(response.text, "analysis-status-badge")
    assert badge["class"] == "topbar__badge"
    assert badge["href"] == "/"
    assert "hidden" in badge
    assert badge["aria-label"] == "分析キューの状態"
    assert badge["aria-live"] == "polite"
    assert badge["aria-atomic"] == "true"
    assert "data-analysis-status-badge" in badge
    assert "topbar__badge-dot" in response.text
    assert "topbar__badge-text" in response.text


def test_topbar_badge_present_on_watchlists(auth_client):
    response = auth_client.get("/watchlists")

    assert response.status_code == 200
    assert find_element_attrs(response.text, "analysis-status-badge")["href"] == "/"


def test_app_script_carries_asset_version_data_attribute(auth_client):
    response = auth_client.get("/")

    assert response.status_code == 200
    assert "data-asset-version=" in response.text
    assert "window.__assetVersion" not in response.text


def test_topbar_badge_css_keeps_hidden_badge_invisible():
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".topbar__badge[hidden] {\n  display: none;\n}" in css
    assert "@keyframes analysis-badge-pulse" in css
    assert '.topbar__badge[data-state="warning"]' in css
    assert "@media (max-width: 720px)" in css


def test_app_js_wires_analysis_status_badge_polling():
    js = APP_JS_PATH.read_text(encoding="utf-8")

    assert "/static/analysis_status.js?v=${version}" in js
    assert "ASSET_VERSION" in js
    assert "analysis-jobs:changed" in js
    assert "buildBadgeViewModel(content, warning)" in js
    assert "buildBadgeText(active, nowMs)" in js
    assert "buildTitlePrefix(active)" in js
    assert "shouldWarnWorkerDown(jobs, nowMs)" in js
    assert "detectCompletions(prevActiveIds, jobs)" in js
    assert "Notification.requestPermission()" in js
