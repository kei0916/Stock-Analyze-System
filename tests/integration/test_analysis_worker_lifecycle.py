"""Lifecycle integration tests for AnalysisWorker."""
from __future__ import annotations

import asyncio
from datetime import datetime
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.base import create_db_engine
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.services.analysis_queue import AnalysisQueueService
from stock_analyze_system.services.analysis_worker import AnalysisWorker

pytestmark = pytest.mark.integration


SUCCESS_EVENTS = [
    {"event": "started", "total": 1},
    {"event": "phase", "index": 0, "analysis_type": "business"},
    {"event": "done", "index": 0, "analysis_type": "business"},
    {"event": "complete"},
]


@pytest.fixture
async def lifecycle_engine(tmp_path):
    engine = await create_db_engine(str(tmp_path / "lifecycle.db"))
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(lifecycle_engine):
    return async_sessionmaker(lifecycle_engine, expire_on_commit=False)


@pytest.fixture
def config():
    return AppConfig()


@pytest.fixture
def fake_clients():
    return MagicMock()


@pytest.fixture
def worker(session_factory, config, fake_clients):
    return AnalysisWorker(session_factory, config, fake_clients, poll_interval=0.05)


async def seed_filings(session_factory, count: int) -> list[Filing]:
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

        filings = [
            Filing(
                company_id=company.id,
                source="SEC",
                filing_type="10-K",
                period_type="annual",
                fiscal_year=2020 + idx,
                accession_no=f"0000320193-{idx:06d}",
            )
            for idx in range(count)
        ]
        session.add_all(filings)
        await session.commit()
        return filings


async def seed_jobs(
    session_factory,
    *,
    status: JobStatus,
    count: int,
    filing_idx: int = 0,
    filings: list[Filing] | None = None,
    created_at: datetime | None = None,
) -> list[AnalysisJob]:
    if filings is None:
        filings = await seed_filings(session_factory, max(count, filing_idx + 1))

    async with session_factory() as session:
        jobs = []
        for offset in range(count):
            filing = filings[filing_idx + offset]
            job = AnalysisJob(
                company_id=filing.company_id,
                filing_id=filing.id,
                status=status.value,
                created_at=created_at,
            )
            session.add(job)
            jobs.append(job)
            await session.flush()
            if created_at is None:
                await asyncio.sleep(0.001)
        await session.commit()
        return jobs


async def get_jobs(session_factory) -> list[AnalysisJob]:
    async with session_factory() as session:
        result = await session.execute(select(AnalysisJob).order_by(AnalysisJob.id))
        return list(result.scalars().all())


