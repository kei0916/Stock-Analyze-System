"""Stocks routes tests"""
from datetime import date

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing


class TestStockSearchPage:
    def test_get_search_page(self, auth_client):
        resp = auth_client.get("/stocks/search")
        assert resp.status_code == 200
        assert "検索" in resp.text


class TestStockSearchResults:
    def test_search_results_partial(self, seeded_aapl_client):
        resp = seeded_aapl_client.get("/stocks/search/results?q=Apple")
        assert resp.status_code == 200
        assert "AAPL" in resp.text
        assert "US_AAPL" in resp.text

    def test_empty_query_returns_no_results(self, seeded_aapl_client):
        resp = seeded_aapl_client.get("/stocks/search/results?q=")
        assert resp.status_code == 200
        assert "AAPL" not in resp.text


class TestStockDetailPage:
    def test_detail_page_for_existing_company(self, seeded_aapl_client):
        resp = seeded_aapl_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        assert "Apple" in resp.text
        for label in ("財務", "バリュエーション", "分析", "ファイリング"):
            assert label in resp.text

    def test_detail_page_unknown_company_404(self, auth_client):
        resp = auth_client.get("/stocks/US_NOPE")
        assert resp.status_code == 404

    def test_detail_page_has_financial_field_picker(self, seeded_aapl_client):
        """財務タブに複数選択用のフィールドピッカー + 複数チャート用コンテナ"""
        resp = seeded_aapl_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        assert "data-financial-fieldpicker" in resp.text
        assert "data-fieldpicker-chips" in resp.text
        assert "data-fieldpicker-add" in resp.text
        assert "data-financial-charts" in resp.text

    def test_detail_page_has_valuation_field_picker(self, seeded_aapl_client):
        """バリュエーションタブにフィールドピッカー + 複数チャート用コンテナ + 日次5年表記"""
        resp = seeded_aapl_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        assert "data-valuation-fieldpicker" in resp.text
        assert "data-valuation-chips" in resp.text
        assert "data-valuation-add" in resp.text
        assert "data-valuation-charts" in resp.text
        assert "日次 5年推移" in resp.text

    def test_detail_page_has_analyze_button_and_progress(self, seeded_aapl_client):
        """分析タブに「決算分析」ボタンと進捗バー DOM がある"""
        resp = seeded_aapl_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        assert "data-rag-analyze" in resp.text
        assert "決算分析" in resp.text
        assert "data-rag-analyze-progress" in resp.text
        assert "data-progress-bar" in resp.text
        assert "data-progress-label" in resp.text
        # 旧 NDJSON エンドポイント URL は data 属性から削除済み
        # (キュー API /api/analysis-jobs に移行)
        assert "/api/stocks/US_AAPL/rag/analyze" not in resp.text
        assert "data-rag-rerun" in resp.text


@pytest.fixture
async def seeded_filings_client(auth_client, db_writer):
    """Apple + Filing 1件をseedしたauth_clientを返す"""
    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        Filing(
            company_id="US_AAPL",
            source="SEC",
            filing_type="10-K",
            period_type="annual",
            fiscal_year=2024,
            period_end=date(2024, 9, 30),
            filed_at=date(2024, 11, 1),
            accession_no="0000320193-24-000123",
        ),
    )
    return auth_client


class TestStockFilingsTab:
    def test_filings_listed_in_detail_page(self, seeded_filings_client):
        resp = seeded_filings_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        assert "10-K" in resp.text
        assert "2024" in resp.text
        assert "0000320193-24-000123" in resp.text

    def test_detail_page_no_filings_shows_empty_message(self, seeded_aapl_client):
        resp = seeded_aapl_client.get("/stocks/US_AAPL")
        assert resp.status_code == 200
        assert "ファイリングがありません" in resp.text
