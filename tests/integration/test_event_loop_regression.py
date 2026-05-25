"""Regression tests for web responsiveness during background analysis."""
from __future__ import annotations

import asyncio
import ast
import inspect
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.base import create_db_engine
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.services.analysis_worker import AnalysisWorker
from stock_analyze_system.web.app import create_app


pytestmark = pytest.mark.integration


def test_pageindex_service_does_not_call_sync_page_index_main():
    from stock_analyze_system.services.pageindex import service as pageindex_service

    source = inspect.getsource(pageindex_service)
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            violations.extend(
                alias.name
                for alias in node.names
                if alias.name == "page_index_main"
            )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "page_index_main":
                violations.append(func.id)
            elif isinstance(func, ast.Attribute) and func.attr == "page_index_main":
                violations.append(func.attr)

    assert violations == []


async def test_web_remains_responsive_while_worker_busy(tmp_path, monkeypatch):
    config = AppConfig()
    config.web.session_secret = "test-secret-for-testing-please-32+"
    config.web.password = "test-password"
    config.database.path = str(tmp_path / "event-loop-regression.db")
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
            accession_no="RG-1",
        )
        session.add(filing)
        await session.flush()
        session.add(AnalysisJob(
            company_id=company.id,
            filing_id=filing.id,
            status=JobStatus.PENDING.value,
        ))
        await session.commit()
        filing_id = filing.id

    async with session_factory() as session:
        filing = await session.get(Filing, filing_id)
        assert filing is not None

    worker_busy = threading.Event()

    class LongRagService:
        async def preflight(self):
            # ADR-004: worker invokes preflight before each job.
            return {"status": "ok", "model": "fake", "response_head": "ok"}

        async def run_full_analysis_stream(self, filing):  # noqa: ARG002
            yield {"event": "started", "total": 4}
            for index, analysis_type in enumerate(["business", "risks", "mda", "outlook"]):
                yield {
                    "event": "phase",
                    "index": index,
                    "total": 4,
                    "analysis_type": analysis_type,
                }
                worker_busy.set()
                time.sleep(0.3)
                yield {"event": "done", "index": index, "analysis_type": analysis_type}
            yield {"event": "complete"}

    class FilingService:
        async def get_filing_by_id(self, requested_filing_id: int) -> Filing | None:
            if requested_filing_id == filing_id:
                return filing
            return None

    async def fake_setup_services(session, config, *, clients=None):  # noqa: ARG001
        return SimpleNamespace(
            rag_service=LongRagService(),
            filing_service=FilingService(),
        )

    monkeypatch.setattr(
        "stock_analyze_system.services.analysis_worker.setup_services",
        fake_setup_services,
    )

    worker = AnalysisWorker(
        session_factory,
        config,
        MagicMock(),
        poll_interval=0.05,
    )
    loop_ready = threading.Event()
    loop_holder: dict[str, asyncio.AbstractEventLoop] = {}
    worker_error: list[BaseException] = []

    def run_worker_thread() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop_holder["loop"] = loop
        loop_ready.set()
        try:
            loop.run_until_complete(worker.run_forever())
        except BaseException as exc:  # pragma: no cover - re-raised in test thread
            worker_error.append(exc)
        finally:
            loop.close()

    worker_thread = threading.Thread(target=run_worker_thread, daemon=True)
    worker_thread.start()
    assert loop_ready.wait(timeout=2.0)

    try:
        assert await asyncio.to_thread(worker_busy.wait, 2.0)
        app = create_app(config)
        latencies: list[float] = []
        with TestClient(app) as client:
            login = client.post(
                "/login",
                data={"password": "test-password"},
                follow_redirects=False,
            )
            assert login.status_code == 303
            for _ in range(50):
                started_at = time.perf_counter()
                response = client.get("/")
                latencies.append(time.perf_counter() - started_at)
                assert response.status_code == 200

        latencies.sort()
        p99 = latencies[int(0.99 * len(latencies)) - 1]
        assert p99 < 0.3, f"p99 latency {p99:.3f}s exceeds 300ms budget"
    finally:
        loop = loop_holder.get("loop")
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(worker.request_shutdown)
        worker_thread.join(timeout=5.0)
        await engine.dispose()
    assert not worker_thread.is_alive()
    assert worker_error == []
