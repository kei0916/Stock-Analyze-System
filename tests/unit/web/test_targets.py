"""Analysis targets routes tests"""
from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
from stock_analyze_system.services.job import SyncResult


@pytest.fixture(autouse=True)
def target_valuation_refresh(monkeypatch):
    import stock_analyze_system.services.job as job_module

    refresh = AsyncMock(return_value=SyncResult(company_id="TEST", valuations_count=1))
    monkeypatch.setattr(
        job_module.JobService,
        "update_valuation_for_company",
        refresh,
        raising=False,
    )
    return refresh


class TestTargetsList:
    def test_get_list_authenticated(self, auth_client):
        resp = auth_client.get("/targets")
        assert resp.status_code == 200
        assert "ターゲット" in resp.text

    def test_get_list_unauthenticated_redirects(self, client):
        resp = client.get("/targets", follow_redirects=False)
        assert resp.status_code == 303


class TestTargetsCreate:
    def test_add_target(self, seeded_aapl_client, target_valuation_refresh):
        resp = seeded_aapl_client.post(
            "/targets",
            data={"company_id": "US_AAPL"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        target_valuation_refresh.assert_awaited_once_with("US_AAPL")
        resp = seeded_aapl_client.get("/targets")
        assert "US_AAPL" in resp.text

    def test_add_target_auto_registers_sec_ticker(self, monkeypatch, auth_client):
        async def fake_list_universe(self):
            return [
                {
                    "ticker": "WRBY",
                    "cik": "0001504776",
                    "name": "Warby Parker Inc.",
                    "exchange": "NYSE",
                },
            ]

        monkeypatch.setattr(SecEdgarClient, "list_universe", fake_list_universe)

        resp = auth_client.post(
            "/targets",
            data={"company_id": "US_WRBY"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        resp = auth_client.get("/targets")
        assert "/stocks/US_WRBY" in resp.text


class TestTargetsDelete:
    def test_delete_target(self, seeded_aapl_client):
        seeded_aapl_client.post(
            "/targets",
            data={"company_id": "US_AAPL"},
            follow_redirects=False,
        )
        resp = seeded_aapl_client.get("/targets")
        assert '/stocks/US_AAPL' in resp.text
        resp = seeded_aapl_client.post(
            "/targets/US_AAPL/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # 詳細ページへのアンカーが消えている
        # (placeholder の "例: US_AAPL" 文字列は残るので /stocks/US_AAPL で判定)
        resp = seeded_aapl_client.get("/targets")
        assert '/stocks/US_AAPL' not in resp.text
        assert "ターゲットがありません" in resp.text

    def test_delete_unknown_returns_404(self, auth_client):
        resp = auth_client.post(
            "/targets/US_NOPE/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 404
