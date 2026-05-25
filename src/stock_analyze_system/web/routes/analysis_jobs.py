"""バックグラウンド分析ジョブ API"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.models.analysis_job import JobStatus
from stock_analyze_system.models.enums import is_adr004_supported
from stock_analyze_system.services.analysis_queue import AnalysisQueueService
from stock_analyze_system.web.auth import enforce_heavy_request_limit
from stock_analyze_system.web.dependencies import (
    AppState, get_app_state, get_services,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis-jobs")


class CreateJobRequest(BaseModel):
    company_id: str
    filing_id: int


def _job_to_dict(job) -> dict:
    return {
        "job_id": job.id,
        "company_id": job.company_id,
        "filing_id": job.filing_id,
        "status": job.status,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "current_analysis_type": job.current_analysis_type,
        "error_details": job.error_details,
        "created_at": (
            job.created_at.isoformat() if job.created_at else None
        ),
        "started_at": (
            job.started_at.isoformat() if job.started_at else None
        ),
        "completed_at": (
            job.completed_at.isoformat() if job.completed_at else None
        ),
        "dismissed_at": (
            job.dismissed_at.isoformat() if job.dismissed_at else None
        ),
    }


def _get_queue(state: AppState = Depends(get_app_state)) -> AnalysisQueueService:
    return state.analysis_queue


@router.post("")
async def create_job(
    request: Request,
    body: CreateJobRequest,
    response: Response,
    queue: AnalysisQueueService = Depends(_get_queue),
    services: ServiceContainer = Depends(get_services),
):
    # filing が company_id に属することを境界で検証 (旧API同等)。
    filing = await services.filing_service.get_filing_by_id(body.filing_id)
    if filing is None or filing.company_id != body.company_id:
        raise HTTPException(
            status_code=404,
            detail=f"filing_id={body.filing_id} not found for {body.company_id}",
        )

    # ADR-004 amendment §A: FilingSectionExtractor の対象は SEC 4 種のみ.
    if not is_adr004_supported(filing):
        raise HTTPException(
            status_code=422,
            detail=(
                f"filing_type={filing.filing_type} (source={filing.source}) "
                "is not supported by ADR-004 extractor"
            ),
        )

    # 既存 pending/running は重複として早期返却。重い rate limit は
    # 新規作成時のみ消費する (再試行・複数タブの cheap な POST を 429 で
    # 拒否しないため)。
    existing = await queue.list_jobs(
        company_id=body.company_id,
        filing_id=body.filing_id,
        statuses=[JobStatus.PENDING, JobStatus.RUNNING],
        limit=1,
    )
    if existing:
        response.status_code = 200
        return _job_to_dict(existing[0])

    enforce_heavy_request_limit(
        request,
        scope=f"analysis-jobs:{body.company_id}",
        detail="Too many analysis-job requests",
    )
    job, is_new = await queue.enqueue(body.company_id, body.filing_id)
    response.status_code = 201 if is_new else 200
    return _job_to_dict(job)


@router.get("/{job_id}")
async def get_job(
    job_id: int,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    job = await queue.get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@router.get("")
async def list_jobs(
    company_id: str | None = None,
    filing_id: int | None = None,
    status: str | None = None,
    include_dismissed: bool = False,
    limit: int = Query(20, ge=1, le=100),
    queue: AnalysisQueueService = Depends(_get_queue),
):
    statuses: list[JobStatus] | None = None
    if status:
        try:
            statuses = [
                JobStatus(s.strip()) for s in status.split(",") if s.strip()
            ]
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {exc}",
            )
    jobs = await queue.list_jobs(
        company_id=company_id,
        filing_id=filing_id,
        statuses=statuses,
        include_dismissed=include_dismissed,
        limit=limit,
    )
    return [_job_to_dict(j) for j in jobs]


@router.delete("/{job_id}")
async def cancel_job(
    job_id: int,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    job = await queue.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@router.post("/{job_id}/dismiss")
async def dismiss_job(
    job_id: int,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    try:
        job = await queue.dismiss(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)
