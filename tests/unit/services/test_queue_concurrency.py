"""Concurrency properties for the analysis queue."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.base import create_db_engine
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository
from stock_analyze_system.services.analysis_queue import AnalysisQueueService


@pytest.fixture
async def concurrency_engine(tmp_path):
    """File-backed SQLite gives concurrent sessions separate connections."""
    engine = await create_db_engine(str(tmp_path / "queue-concurrency.db"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(concurrency_engine):
    return async_sessionmaker(concurrency_engine, expire_on_commit=False)


@pytest.fixture
def queue_service(session_factory):
    return AnalysisQueueService(session_factory=session_factory)


async def _seed_company(session_factory, company_id: str = "US_AAPL") -> str:
    async with session_factory() as session:
        company = Company(
            id=company_id,
            ticker="AAPL",
            name="Apple Inc.",
            market="NASDAQ",
            accounting_standard="US-GAAP",
        )
        session.add(company)
        await session.commit()
        return company.id


async def _seed_filings(
    session_factory,
    company_id: str,
    count: int,
) -> list[int]:
    async with session_factory() as session:
        filings = [
            Filing(
                company_id=company_id,
                source="SEC",
                filing_type="10-K",
                period_type="annual",
                fiscal_year=2024 - i,
                accession_no=f"0000320193-24-{i:06d}",
            )
            for i in range(count)
        ]
        session.add_all(filings)
        await session.commit()
        return [filing.id for filing in filings]


async def _pending_jobs(session_factory) -> list[AnalysisJob]:
    async with session_factory() as session:
        result = await session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.status == JobStatus.PENDING.value)
            .order_by(AnalysisJob.id),
        )
        return list(result.scalars().all())


async def test_p01_concurrent_enqueue_same_filing_is_idempotent(
    session_factory,
):
    company_id = await _seed_company(session_factory)
    filing_id = (await _seed_filings(session_factory, company_id, 1))[0]
    barrier = asyncio.Event()

    async def enqueue_from_distinct_service():
        await barrier.wait()
        return await AnalysisQueueService(
            session_factory=session_factory,
        ).enqueue(company_id, filing_id)

    tasks = [asyncio.create_task(enqueue_from_distinct_service()) for _ in range(20)]
    barrier.set()

    results = await asyncio.gather(*tasks)

    job_ids = {job.id for job, _is_new in results}
    pending = await _pending_jobs(session_factory)

    assert len(job_ids) == 1
    assert len(pending) == 1
    assert pending[0].id == next(iter(job_ids))
    assert pending[0].company_id == company_id
    assert pending[0].filing_id == filing_id


async def test_p02_concurrent_enqueue_two_filings_creates_one_job_per_filing(
    session_factory,
):
    company_id = await _seed_company(session_factory)
    first_filing_id, second_filing_id = await _seed_filings(
        session_factory,
        company_id,
        2,
    )

    barrier = asyncio.Event()

    async def enqueue_from_distinct_service(filing_id: int):
        await barrier.wait()
        return await AnalysisQueueService(
            session_factory=session_factory,
        ).enqueue(company_id, filing_id)

    tasks = [
        *[
            asyncio.create_task(enqueue_from_distinct_service(first_filing_id))
            for _ in range(10)
        ],
        *[
            asyncio.create_task(enqueue_from_distinct_service(second_filing_id))
            for _ in range(10)
        ],
    ]
    barrier.set()
    await asyncio.gather(*tasks)

    pending = await _pending_jobs(session_factory)

    assert len(pending) == 2
    assert {job.filing_id for job in pending} == {
        first_filing_id,
        second_filing_id,
    }


async def test_p03_dequeue_cancel_race_converges_to_consistent_status(
    queue_service,
    session_factory,
):
    company_id = await _seed_company(session_factory)
    filing_id = (await _seed_filings(session_factory, company_id, 1))[0]
    job, _is_new = await queue_service.enqueue(company_id, filing_id)

    async def dequeue_once():
        async with session_factory() as session:
            return await AnalysisJobRepository(session).dequeue_next()

    dequeued, cancelled = await asyncio.gather(
        dequeue_once(),
        queue_service.cancel(job.id),
    )

    async with session_factory() as session:
        final = await session.get(AnalysisJob, job.id)
        total = await session.scalar(select(func.count(AnalysisJob.id)))

    assert total == 1
    assert final is not None
    assert final.status in {
        JobStatus.RUNNING.value,
        JobStatus.CANCELLED.value,
    }
    if final.status == JobStatus.RUNNING.value:
        assert final.started_at is not None
        assert final.completed_at is None
        assert dequeued is not None
        assert dequeued.id == job.id
        assert cancelled is not None
        assert cancelled.id == job.id
        assert cancelled.status == JobStatus.RUNNING.value
        assert cancelled.completed_at is None
    else:
        assert final.completed_at is not None
        assert dequeued is None
        assert cancelled is not None
        assert cancelled.id == job.id
        assert cancelled.status == JobStatus.CANCELLED.value
        assert cancelled.completed_at is not None


async def test_p04_two_dequeue_loops_do_not_pick_same_job(
    queue_service,
    session_factory,
):
    company_id = await _seed_company(session_factory)
    filing_ids = await _seed_filings(session_factory, company_id, 100)
    await asyncio.gather(
        *[
            queue_service.enqueue(company_id, filing_id)
            for filing_id in filing_ids
        ],
    )

    async def dequeue_until_empty() -> list[int]:
        picked: list[int] = []
        while True:
            async with session_factory() as session:
                job = await AnalysisJobRepository(session).dequeue_next()
            if job is None:
                return picked
            picked.append(job.id)

    first, second = await asyncio.gather(
        dequeue_until_empty(),
        dequeue_until_empty(),
    )
    picked_ids = first + second

    assert len(picked_ids) == 100
    assert len(set(picked_ids)) == 100

    async with session_factory() as session:
        running_count = await session.scalar(
            select(func.count(AnalysisJob.id)).where(
                AnalysisJob.status == JobStatus.RUNNING.value,
            ),
        )
    assert running_count == 100
