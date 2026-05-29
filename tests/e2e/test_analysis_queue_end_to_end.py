"""End-to-end coverage for the HTTP analysis queue and worker."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.analysis_job import JobStatus
from stock_analyze_system.models.base import create_db_engine
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.services.analysis_worker import AnalysisWorker
from stock_analyze_system.web.app import create_app


pytestmark = pytest.mark.integration


SUCCESS_EVENTS = [
    {"event": "started", "total": 4},
    {"event": "phase", "index": 0, "total": 4, "analysis_type": "business"},
    {"event": "done", "index": 0, "analysis_type": "business"},
    {"event": "phase", "index": 1, "total": 4, "analysis_type": "risks"},
    {"event": "done", "index": 1, "analysis_type": "risks"},
    {"event": "phase", "index": 2, "total": 4, "analysis_type": "mda"},
    {"event": "done", "index": 2, "analysis_type": "mda"},
    {"event": "phase", "index": 3, "total": 4, "analysis_type": "outlook"},
    {"event": "done", "index": 3, "analysis_type": "outlook"},
    {"event": "complete"},
]


class FakeFilingService:
    def __init__(self, filing: Filing) -> None:
        self._filing = filing

    async def get_filing_by_id(self, filing_id: int) -> Filing | None:
        if filing_id == self._filing.id:
            return self._filing
        return None


class FakeRagService:
    def __init__(self, events: list[dict]) -> None:
        self._events = events

    async def preflight(self) -> dict:
        return {
            "status": "ok",
            "model": "test-model",
            "response_head": '{"ok": 1}',
            "diagnostic": {},
        }

    async def run_full_analysis_stream(self, filing):  # noqa: ARG002
        for event in self._events:
            if event.get("event") == "_sleep":
                await asyncio.sleep(event["seconds"])
            else:
                yield event


@pytest.fixture
async def e2e_setup(tmp_path, monkeypatch):
    config = AppConfig()
    config.web.session_secret = "test-secret-for-testing-please-32+"
    config.web.password = "test-password"
    config.database.path = str(tmp_path / "analysis-e2e.db")
    config.pageindex.enabled = False

    engine = await create_db_engine(config.database.path)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        company = Company(
            id="US_AAPL",
            ticker="AAPL",
            name="Apple Inc.",
            market="NASDAQ",
            accounting_standard="US-GAAP",
        )
        session.add(company)
        await session.flush()
        filing = Filing(
            company_id=company.id,
            source="SEC",
            filing_type="10-K",
            period_type="annual",
            fiscal_year=2024,
            accession_no="E2E-1",
        )
        session.add(filing)
        await session.commit()
        filing_id = filing.id

    async def fetch_filing() -> Filing:
        async with session_factory() as session:
            filing = await session.get(Filing, filing_id)
            assert filing is not None
            return filing

    async def install_rag(events: list[dict]) -> None:
        filing = await fetch_filing()
        container = SimpleNamespace(
            rag_service=FakeRagService(events),
            filing_service=FakeFilingService(filing),
        )

        async def fake_setup_services(session, config, *, clients=None):  # noqa: ARG001
            return container

        monkeypatch.setattr(
            "stock_analyze_system.services.analysis_worker.setup_services",
            fake_setup_services,
        )

    yield SimpleNamespace(
        config=config,
        session_factory=session_factory,
        filing_id=filing_id,
        install_rag=install_rag,
    )

    await engine.dispose()


async def wait_for_http_status(client: TestClient, job_id: int, status: str) -> dict:
    deadline = time.monotonic() + 5.0
    latest: dict | None = None
    while time.monotonic() < deadline:
        await asyncio.sleep(0.05)
        response = client.get(f"/api/analysis-jobs/{job_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] == status:
            return latest
    raise AssertionError(f"job {job_id} did not reach {status}; latest={latest}")


async def test_full_lifecycle_via_http(e2e_setup):
    await e2e_setup.install_rag(SUCCESS_EVENTS)
    worker = AnalysisWorker(
        e2e_setup.session_factory,
        e2e_setup.config,
        MagicMock(),
        poll_interval=0.05,
    )
    worker_task = asyncio.create_task(worker.run_forever())

    try:
        app = create_app(e2e_setup.config)
        with TestClient(app) as client:
            login = client.post(
                "/login",
                data={"password": "test-password"},
                follow_redirects=False,
            )
            assert login.status_code == 303
            response = client.post(
                "/api/analysis-jobs",
                json={"company_id": "US_AAPL", "filing_id": e2e_setup.filing_id},
            )
            assert response.status_code == 201

            completed = await wait_for_http_status(
                client,
                response.json()["job_id"],
                JobStatus.COMPLETED.value,
            )
            assert completed["progress_current"] == 4
            assert completed["progress_total"] == 4
            assert completed["current_analysis_type"] is None
    finally:
        worker.request_shutdown()
        await asyncio.wait_for(worker_task, timeout=5.0)


async def test_pending_job_can_be_cancelled_before_worker_starts(e2e_setup):
    app = create_app(e2e_setup.config)
    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"password": "test-password"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        response = client.post(
            "/api/analysis-jobs",
            json={"company_id": "US_AAPL", "filing_id": e2e_setup.filing_id},
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        cancel = client.delete(f"/api/analysis-jobs/{job_id}")

        assert cancel.status_code == 200
        assert cancel.json()["status"] == JobStatus.CANCELLED.value


async def test_failed_job_retains_error_details(e2e_setup):
    failed_events = [
        {"event": "started", "total": 4},
        {"event": "phase", "index": 0, "total": 4, "analysis_type": "business"},
        {"event": "error", "index": 0, "analysis_type": "business", "message": "boom"},
        {"event": "phase", "index": 1, "total": 4, "analysis_type": "risks"},
        {"event": "error", "index": 1, "analysis_type": "risks", "message": "boom"},
        {"event": "phase", "index": 2, "total": 4, "analysis_type": "mda"},
        {"event": "error", "index": 2, "analysis_type": "mda", "message": "boom"},
        {"event": "phase", "index": 3, "total": 4, "analysis_type": "outlook"},
        {"event": "error", "index": 3, "analysis_type": "outlook", "message": "boom"},
        {"event": "complete"},
    ]
    await e2e_setup.install_rag(failed_events)
    worker = AnalysisWorker(
        e2e_setup.session_factory,
        e2e_setup.config,
        MagicMock(),
        poll_interval=0.05,
    )
    worker_task = asyncio.create_task(worker.run_forever())

    try:
        app = create_app(e2e_setup.config)
        with TestClient(app) as client:
            login = client.post(
                "/login",
                data={"password": "test-password"},
                follow_redirects=False,
            )
            assert login.status_code == 303
            response = client.post(
                "/api/analysis-jobs",
                json={"company_id": "US_AAPL", "filing_id": e2e_setup.filing_id},
            )
            assert response.status_code == 201

            failed = await wait_for_http_status(
                client,
                response.json()["job_id"],
                JobStatus.FAILED.value,
            )

        assert [item["type"] for item in failed["error_details"]["failed_types"]] == [
            "business",
            "risks",
            "mda",
            "outlook",
        ]
    finally:
        worker.request_shutdown()
        await asyncio.wait_for(worker_task, timeout=5.0)
