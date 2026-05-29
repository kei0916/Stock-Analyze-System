"""AnalysisJob リポジトリ"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.shared.time_utils import now_utc


class AnalysisJobRepository:
    """AnalysisJob ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, *, company_id: str, filing_id: int) -> AnalysisJob:
        job = AnalysisJob(
            company_id=company_id,
            filing_id=filing_id,
            status=JobStatus.PENDING.value,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get(self, job_id: int) -> AnalysisJob | None:
        # populate_existing で identity map のキャッシュを上書きし、
        # raw UPDATE 直後でも DB の最新値を返す。
        # キュー用途ではジョブ取得頻度が低いので追加 SELECT のコストは許容。
        return await self._session.get(
            AnalysisJob, job_id, populate_existing=True,
        )

    async def find_active_by_company_filing(
        self, company_id: str, filing_id: int,
    ) -> AnalysisJob | None:
        stmt = select(AnalysisJob).where(
            AnalysisJob.company_id == company_id,
            AnalysisJob.filing_id == filing_id,
            AnalysisJob.status.in_(
                [JobStatus.PENDING.value, JobStatus.RUNNING.value],
            ),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        company_id: str | None = None,
        filing_id: int | None = None,
        statuses: list[JobStatus] | None = None,
        include_dismissed: bool = False,
        limit: int = 20,
    ) -> list[AnalysisJob]:
        stmt = select(AnalysisJob)
        if company_id is not None:
            stmt = stmt.where(AnalysisJob.company_id == company_id)
        if filing_id is not None:
            stmt = stmt.where(AnalysisJob.filing_id == filing_id)
        if statuses is not None:
            stmt = stmt.where(
                AnalysisJob.status.in_([s.value for s in statuses]),
            )
        if not include_dismissed:
            stmt = stmt.where(AnalysisJob.dismissed_at.is_(None))
        stmt = stmt.order_by(AnalysisJob.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def dequeue_next(self) -> AnalysisJob | None:
        """最古の pending を原子的に running に遷移させ、ジョブを返す。

        rowcount を見ることで複数ワーカー間の競合に耐性を持つ。
        他ワーカーが先に取った場合は None を返す。
        """

        stmt = (
            select(AnalysisJob.id)
            .where(AnalysisJob.status == JobStatus.PENDING.value)
            .order_by(AnalysisJob.created_at.asc(), AnalysisJob.id.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        candidate_id = result.scalar_one_or_none()
        if candidate_id is None:
            return None

        now = now_utc()
        update_stmt = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == candidate_id,
                AnalysisJob.status == JobStatus.PENDING.value,
            )
            .values(
                status=JobStatus.RUNNING.value,
                started_at=now,
            )
        )
        update_result = await self._session.execute(update_stmt)
        await self._session.commit()

        if update_result.rowcount == 0:
            return None

        # populate_existing で identity map のキャッシュを上書きし、
        # UPDATE 後の最新値 (status=running, started_at=now) を返す。
        return await self._session.get(
            AnalysisJob, candidate_id, populate_existing=True,
        )

    async def update_status(
        self,
        job_id: int,
        status: JobStatus,
        *,
        completed_at=None,
        error_details: dict | None = None,
    ) -> None:
        """ジョブの status を遷移させる。指定された付随フィールドのみ更新。"""

        values: dict = {"status": status.value}
        if completed_at is not None:
            values["completed_at"] = completed_at
        if error_details is not None:
            values["error_details"] = error_details
        if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            values["current_analysis_type"] = None

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def cancel_pending(self, job_id: int, *, completed_at) -> bool:
        """pending のままの場合だけ cancelled に遷移させる。"""

        stmt = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status == JobStatus.PENDING.value,
            )
            .values(
                status=JobStatus.CANCELLED.value,
                completed_at=completed_at,
                current_analysis_type=None,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    async def dismiss(self, job_id: int) -> None:

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(dismissed_at=now_utc())
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def dismiss_past_for_filing(
        self, company_id: str, filing_id: int, *, commit: bool = True,
    ) -> int:
        """同 filing の failed/cancelled (未 dismiss) を dismiss する。

        デフォルトでは direct caller の取りこぼしを防ぐため commit する。
        enqueue のように後続 create と同一 transaction に含めたい caller は
        commit=False を明示する。
        """

        stmt = (
            update(AnalysisJob)
            .where(
                AnalysisJob.company_id == company_id,
                AnalysisJob.filing_id == filing_id,
                AnalysisJob.status.in_(
                    [JobStatus.FAILED.value, JobStatus.CANCELLED.value],
                ),
                AnalysisJob.dismissed_at.is_(None),
            )
            .values(dismissed_at=now_utc())
        )
        result = await self._session.execute(stmt)
        if commit:
            await self._session.commit()
        return result.rowcount

    async def reset_running_to_failed(self, *, reason: str) -> int:
        """running を failed にリセット（起動時復旧用）。"""

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.status == JobStatus.RUNNING.value)
            .values(
                status=JobStatus.FAILED.value,
                error_details={"reason": reason},
                completed_at=now_utc(),
                current_analysis_type=None,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount

    async def update_progress(
        self,
        job_id: int,
        *,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """進捗カウンタを更新する (指定された値のみ書き込む)。"""

        values: dict = {}
        if current is not None:
            values["progress_current"] = current
        if total is not None:
            values["progress_total"] = total
        if not values:
            return

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def set_current_type(self, job_id: int, value: str) -> None:
        """`current_analysis_type` をセット (phase 切替時に呼ぶ)。"""
        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(current_analysis_type=value)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def clear_current_type(self, job_id: int) -> None:
        """`current_analysis_type` を NULL にする (全 phase 完了後に呼ぶ)。"""
        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(current_analysis_type=None)
        )
        await self._session.execute(stmt)
        await self._session.commit()
