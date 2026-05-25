"""Jobs routes tests"""
from unittest.mock import AsyncMock


class TestJobsList:
    def test_get_jobs_page(self, auth_client):
        resp = auth_client.get("/jobs")
        assert resp.status_code == 200
        assert "ジョブ" in resp.text
        assert "単一銘柄を同期" in resp.text
        assert "日次バッチ" in resp.text

    def test_jobs_page_shows_error_from_query(self, auth_client):
        resp = auth_client.get("/jobs?error=something+broke")
        assert resp.status_code == 200
        assert "something broke" in resp.text

    def test_unauthenticated_redirects(self, client):
        resp = client.get("/jobs", follow_redirects=False)
        assert resp.status_code == 303


class TestJobsSync:
    def test_sync_success_redirects(self, monkeypatch, auth_client):
        """job_service.sync_companyが成功したら/jobsへリダイレクト"""
        import stock_analyze_system.services.job as job_module
        monkeypatch.setattr(
            job_module.JobService, "sync_company", AsyncMock(return_value=None),
        )
        resp = auth_client.post(
            "/jobs/sync", data={"company_id": "US_AAPL"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/jobs"

    def test_sync_failure_redirects_with_error(self, monkeypatch, auth_client):
        """例外時は?error=...付きでリダイレクト"""
        import stock_analyze_system.services.job as job_module
        monkeypatch.setattr(
            job_module.JobService, "sync_company",
            AsyncMock(side_effect=RuntimeError("boom")),
        )
        resp = auth_client.post(
            "/jobs/sync", data={"company_id": "US_NOPE"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/jobs?error=" in resp.headers["location"]
        assert "boom" not in resp.headers["location"]

    def test_sync_rate_limit_redirects_back_to_jobs(self, monkeypatch, auth_client):
        import stock_analyze_system.services.job as job_module
        monkeypatch.setattr(
            job_module.JobService, "sync_company", AsyncMock(return_value=None),
        )

        for _ in range(3):
            resp = auth_client.post(
                "/jobs/sync", data={"company_id": "US_AAPL"},
                follow_redirects=False,
            )
            assert resp.status_code == 303

        resp = auth_client.post(
            "/jobs/sync", data={"company_id": "US_AAPL"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert "/jobs?error=" in resp.headers["location"]


class TestJobsDaily:
    def test_daily_success_redirects(self, monkeypatch, auth_client):
        import stock_analyze_system.services.job as job_module
        monkeypatch.setattr(
            job_module.JobService, "run_daily_update",
            AsyncMock(return_value=None),
        )
        resp = auth_client.post(
            "/jobs/daily", data={"market": "us"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/jobs"

    def test_daily_failure_redirects_with_error(self, monkeypatch, auth_client):
        """run_daily_update 例外時は ?error=... 付きリダイレクト"""
        import stock_analyze_system.services.job as job_module
        monkeypatch.setattr(
            job_module.JobService, "run_daily_update",
            AsyncMock(side_effect=RuntimeError("daily failed")),
        )
        resp = auth_client.post(
            "/jobs/daily", data={"market": "us"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/jobs?error=" in resp.headers["location"]
        assert "daily+failed" not in resp.headers["location"]
        assert "daily%20failed" not in resp.headers["location"]

    def test_daily_rate_limit_redirects_back_to_jobs(self, monkeypatch, auth_client):
        import stock_analyze_system.services.job as job_module
        monkeypatch.setattr(
            job_module.JobService, "run_daily_update",
            AsyncMock(return_value=None),
        )

        for _ in range(3):
            resp = auth_client.post(
                "/jobs/daily", data={"market": "us"},
                follow_redirects=False,
            )
            assert resp.status_code == 303

        resp = auth_client.post(
            "/jobs/daily", data={"market": "us"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert "/jobs?error=" in resp.headers["location"]
