"""Web API テスト: /api/analysis-jobs"""
from __future__ import annotations

import pytest

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing


@pytest.fixture
async def seeded_filing(seeded_aapl_client, db_writer):
    filing = Filing(
        company_id="US_AAPL",
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    )
    await db_writer(filing)
    return {
        "client": seeded_aapl_client,
        "company_id": "US_AAPL",
        "filing_id": 1,
    }


@pytest.fixture
async def seeded_msft_filing(seeded_filing, db_writer):
    """別 company (MSFT) と、その配下の filing を追加で seed."""
    await db_writer(
        Company(
            id="US_MSFT",
            ticker="MSFT",
            name="Microsoft Corp",
            market="NASDAQ",
            accounting_standard="US-GAAP",
        )
    )
    msft_filing = Filing(
        company_id="US_MSFT",
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000789019-24-000111",
    )
    await db_writer(msft_filing)
    return {
        **seeded_filing,
        "msft_company_id": "US_MSFT",
        "msft_filing_id": 2,
    }


class TestCreateJob:
    def test_create_returns_201_with_pending_job(self, seeded_filing):
        client = seeded_filing["client"]
        resp = client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "pending"
        assert data["company_id"] == "US_AAPL"
        assert data["filing_id"] == 1
        assert "job_id" in data

    def test_create_returns_200_for_duplicate(self, seeded_filing):
        client = seeded_filing["client"]
        body = {
            "company_id": seeded_filing["company_id"],
            "filing_id": seeded_filing["filing_id"],
        }
        first = client.post("/api/analysis-jobs", json=body)
        assert first.status_code == 201
        first_id = first.json()["job_id"]

        second = client.post("/api/analysis-jobs", json=body)
        assert second.status_code == 200
        assert second.json()["job_id"] == first_id

    def test_create_requires_auth(self, app):
        """auth されていない TestClient で /login にリダイレクトされる"""
        from fastapi.testclient import TestClient
        with TestClient(app) as fresh_client:
            resp = fresh_client.post(
                "/api/analysis-jobs",
                json={"company_id": "US_AAPL", "filing_id": 1},
                follow_redirects=False,
            )
            assert resp.status_code == 303
            assert resp.headers["location"] == "/login"

    def test_duplicate_post_is_not_rate_limited(self, seeded_filing):
        """重複 POST は rate limit を消費せず既存 job_id を返す。

        web_config では heavy_rate_limit_attempts=3。同じ company+filing への
        リトライ・複数タブからの POST は cheap な重複チェックで早期 return
        されるべきで、4回目以降も 200 で job_id を返すこと。
        """
        client = seeded_filing["client"]
        body = {
            "company_id": seeded_filing["company_id"],
            "filing_id": seeded_filing["filing_id"],
        }
        first = client.post("/api/analysis-jobs", json=body)
        assert first.status_code == 201, first.text
        first_id = first.json()["job_id"]

        for _ in range(5):
            resp = client.post("/api/analysis-jobs", json=body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["job_id"] == first_id

    def test_create_rejects_mismatched_company_and_filing(
        self, seeded_msft_filing,
    ):
        """filing が異なる company に属する場合は 404 を返す。

        会社A の company_id と、会社B 配下の filing_id を渡された場合、
        旧 API (/api/companies/{id}/rag/ask) と同様 404 で弾く。
        500 にも、ジョブの不整合な作成にもならないこと。
        """
        client = seeded_msft_filing["client"]
        resp = client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_msft_filing["company_id"],
                "filing_id": seeded_msft_filing["msft_filing_id"],
            },
        )
        assert resp.status_code == 404, resp.text

    def test_create_rejects_unknown_filing(self, seeded_filing):
        """存在しない filing_id は 404 を返す。"""
        client = seeded_filing["client"]
        resp = client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": 99999,
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_create_rejects_annual_report_filing(
        self, seeded_filing, db_writer,
    ):
        """ADR-004 amendment §A: EDINET annual_report は extractor 非対応のため
        422 で拒否する (UI から enqueue されないように API 境界で守る)."""
        await db_writer(
            Company(
                id="JP_7203", ticker="7203", name="Toyota Motor",
                market="TSE", accounting_standard="IFRS",
            ),
            Filing(
                id=999,
                company_id="JP_7203",
                source="EDINET",
                filing_type="annual_report",
                period_type="annual", fiscal_year=2024,
                doc_id="S100ABCD",
            ),
        )

        client = seeded_filing["client"]
        resp = client.post(
            "/api/analysis-jobs",
            json={"company_id": "JP_7203", "filing_id": 999},
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert "ADR-004" in detail and "annual_report" in detail

    async def test_create_rejects_non_sec_source(self, seeded_filing, db_writer):
        """`source != 'SEC'` の filing は 422. defense-in-depth として
        filing_type が SEC と被っていても (将来的に EDINET 側で 10-K 風 type を
        入れたケース等) 拒否する."""
        await db_writer(
            Company(
                id="JP_OTHER", ticker="9999", name="Other",
                market="TSE", accounting_standard="IFRS",
            ),
            Filing(
                id=998,
                company_id="JP_OTHER",
                source="EDINET",
                filing_type="10-K",  # type は被るが source が SEC でない
                period_type="annual", fiscal_year=2024,
                doc_id="S100ABCE",
            ),
        )

        client = seeded_filing["client"]
        resp = client.post(
            "/api/analysis-jobs",
            json={"company_id": "JP_OTHER", "filing_id": 998},
        )
        assert resp.status_code == 422, resp.text

    async def test_create_accepts_six_k_filing(self, seeded_filing, db_writer):
        """ADR-004 amendment §A: 6-K は `_FULL_TEXT_FALLBACK` で best-effort
        扱いだが UI / API 候補には含める."""
        from stock_analyze_system.models.filing import Filing

        await db_writer(
            Filing(
                id=997,
                company_id="US_AAPL",
                source="SEC",
                filing_type="6-K",
                period_type="other", fiscal_year=2024,
                accession_no="0000320193-24-006K01",
            ),
        )

        client = seeded_filing["client"]
        resp = client.post(
            "/api/analysis-jobs",
            json={"company_id": "US_AAPL", "filing_id": 997},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["filing_id"] == 997


class TestGetJob:
    def test_get_returns_job_details(self, seeded_filing):
        client = seeded_filing["client"]
        body = {
            "company_id": seeded_filing["company_id"],
            "filing_id": seeded_filing["filing_id"],
        }
        created = client.post("/api/analysis-jobs", json=body).json()
        resp = client.get(f"/api/analysis-jobs/{created['job_id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == created["job_id"]
        assert data["status"] == "pending"

    def test_get_returns_404_for_missing(self, seeded_filing):
        client = seeded_filing["client"]
        resp = client.get("/api/analysis-jobs/99999")
        assert resp.status_code == 404


class TestListJobs:
    def test_list_default_returns_empty(self, seeded_filing):
        client = seeded_filing["client"]
        resp = client.get("/api/analysis-jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_pending(self, seeded_filing):
        client = seeded_filing["client"]
        body = {
            "company_id": seeded_filing["company_id"],
            "filing_id": seeded_filing["filing_id"],
        }
        client.post("/api/analysis-jobs", json=body)
        resp = client.get("/api/analysis-jobs?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"

    def test_list_filters_by_company_filing(self, seeded_filing):
        client = seeded_filing["client"]
        body = {
            "company_id": seeded_filing["company_id"],
            "filing_id": seeded_filing["filing_id"],
        }
        client.post("/api/analysis-jobs", json=body)
        resp = client.get(
            f"/api/analysis-jobs"
            f"?company_id={seeded_filing['company_id']}"
            f"&filing_id={seeded_filing['filing_id']}"
            f"&status=pending,running",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_rejects_zero_limit(self, seeded_filing):
        resp = seeded_filing["client"].get("/api/analysis-jobs?limit=0")
        assert resp.status_code == 422

    def test_list_rejects_negative_limit(self, seeded_filing):
        resp = seeded_filing["client"].get("/api/analysis-jobs?limit=-1")
        assert resp.status_code == 422

    def test_list_rejects_overlimit(self, seeded_filing):
        resp = seeded_filing["client"].get("/api/analysis-jobs?limit=101")
        assert resp.status_code == 422

    def test_list_accepts_max_limit(self, seeded_filing):
        resp = seeded_filing["client"].get("/api/analysis-jobs?limit=100")
        assert resp.status_code == 200


class TestCancelJob:
    def test_delete_cancels_pending(self, seeded_filing):
        client = seeded_filing["client"]
        body = {
            "company_id": seeded_filing["company_id"],
            "filing_id": seeded_filing["filing_id"],
        }
        created = client.post("/api/analysis-jobs", json=body).json()
        resp = client.delete(f"/api/analysis-jobs/{created['job_id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_delete_returns_404_for_missing(self, seeded_filing):
        client = seeded_filing["client"]
        resp = client.delete("/api/analysis-jobs/99999")
        assert resp.status_code == 404


class TestDismissJob:
    async def test_dismiss_marks_dismissed_at(
        self, seeded_filing, web_config,
    ):
        from stock_analyze_system.models.base import (
            create_db_engine, get_session,
        )
        engine = await create_db_engine(web_config.database.path)
        try:
            async with get_session(engine) as s:
                failed = AnalysisJob(
                    company_id=seeded_filing["company_id"],
                    filing_id=seeded_filing["filing_id"],
                    status=JobStatus.FAILED.value,
                )
                s.add(failed)
                await s.flush()
                job_id = failed.id
        finally:
            await engine.dispose()

        client = seeded_filing["client"]
        resp = client.post(f"/api/analysis-jobs/{job_id}/dismiss")
        assert resp.status_code == 200
        assert resp.json()["dismissed_at"] is not None

    def test_dismiss_rejects_pending_with_400(self, seeded_filing):
        client = seeded_filing["client"]
        body = {
            "company_id": seeded_filing["company_id"],
            "filing_id": seeded_filing["filing_id"],
        }
        created = client.post("/api/analysis-jobs", json=body).json()
        resp = client.post(
            f"/api/analysis-jobs/{created['job_id']}/dismiss",
        )
        assert resp.status_code == 400


def test_api_analysis_filing_types_match_adr004_canonical_set():
    """ADR-004 amendment §A: api.py の ANALYSIS_FILING_TYPES が
    `models.enums.ADR004_FILING_TYPES` と一致することを保証する。

    `analysis_jobs.py` の validation も同じ `ADR004_FILING_TYPES` を直接
    import するため定数自体は単一情報源 (`models.enums`)。本 test は
    api.py の list 表現が ADR-004 正本と乖離しないこと (順序や追加漏れ) を検査する。
    """
    from stock_analyze_system.models.enums import ADR004_FILING_TYPES
    from stock_analyze_system.web.routes.api import ANALYSIS_FILING_TYPES

    assert set(ANALYSIS_FILING_TYPES) == ADR004_FILING_TYPES, (
        "api.py ANALYSIS_FILING_TYPES が models.enums.ADR004_FILING_TYPES と "
        "divergence した. 単一情報源は ADR004_FILING_TYPES."
    )
