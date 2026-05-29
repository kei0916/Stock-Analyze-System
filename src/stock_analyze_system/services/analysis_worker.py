"""Background LLM analysis worker / separate process daemon."""
from __future__ import annotations

import asyncio
import fcntl
import logging
import signal
from pathlib import Path
from typing import TextIO

from stock_analyze_system.cli.container import setup_services
from stock_analyze_system.config import AppConfig
from stock_analyze_system.exceptions import (
    AnalysisFailedError,
    ExtractionFailedError,
)
from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.enums import (
    ADR004_SUPPORTED_DESC,
    is_adr004_supported,
)
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository
from stock_analyze_system.shared.clients import ClientBundle
from stock_analyze_system.shared.time_utils import now_utc

logger = logging.getLogger(__name__)

# ADR-004 §A15: runbook (docs/analysis-jobs-runbook.md §2.1) と
# error_details の key 名を同期するための単一情報源。
# 追加・改名するときは runbook の表も同時に更新する
# (`test_runbook_error_details_keys_match_worker_constants` が同期を検査)。
ERROR_DETAILS_KEYS: frozenset[str] = frozenset({
    "extraction_error",  # FilingSectionExtractor / preflight 失敗
    "failed_types",      # 特定 analysis_type の step-3 LLM 失敗
})