async def wait_until(condition, *, timeout: float = 2.0, interval: float = 0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await condition()
        if result:
            return result
        await asyncio.sleep(interval)
    raise AssertionError("condition was not met before timeout")


class FakeFilingService:
    def __init__(self, filings: list[Filing]):
        self._filings = {filing.id: filing for filing in filings}

    async def get_filing_by_id(self, filing_id: int) -> Filing | None:
        return self._filings.get(filing_id)


class FakeRagService:
    def __init__(self, events_by_filing_id):
        self._events_by_filing_id = events_by_filing_id
        self.seen_filing_ids = []
        self.sleep_started = asyncio.Event()

    async def preflight(self) -> dict:
        # ADR-004: worker calls preflight before each job; fakes need to satisfy
        # the contract or the worker fails before reaching run_full_analysis_stream.
        return {"status": "ok", "model": "fake", "response_head": "ok"}

    async def run_full_analysis_stream(self, filing):
        self.seen_filing_ids.append(filing.id)
        events = self._events_by_filing_id.get(filing.id, SUCCESS_EVENTS)
        for event in events:
            if event.get("event") == "_sleep":
                self.sleep_started.set()
                await asyncio.sleep(event["seconds"])
                continue
            yield event


def install_fake_setup(monkeypatch, *, filings: list[Filing], rag_service):
    container = SimpleNamespace(
        rag_service=rag_service,
        filing_service=FakeFilingService(filings),
    )

    async def fake_setup_services(session, config, *, clients=None):
        return container

    monkeypatch.setattr(
        "stock_analyze_system.services.analysis_worker.setup_services",
        fake_setup_services,
    )
    return container


async def run_worker_until_complete(
    worker,
    session_factory,
    expected_completed: int,
    *,
    timeout: float = 3.0,
):
    task = asyncio.create_task(worker.run_forever())
    try:
        await wait_until(
            lambda: count_status(session_factory, JobStatus.COMPLETED, expected_completed),
            timeout=timeout,
        )
    finally:
        worker.request_shutdown()
        await asyncio.wait_for(task, timeout=1.0)


async def count_status(session_factory, status: JobStatus, expected: int) -> bool:
    jobs = await get_jobs(session_factory)
    return sum(job.status == status.value for job in jobs) == expected


async def test_run_forever_processes_queued_jobs_in_order(
    session_factory,
    monkeypatch,
    config,
    fake_clients,
):
    filings = await seed_filings(session_factory, 3)
    shared_created_at = datetime(2026, 1, 1)
    await seed_jobs(
        session_factory,
        status=JobStatus.PENDING,
        count=3,
        filings=filings,
        created_at=shared_created_at,
    )
    rag_service = FakeRagService({
        filing.id: SUCCESS_EVENTS
        for filing in filings
    })
    install_fake_setup(monkeypatch, filings=filings, rag_service=rag_service)
    worker = AnalysisWorker(
        session_factory,
        config,
        fake_clients,
        poll_interval=5.0,
    )

    started_at = time.monotonic()
    await run_worker_until_complete(
        worker,
        session_factory,
        expected_completed=3,
        timeout=1.0,
    )

    jobs = await get_jobs(session_factory)
    assert {job.created_at for job in jobs} == {shared_created_at}
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value] * 3
    assert rag_service.seen_filing_ids == [filing.id for filing in filings]
    assert time.monotonic() - started_at < 1.0


async def test_run_forever_resets_stale_running_at_startup(
    session_factory,
    worker,
):
    await seed_jobs(session_factory, status=JobStatus.RUNNING, count=2)
    worker.request_shutdown()

    await worker.run_forever()

    jobs = await get_jobs(session_factory)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value] * 2
    assert all(
        job.error_details["reason"] == "Worker restarted while running"
        for job in jobs
    )


async def test_run_forever_sigterm_during_job_finishes_first(
    session_factory,
    worker,
    monkeypatch,
):
    filings = await seed_filings(session_factory, 2)
    await seed_jobs(
        session_factory,
        status=JobStatus.PENDING,
        count=2,
        filings=filings,
    )
    rag_service = FakeRagService({
        filings[0].id: [
            {"event": "started", "total": 1},
            {"event": "_sleep", "seconds": 0.5},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {"event": "done", "index": 0, "analysis_type": "business"},
            {"event": "complete"},
        ],
        filings[1].id: SUCCESS_EVENTS,
    })
    install_fake_setup(monkeypatch, filings=filings, rag_service=rag_service)
    task = asyncio.create_task(worker.run_forever())

    try:
        await asyncio.wait_for(rag_service.sleep_started.wait(), timeout=1.0)
        worker.request_shutdown()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        worker.request_shutdown()
        if not task.done():
            await asyncio.wait_for(task, timeout=1.0)

    jobs = await get_jobs(session_factory)
    assert [job.status for job in jobs] == [
        JobStatus.COMPLETED.value,
        JobStatus.PENDING.value,
    ]


async def test_run_forever_sigterm_when_idle_exits_quickly(
    session_factory,
    config,
    fake_clients,
):
    worker = AnalysisWorker(
        session_factory,
        config,
        fake_clients,
        poll_interval=5.0,
    )
    task = asyncio.create_task(worker.run_forever())

    try:
        await asyncio.sleep(0.05)
        started_at = time.monotonic()
        worker.request_shutdown()
        await asyncio.wait_for(task, timeout=1.0)
    finally:
        worker.request_shutdown()
        if not task.done():
            await asyncio.wait_for(task, timeout=1.0)

    assert time.monotonic() - started_at < 0.5


