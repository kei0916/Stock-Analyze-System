"""AnalysisJob モデル単体テスト"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES


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


class TestJobStatus:
    def test_enum_values(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"


class TestAnalysisJobModel:
    async def test_create_with_defaults(self, session, sample_filing):
        job = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        session.add(job)
        await session.flush()

        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.progress_current == 0
        assert job.progress_total == len(ANALYSIS_TYPE_NAMES)
        assert job.current_analysis_type is None
        assert job.error_details is None
        assert job.created_at is not None
        assert job.started_at is None
        assert job.completed_at is None
        assert job.dismissed_at is None

    async def test_partial_unique_index_blocks_duplicate_pending(
        self, session, sample_filing,
    ):
        """同 (company_id, filing_id) で pending 2 件は不可"""
        job1 = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.PENDING.value,
        )
        session.add(job1)
        await session.flush()

        job2 = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.PENDING.value,
        )
        session.add(job2)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_partial_unique_index_allows_completed_plus_pending(
        self, session, sample_filing,
    ):
        """completed が既存でも、新しい pending は作成できる"""
        completed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.COMPLETED.value,
        )
        session.add(completed)
        await session.flush()

        new_pending = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.PENDING.value,
        )
        session.add(new_pending)
        await session.flush()

        result = await session.execute(
            select(AnalysisJob).where(
                AnalysisJob.company_id == sample_filing.company_id,
            )
        )
        assert len(list(result.scalars().all())) == 2

    async def test_partial_unique_index_blocks_duplicate_running(
        self, session, sample_filing,
    ):
        """同 (company_id, filing_id) で running 2 件も不可"""
        job1 = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(job1)
        await session.flush()

        job2 = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(job2)
        with pytest.raises(IntegrityError):
            await session.flush()