class AnalysisWorker:
    """Separate-process worker for background LLM analysis jobs."""

    def __init__(
        self,
        session_factory,
        config: AppConfig,
        clients: ClientBundle,
        *,
        poll_interval: float = 2.0,
    ):
        self._session_factory = session_factory
        self._config = config
        self._clients = clients
        self._poll_interval = poll_interval
        self._shutdown = asyncio.Event()
        self._worker_lock_file: TextIO | None = None

    def request_shutdown(self) -> None:
        self._shutdown.set()

    async def run_forever(self) -> None:
        """Run jobs until shutdown is requested."""
        self._acquire_worker_lock()
        try:
            await self._reset_stale_running()

            while not self._shutdown.is_set():
                executed = await self.run_one_job()
                if executed:
                    continue

                try:
                    await asyncio.wait_for(
                        self._shutdown.wait(),
                        timeout=self._poll_interval,
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            self._release_worker_lock()

    def _worker_lock_path(self) -> Path | None:
        bind = getattr(self._session_factory, "kw", {}).get("bind")
        if bind is None:
            bind = getattr(self._session_factory, "bind", None)

        database = getattr(getattr(bind, "url", None), "database", None)
        if database in (None, "", ":memory:"):
            return None

        db_path = Path(database)
        return db_path.with_name(f"{db_path.name}.worker.lock")

    def _acquire_worker_lock(self) -> None:
        lock_path = self._worker_lock_path()
        if lock_path is None:
            logger.warning(
                "analysis worker lock skipped; database path could not be derived",
            )
            return

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise RuntimeError("Another analysis worker is already running") from exc

        self._worker_lock_file = lock_file

    def _release_worker_lock(self) -> None:
        if self._worker_lock_file is None:
            return

        try:
            fcntl.flock(self._worker_lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            self._worker_lock_file.close()
            self._worker_lock_file = None

    async def run_one_job(self) -> bool:
        """Dequeue and execute one pending job. Return False when no job exists."""
        job = await self._dequeue_next()
        if job is None:
            return False

        await self._execute_with_status(job)
        return True

    async def _reset_stale_running(self) -> None:
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            await repo.reset_running_to_failed(
                reason="Worker restarted while running",
            )

    async def _dequeue_next(self) -> AnalysisJob | None:
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            return await repo.dequeue_next()

    async def _execute_with_status(self, job: AnalysisJob) -> None:
        """Run one job and reflect the result in its persisted status."""
        try:
            await self._run_job(job)
        except asyncio.CancelledError:
            await self._finalize(job.id, JobStatus.CANCELLED)
            raise
        except AnalysisFailedError as exc:
            await self._finalize(
                job.id, JobStatus.FAILED,
                error_details={"failed_types": exc.failed_types},
            )
        except ExtractionFailedError as exc:
            await self._finalize(
                job.id, JobStatus.FAILED,
                error_details={"extraction_error": {
                    "message": str(exc),
                    "diagnostic": exc.diagnostic,
                }},
            )
        except Exception as exc:
            logger.exception("job %d failed", job.id)
            await self._finalize(
                job.id, JobStatus.FAILED,
                error_details={"reason": str(exc)},
            )
        else:
            await self._finalize(job.id, JobStatus.COMPLETED)

    async def _finalize(
        self,
        job_id: int,
        status: JobStatus,
        *,
        error_details: dict | None = None,
    ) -> None:
        """Persist a job's terminal status with a single owning session."""
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            await repo.update_status(
                job_id,
                status,
                completed_at=now_utc(),
                error_details=error_details,
            )

    async def _run_job(self, job: AnalysisJob) -> None:
        """Run one job by consuming RagService.run_full_analysis_stream."""
        failed_types: list[dict] = []
        extraction_error: dict | None = None
        progress_index = 0

        async with self._session_factory() as session:
            container = await setup_services(
                session,
                self._config,
                clients=self._clients,
            )
            rag = container.rag_service
            # ADR-004 amendment §B: rag_service は常に構築されるため None ガードは不要。
            filing = await container.filing_service.get_filing_by_id(
                job.filing_id,
            )
            if filing is None:
                raise ValueError(f"filing_id={job.filing_id} not found")
            if filing.company_id != job.company_id:
                raise ValueError(
                    f"filing_id={job.filing_id} belongs to {filing.company_id}, "
                    f"not job.company_id={job.company_id}"
                )

            # ADR-004 amendment §A defense-in-depth: API 境界を bypass する
            # 経路 (DB 直書き / 旧 pending job) でも違反は extractor 前で
            # 失敗させ、`failed_types` の取りこぼしと区別する.
            if not is_adr004_supported(filing):
                raise ExtractionFailedError(
                    f"unsupported filing for ADR-004 extractor: "
                    f"source={filing.source}, filing_type={filing.filing_type} "
                    f"(supported: {ADR004_SUPPORTED_DESC})",
                )

            # Step-3-equivalent LLM probe. Failing here is much cheaper than
            # discovering the broken LLM after a 20-minute extractor run.
            preflight = await rag.preflight()
            if preflight.get("status") != "ok":
                reason = preflight.get("reason") or "empty response"
                raise ExtractionFailedError(
                    f"preflight failed ({preflight.get('status')}): {reason}",
                    diagnostic=preflight.get("diagnostic"),
                )

            repo = AnalysisJobRepository(session)

            async for event in rag.run_full_analysis_stream(filing):
                etype = event.get("event")
                if etype == "started":
                    await repo.update_progress(job.id, total=event["total"])
                elif etype == "phase":
                    progress_index = event["index"]
                    await repo.update_progress(job.id, current=progress_index)
                    await repo.set_current_type(job.id, event["analysis_type"])
                elif etype in ("done", "cached", "skipped"):
                    progress_index = event["index"] + 1
                    await repo.update_progress(job.id, current=progress_index)
                elif etype == "error":
                    if "index" in event:
                        progress_index = event.get("index", progress_index) + 1
                        await repo.update_progress(job.id, current=progress_index)
                    analysis_type = event.get("analysis_type")
                    if analysis_type is None:
                        extraction_error = {
                            "message": event.get("message", ""),
                            "diagnostic": event.get("diagnostic"),
                        }
                    else:
                        failed_types.append({
                            "type": analysis_type,
                            "message": event.get("message", ""),
                        })

            await repo.update_progress(job.id, current=progress_index)

        if extraction_error is not None:
            raise ExtractionFailedError(
                extraction_error["message"],
                diagnostic=extraction_error.get("diagnostic"),
            )
        if failed_types:
            raise AnalysisFailedError(failed_types)

    def install_signal_handlers(self) -> None:
        def handler(signum, frame) -> None:  # noqa: ARG001
            logger.info("analysis worker received signal %s; shutting down", signum)
            self.request_shutdown()

        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)
