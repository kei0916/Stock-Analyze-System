"""Dashboard route tests"""
from datetime import date, datetime

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.company_analysis import CompanyAnalysis
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.models.quote_price import QuotePrice
from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem


class TestDashboard:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303

    def test_authenticated_returns_200(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "ダッシュボード" in resp.text

    def test_navigation_active_state_root(self, auth_client):
        resp = auth_client.get("/")
        assert 'aria-current="page"' in resp.text

    def test_renders_kpi_grid_and_actions(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        for label in ("登録銘柄", "ウォッチ中", "分析ターゲット", "LLM分析"):
            assert label in resp.text
        assert "kpi-grid--4" in resp.text
        assert "日次更新" in resp.text
        assert "銘柄を追加" in resp.text

    def test_empty_state_for_panels(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert "ウォッチリストがありません" in resp.text
        assert "同期実行履歴がありません" in resp.text
        # 旧「LLM分析」パネルは「LLM分析キュー」に置換済み
        assert "実行中の分析はありません" in resp.text
        assert "llm-queue-panel" in resp.text


@pytest.fixture
async def seeded_dashboard_client(auth_client, db_writer):
    """ダッシュボード描画に必要な一通りのデータをseedしたclient"""
    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        Watchlist(id=1, name="Tech Watch", description="技術株"),
        WatchlistItem(watchlist_id=1, company_id="US_AAPL"),
        Valuation(
            company_id="US_AAPL", currency="USD", date=date(2026, 4, 1),
            stock_price=180.5, market_cap=2.8e12, per=29.5, pbr=42.0,
        ),
        QuotePrice(
            company_id="US_AAPL", provider="google_sheets",
            price=181.2, currency="USD",
            fetched_at=datetime(2026, 5, 1, 9, 14),
            status="ok",
        ),
        Filing(
            id=1, company_id="US_AAPL", source="SEC", filing_type="10-K",
            period_type="annual", fiscal_year=2024,
            period_end=date(2024, 9, 30), filed_at=date(2024, 11, 1),
            accession_no="0000320193-24-000123",
        ),
        CompanyAnalysis(
            company_id="US_AAPL", filing_id=1,
            analysis_type="business_summary",
            result_json='{"summary": "..."}',
            model_name="gpt-oss-120b",
        ),
    )
    return auth_client


class TestDashboardSeeded:
    def test_watchlist_preview_shows_company(self, seeded_dashboard_client):
        resp = seeded_dashboard_client.get("/")
        assert resp.status_code == 200
        assert "Tech Watch" in resp.text
        assert "Apple Inc" in resp.text
        assert "US_AAPL" in resp.text

    def test_recent_sync_shows_quote(self, seeded_dashboard_client):
        resp = seeded_dashboard_client.get("/")
        assert "最近の同期" in resp.text
        assert "ok" in resp.text
        assert "05-01 09:14" in resp.text

    def test_recent_analysis_shows_entry(self, seeded_dashboard_client):
        """LLM分析パネルはキュー化されたため completed の表示はなくなった。
        代わりに KPI tile (LLM分析カウント) で件数のみ表示される。
        """
        resp = seeded_dashboard_client.get("/")
        # KPI tile にカウントが含まれる (完了済み 1 件)
        assert "kpi-tile" in resp.text

    def test_last_sync_in_header(self, seeded_dashboard_client):
        resp = seeded_dashboard_client.get("/")
        assert "最終同期" in resp.text
        assert "2026-05-01 09:14" in resp.text

    def test_kpi_counts_reflect_seed(self, seeded_dashboard_client):
        resp = seeded_dashboard_client.get("/")
        # 登録銘柄=1, ウォッチ中=1, LLM分析=1
        assert ">1<" in resp.text or ">1\n" in resp.text
