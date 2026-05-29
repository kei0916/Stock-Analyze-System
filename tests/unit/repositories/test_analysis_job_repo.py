"""AnalysisJobRepository 単体テスト"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository


@pytest.fixture
async def sample_filing(session, sample_company):
    filing = Filing(
        company_id=sample_company.id,
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    )
    session.add(filing)
    await session.flush()
    return filing


@pytest.fixture
async def sample_filing_2(session, sample_company):
    filing = Filing(
        company_id=sample_company.id,
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
        accession_no="0000320193-23-000999",
    )
    session.add(filing)
    await session.flush()
    return filing


class TestAnalysisJobRepoBasics:
    async def test_create_returns_pending_job(self, session, sample_filing):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.company_id == sample_filing.company_id
        assert job.filing_id == sample_filing.id

    async def test_get_returns_job_by_id(self, session, sample_filing):
        repo = AnalysisJobRepository(session)
        created = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        fetched = await repo.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_returns_none_for_missing_id(self, session):
        repo = AnalysisJobRepository(session)
        assert await repo.get(99999) is None

    async def test_find_active_returns_pending(self, session, sample_filing):
        repo = AnalysisJobRepository(session)
        created = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        found = await repo.find_active_by_company_filing(
            sample_filing.company_id, sample_filing.id,
        )
        assert found is not None
        assert found.id == created.id

    async def test_find_active_returns_none_when_completed(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.COMPLETED.value,
        )
        session.add(job)
        await session.flush()

        found = await repo.find_active_by_company_filing(
            sample_filing.company_id, sample_filing.id,
        )
        assert found is None

    async def test_list_filters_by_status(
        self, session, sample_filing, sample_filing_2,
    ):
        repo = AnalysisJobRepository(session)
        await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        running = AnalysisJob(
            company_id=sample_filing_2.company_id,
            filing_id=sample_filing_2.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(running)
        await session.flush()

        pending_only = await repo.list(statuses=[JobStatus.PENDING])
        assert len(pending_only) == 1
        assert pending_only[0].status == JobStatus.PENDING.value

        all_active = await repo.list(
            statuses=[JobStatus.PENDING, JobStatus.RUNNING],
        )
        assert len(all_active) == 2

    async def test_list_filters_by_company_filing(
        self, session, sample_filing, sample_filing_2,
    ):
        repo = AnalysisJobRepository(session)
        await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await repo.create(
            company_id=sample_filing_2.company_id,
            filing_id=sample_filing_2.id,
        )

        only_first = await repo.list(filing_id=sample_filing.id)
        assert len(only_first) == 1
        assert only_first[0].filing_id == sample_filing.id

    async def test_list_filters_by_company_id(
        self, session, sample_filing,
    ):
        """company_id 単独フィルタ: 別会社のジョブは含まれない"""
        from stock_analyze_system.models.company import Company
        other_company = Company(
            id="JP_7203", security_code="7203",
            name="Toyota Motor Corporation",
            market="TSE_PRIME", accounting_standard="IFRS",
        )
        session.add(other_company)
        await session.flush()
        other_filing = Filing(
            company_id=other_company.id,
            source="EDINET", filing_type="annual_report",
            period_type="annual", fiscal_year=2024,
            accession_no="JP-7203-2024",
        )
        session.add(other_filing)
        await session.flush()

        repo = AnalysisJobRepository(session)
        await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await repo.create(
            company_id=other_company.id,
            filing_id=other_filing.id,
        )

        only_aapl = await repo.list(company_id=sample_filing.company_id)
        assert len(only_aapl) == 1
        assert only_aapl[0].company_id == sample_filing.company_id

    async def test_find_active_returns_running(self, session, sample_filing):
        """RUNNING も active として返される"""
        repo = AnalysisJobRepository(session)
        running_job = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(running_job)
        await session.flush()

        found = await repo.find_active_by_company_filing(
            sample_filing.company_id, sample_filing.id,
        )
        assert found is not None
        assert found.status == JobStatus.RUNNING.value

    async def test_list_excludes_dismissed_by_default(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        dismissed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.FAILED.value,
            dismissed_at=datetime.now(timezone.utc),
        )
        session.add(dismissed)
        await session.flush()

        result = await repo.list(statuses=[JobStatus.FAILED])
        assert result == []

        with_dismissed = await repo.list(
            statuses=[JobStatus.FAILED], include_dismissed=True,
        )
        assert len(with_dismissed) == 1


class TestAnalysisJobRepoDequeue:
    async def test_dequeue_next_returns_oldest_pending_and_marks_running(
        self, session, sample_filing, sample_filing_2,
    ):
        repo = AnalysisJobRepository(session)
        first = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await repo.create(
            company_id=sample_filing_2.company_id,
            filing_id=sample_filing_2.id,
        )
        await session.commit()  # commit to make created_at deterministic

        dequeued = await repo.dequeue_next()
        assert dequeued is not None
        assert dequeued.id == first.id
        assert dequeued.status == JobStatus.RUNNING.value
        assert dequeued.started_at is not None

    async def test_dequeue_next_returns_none_when_empty(self, session):
        repo = AnalysisJobRepository(session)
        result = await repo.dequeue_next()
        assert result is None

    async def test_dequeue_next_skips_running(
        self, session, sample_filing,
    ):
        """既に running のジョブは取らない"""
        running = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(running)
        await session.flush()

        repo = AnalysisJobRepository(session)
        result = await repo.dequeue_next()
        assert result is None

    async def test_dequeue_next_atomic_no_double_take(
        self, session, sample_filing,
    ):
        """同じ pending を 2 回 dequeue しても 2 回目は None"""
        repo = AnalysisJobRepository(session)
        await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()

        first = await repo.dequeue_next()
        second = await repo.dequeue_next()

        assert first is not None
        assert second is None


class TestAnalysisJobRepoUpdate:
    async def test_update_status_to_completed(self, session, sample_filing):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()
        completed_at = datetime.now(timezone.utc)
        await repo.update_status(
            job.id, JobStatus.COMPLETED, completed_at=completed_at,
        )

        fetched = await repo.get(job.id)
        assert fetched.status == JobStatus.COMPLETED.value
        assert fetched.completed_at is not None

    async def test_update_status_with_error_details(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()

        await repo.update_status(
            job.id, JobStatus.FAILED,
            error_details={"failed_types": [
                {"type": "mda", "message": "timeout"},
            ]},
        )
        fetched = await repo.get(job.id)
        assert fetched.status == JobStatus.FAILED.value
        assert fetched.error_details["failed_types"][0]["type"] == "mda"

    async def test_update_progress_updates_current_and_total_only(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()

        await repo.update_progress(job.id, current=2)
        fetched = await repo.get(job.id)
        assert fetched.progress_current == 2
        assert fetched.progress_total == 4  # 未指定なら維持

        await repo.update_progress(job.id, total=8)
        fetched = await repo.get(job.id)
        assert fetched.progress_total == 8
        assert fetched.progress_current == 2  # 未指定なら維持

    async def test_set_current_type_updates_only_that_column(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()

        await repo.set_current_type(job.id, "mda")
        fetched = await repo.get(job.id)
        assert fetched.current_analysis_type == "mda"
        assert fetched.progress_current == 0  # 他の列は触らない

    async def test_clear_current_type_sets_column_to_null(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()
        await repo.set_current_type(job.id, "mda")

        await repo.clear_current_type(job.id)
        fetched = await repo.get(job.id)
        assert fetched.current_analysis_type is None

    async def test_update_status_to_terminal_clears_current_type(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()
        await repo.set_current_type(job.id, "mda")

        await repo.update_status(job.id, JobStatus.FAILED)

        fetched = await repo.get(job.id)
        assert fetched.status == JobStatus.FAILED.value
        assert fetched.current_analysis_type is None


class TestAnalysisJobRepoDismissReset:
    async def test_dismiss_marks_dismissed_at(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.FAILED.value,
        )
        session.add(job)
        await session.commit()

        await repo.dismiss(job.id)
        fetched = await repo.get(job.id)
        assert fetched.dismissed_at is not None

    async def test_dismiss_past_for_filing_marks_failed_and_cancelled(
        self, session, sample_filing,
    ):
        """同 filing の failed/cancelled をまとめて dismiss"""
        failed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.FAILED.value,
        )
        cancelled = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.CANCELLED.value,
        )
        completed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.COMPLETED.value,  # completed は対象外
        )
        session.add_all([failed, cancelled, completed])
        await session.commit()

        repo = AnalysisJobRepository(session)
        count = await repo.dismiss_past_for_filing(
            sample_filing.company_id, sample_filing.id,
        )
        assert count == 2

        for job in [failed, cancelled]:
            await session.refresh(job)
            assert job.dismissed_at is not None
        await session.refresh(completed)
        assert completed.dismissed_at is None

    async def test_dismiss_past_for_filing_commits_by_default(
        self, async_engine,
    ):
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        async with session_factory() as session:
            company = Company(
                id="US_AAPL_DIRECT",
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
                accession_no="0000320193-24-000777",
            )
            session.add(filing)
            await session.flush()
            failed = AnalysisJob(
                company_id=company.id,
                filing_id=filing.id,
                status=JobStatus.FAILED.value,
            )
            session.add(failed)
            await session.commit()
            failed_id = failed.id
            filing_id = filing.id
            company_id = company.id

            repo = AnalysisJobRepository(session)
            assert await repo.dismiss_past_for_filing(company_id, filing_id) == 1

        async with session_factory() as session:
            persisted = await session.get(AnalysisJob, failed_id)
            assert persisted is not None
            assert persisted.dismissed_at is not None

    async def test_reset_running_to_failed_records_reason_and_clears_current_type(
        self, session, sample_filing,
    ):
        running = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.RUNNING.value,
            current_analysis_type="mda",
        )
        session.add(running)
        await session.commit()

        repo = AnalysisJobRepository(session)
        count = await repo.reset_running_to_failed(
            reason="Server restarted while running",
        )
        assert count == 1

        await session.refresh(running)
        assert running.status == JobStatus.FAILED.value
        assert running.error_details == {
            "reason": "Server restarted while running",
        }
        assert running.completed_at is not None
        assert running.current_analysis_type is None
