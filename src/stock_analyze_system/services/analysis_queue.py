"""Web 側の LLM 分析キューサービス"""
from __future__ import annotations

import asyncio

from sqlalchemy.exc import IntegrityError

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository
from stock_analyze_system.shared.time_utils import now_utc


class AnalysisQueueService:
    """Web 側の LLM 分析キュー操作を提供するサービス。"""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._enqueue_lock = asyncio.Lock()

    async def enqueue(
        self, company_id: str, filing_id: int,
    ) -> tuple[AnalysisJob, bool]:
        """ジョブを enqueue。

        Returns:
            (job, is_new): is_new=True なら新規作成、False なら既存 pending/running を返却。
        """
        async with self._enqueue_lock:
            async with self._session_factory() as session:
                repo = AnalysisJobRepository(session)

                existing = await repo.find_active_by_company_filing(
                    company_id, filing_id,
                )
                if existing is not None:
                    return existing, False

                try:
                    # 同 filing の過去 failed/cancelled を自動 dismiss。
                    # create と同一 transaction にし、新規作成失敗時に
                    # 調査対象の failure history だけが消えないようにする。
                    await repo.dismiss_past_for_filing(
                        company_id, filing_id, commit=False,
                    )
                    job = await repo.create(
                        company_id=company_id, filing_id=filing_id,
                    )
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    existing = await repo.find_active_by_company_filing(
                        company_id, filing_id,
                    )
                    if existing is not None:
                        return existing, False
                    raise

        return job, True

    async def cancel(self, job_id: int) -> AnalysisJob | None:
        """pending ジョブをキャンセルする。running 以降は変更しない。"""
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            job = await repo.get(job_id)
            if job is None:
                return None

            if job.status == JobStatus.PENDING.value:
                completed = now_utc()
                cancelled = await repo.cancel_pending(
                    job_id, completed_at=completed,
                )
                if not cancelled:
                    return await repo.get(job_id)

                job.status = JobStatus.CANCELLED.value
                job.completed_at = completed
                return job

            return job  # 既に終了状態

    async def dismiss(self, job_id: int) -> AnalysisJob | None:
        """完了状態のジョブを UI から非表示にする。"""
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            job = await repo.get(job_id)
            if job is None:
                return None
            allowed = {
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
                JobStatus.COMPLETED.value,
            }
            if job.status not in allowed:
                raise ValueError(
                    f"Cannot dismiss job in status: {job.status}",
                )
            dismissed = now_utc()
            await repo.dismiss(job_id)
            job.dismissed_at = dismissed
            return job

    async def get_status(self, job_id: int) -> AnalysisJob | None:
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            return await repo.get(job_id)

    async def list_jobs(
        self,
        *,
        company_id: str | None = None,
        filing_id: int | None = None,
        statuses: list[JobStatus] | None = None,
        include_dismissed: bool = False,
        limit: int = 20,
    ) -> list[AnalysisJob]:
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            return await repo.list(
                company_id=company_id,
                filing_id=filing_id,
                statuses=statuses,
                include_dismissed=include_dismissed,
                limit=limit,
            )