async def test_second_worker_fails_before_resetting_live_running_job(
    session_factory,
    config,
    fake_clients,
    monkeypatch,
):
    filings = await seed_filings(session_factory, 1)
    jobs = await seed_jobs(
        session_factory,
        status=JobStatus.PENDING,
        count=1,
        filings=filings,
    )
    rag_service = FakeRagService({
        filings[0].id: [
            {"event": "started", "total": 1},
            {"event": "_sleep", "seconds": 0.5},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {"event": "done", "index": 0, "analysis_type": "business"},
            {"event": "complete"},
        ],
    })
    install_fake_setup(monkeypatch, filings=filings, rag_service=rag_service)
    worker1 = AnalysisWorker(
        session_factory,
        config,
        fake_clients,
        poll_interval=5.0,
    )
    worker2 = AnalysisWorker(
        session_factory,
        config,
        fake_clients,
        poll_interval=5.0,
    )
    task = asyncio.create_task(worker1.run_forever())

    try:
        await asyncio.wait_for(rag_service.sleep_started.wait(), timeout=1.0)
        worker2.request_shutdown()
        with pytest.raises(RuntimeError, match="Another analysis worker"):
            await worker2.run_forever()

        jobs_after_second_start = await get_jobs(session_factory)
        assert jobs_after_second_start[0].id == jobs[0].id
        assert jobs_after_second_start[0].status == JobStatus.RUNNING.value
    finally:
        worker1.request_shutdown()
        await asyncio.wait_for(task, timeout=2.0)


async def test_run_forever_picks_up_new_job_after_idle(
    session_factory,
    worker,
    monkeypatch,
    config,
    fake_clients,
):
    filings = await seed_filings(session_factory, 1)
    rag_service = FakeRagService({filings[0].id: SUCCESS_EVENTS})
    install_fake_setup(monkeypatch, filings=filings, rag_service=rag_service)
    queue = AnalysisQueueService(session_factory)
    task = asyncio.create_task(worker.run_forever())

    try:
        await asyncio.sleep(0.1)
        await queue.enqueue(filings[0].company_id, filings[0].id)
        await wait_until(
            lambda: count_status(session_factory, JobStatus.COMPLETED, 1),
            timeout=2.0,
        )
    finally:
        worker.request_shutdown()
        await asyncio.wait_for(task, timeout=1.0)

    jobs = await get_jobs(session_factory)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value]


async def test_worker_does_not_block_concurrent_db_reads(
    session_factory,
    worker,
    monkeypatch,
    config,
    fake_clients,
):
    filings = await seed_filings(session_factory, 1)
    await seed_jobs(
        session_factory,
        status=JobStatus.PENDING,
        count=1,
        filings=filings,
    )
    rag_service = FakeRagService({
        filings[0].id: [
            {"event": "started", "total": 1},
            {"event": "_sleep", "seconds": 2.0},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {"event": "done", "index": 0, "analysis_type": "business"},
            {"event": "complete"},
        ],
    })
    install_fake_setup(monkeypatch, filings=filings, rag_service=rag_service)
    queue = AnalysisQueueService(session_factory)
    task = asyncio.create_task(worker.run_forever())

    try:
        await asyncio.wait_for(rag_service.sleep_started.wait(), timeout=1.0)
        started_at = time.monotonic()
        results = await asyncio.wait_for(
            asyncio.gather(*[
                queue.list_jobs(limit=20)
                for _ in range(10)
            ]),
            timeout=0.5,
        )
        elapsed = time.monotonic() - started_at
        assert elapsed < 0.5
        assert all(isinstance(result, list) for result in results)

        await wait_until(
            lambda: count_status(session_factory, JobStatus.COMPLETED, 1),
            timeout=3.0,
        )
    finally:
        worker.request_shutdown()
        await asyncio.wait_for(task, timeout=1.0)
