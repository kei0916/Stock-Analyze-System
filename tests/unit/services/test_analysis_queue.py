"""AnalysisQueueService 単体テスト"""
from __future__ import annotations

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository
from stock_analyze_system.services.analysis_queue import AnalysisQueueService


def test_analysis_queue_service_can_be_instantiated():
    svc = AnalysisQueueService(session_factory=lambda: None)
    assert svc is not None


def test_analysis_queue_service_has_no_worker_methods():
    svc = AnalysisQueueService(session_factory=lambda: None)
    for name in (
        "_config",
        "_clients",
        "start",
        "stop",
        "_worker_task",
        "_shutdown_event",
        "_wakeup_event",
        "_running_tasks",
        "_worker_loop",
        "_dequeue_next",
        "_run_job",
        "_execute_with_status",
    ):
        assert not hasattr(svc, name)


@pytest.fixture
async def session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def seed_company_and_filing(session_factory):
    async with session_factory() as s:
        company = Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc.",
            market="NASDAQ", accounting_standard="US-GAAP",
        )
        s.add(company)
        await s.flush()
        filing = Filing(
            company_id=company.id,
            source="SEC", filing_type="10-K",
            period_type="annual", fiscal_year=2024,
            accession_no="0000320193-24-000123",
        )
        s.add(filing)
        await s.commit()
        return company.id, filing.id


@pytest.fixture
def queue_service(session_factory):
    return AnalysisQueueService(session_factory=session_factory)


class TestEnqueue:
    async def test_enqueue_creates_pending_job(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        job, _is_new = await queue_service.enqueue(company_id, filing_id)
        assert job.id is not None
        assert job.status == JobStatus.PENDING.value

        async with session_factory() as s:
            fetched = await s.get(AnalysisJob, job.id)
            assert fetched is not None

    async def test_enqueue_returns_existing_for_duplicate_pending(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        first, _is_new = await queue_service.enqueue(company_id, filing_id)
        second, _is_new = await queue_service.enqueue(company_id, filing_id)
        assert first.id == second.id

    async def test_enqueue_dismisses_past_failed(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            failed = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.FAILED.value,
            )
            s.add(failed)
            await s.commit()
            failed_id = failed.id

        await queue_service.enqueue(company_id, filing_id)

        async with session_factory() as s:
            updated = await s.get(AnalysisJob, failed_id)
            assert updated.dismissed_at is not None

    async def test_enqueue_dismiss_rollback_when_create_fails(
        self,
        monkeypatch,
        queue_service,
        seed_company_and_filing,
        session_factory,
    ):
        """dismiss + create は 1 transaction。create 失敗時は過去 failure を残す."""
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            failed = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.FAILED.value,
            )
            s.add(failed)
            await s.commit()
            failed_id = failed.id

        async def fail_create(self, *, company_id, filing_id):
            raise IntegrityError("insert analysis_jobs", {}, RuntimeError("boom"))

        monkeypatch.setattr(AnalysisJobRepository, "create", fail_create)

        with pytest.raises(IntegrityError):
            await queue_service.enqueue(company_id, filing_id)

        async with session_factory() as s:
            updated = await s.get(AnalysisJob, failed_id)
            assert updated.dismissed_at is None


class TestCancelDismiss:
    async def test_cancel_pending_marks_cancelled(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        job, _is_new = await queue_service.enqueue(company_id, filing_id)
        cancelled = await queue_service.cancel(job.id)

        assert cancelled is not None
        assert cancelled.status == JobStatus.CANCELLED.value
        assert cancelled.completed_at is not None

    async def test_cancel_running_is_noop(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            running = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.RUNNING.value,
            )
            s.add(running)
            await s.commit()
            job_id = running.id

        result = await queue_service.cancel(job_id)

        assert result is not None
        assert result.id == job_id
        assert result.status == JobStatus.RUNNING.value
        assert result.completed_at is None

        async with session_factory() as s:
            fetched = await s.get(AnalysisJob, job_id)
        assert fetched.status == JobStatus.RUNNING.value
        assert fetched.completed_at is None

    async def test_cancel_returns_latest_when_pending_job_becomes_running(
        self,
        monkeypatch,
        queue_service,
        seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        job, _is_new = await queue_service.enqueue(company_id, filing_id)

        async def fake_cancel_pending(self, job_id, *, completed_at):
            stmt = (
                update(AnalysisJob)
                .where(AnalysisJob.id == job_id)
                .values(status=JobStatus.RUNNING.value)
            )
            await self._session.execute(stmt)
            await self._session.commit()
            return False

        monkeypatch.setattr(
            AnalysisJobRepository,
            "cancel_pending",
            fake_cancel_pending,
        )

        result = await queue_service.cancel(job.id)

        assert result is not None
        assert result.status == JobStatus.RUNNING.value
        assert result.completed_at is None

        latest = await queue_service.get_status(job.id)
        assert latest is not None
        assert latest.status == JobStatus.RUNNING.value
        assert latest.completed_at is None

    async def test_cancel_returns_none_for_missing(self, queue_service):
        result = await queue_service.cancel(99999)
        assert result is None

    async def test_dismiss_marks_dismissed_at(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            failed = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.FAILED.value,
            )
            s.add(failed)
            await s.commit()
            job_id = failed.id

        result = await queue_service.dismiss(job_id)
        assert result is not None
        assert result.dismissed_at is not None

    async def test_dismiss_rejects_running(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        """pending/running の dismiss は ValueError"""
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            running = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.RUNNING.value,
            )
            s.add(running)
            await s.commit()
            job_id = running.id

        with pytest.raises(ValueError):
            await queue_service.dismiss(job_id)

    async def test_get_status_returns_job(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        job, _is_new = await queue_service.enqueue(company_id, filing_id)
        fetched = await queue_service.get_status(job.id)
        assert fetched is not None
        assert fetched.id == job.id

    async def test_list_jobs_passes_filters(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        await queue_service.enqueue(company_id, filing_id)
        result = await queue_service.list_jobs(
            statuses=[JobStatus.PENDING],
        )
        assert len(result) == 1
