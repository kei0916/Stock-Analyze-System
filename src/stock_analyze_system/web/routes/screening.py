"""Screening JSON API endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.services.screening import (
    FIELD_METADATA,
    SCREENING_CATEGORICAL_FIELDS,
    SCREENING_NUMERIC_FIELDS,
    FilterClause,
    ScreenSpec,
    SortSpec,
)
from stock_analyze_system.shared.json_utils import json_safe
from stock_analyze_system.web.auth import enforce_heavy_request_limit
from stock_analyze_system.web.dependencies import get_services, render

page_router = APIRouter()
router = APIRouter(prefix="/api/screening")


@page_router.get("/screening", response_class=HTMLResponse)
async def page(request: Request):
    return render(request, "screening/check.html")


class FilterPayload(BaseModel):
    field: str
    op: Literal["gte", "lte", "between", "eq", "in"]
    value: float | int | tuple[float, float] | list[float] | str | list[str]


class SortPayload(BaseModel):
    field: str
    desc: bool = True


class RunRequest(BaseModel):
    filters: list[FilterPayload] = Field(default_factory=list)
    sort: SortPayload | None = None
    limit: int = 100
    offset: int = 0
    include_null: bool = False


class TargetsRequest(BaseModel):
    company_ids: list[str]


def _require_service(services: ServiceContainer):
    svc = services.screening_service
    if svc is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="screening_service unavailable",
        )
    return svc


@router.post("/run")
async def run_screen(
    request: Request,
    payload: RunRequest,
    services: ServiceContainer = Depends(get_services),
):
    svc = _require_service(services)
    enforce_heavy_request_limit(
        request,
        scope="screening-run",
        detail="Too many screening requests",
    )
    spec = ScreenSpec(
        filters=[
            FilterClause(field=f.field, op=f.op, value=f.value)
            for f in payload.filters
        ],
        sort=SortSpec(field=payload.sort.field, desc=payload.sort.desc)
        if payload.sort
        else None,
        limit=payload.limit,
        offset=payload.offset,
        include_null=payload.include_null,
    )
    try:
        result = await svc.run_screen(spec)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "items": [
            {
                "company_id": it.company_id,
                "ticker": it.ticker,
                "name": it.name,
                "sector": it.sector,
                "market": it.market,
                "metrics": json_safe(it.metrics),
            }
            for it in result.items
        ],
        "total_matched": result.total_matched,
        "limit": result.limit,
        "offset": result.offset,
    }


@router.get("/distributions/{field}")
async def get_distribution(
    field: str,
    buckets: int = 20,
    services: ServiceContainer = Depends(get_services),
):
    svc = _require_service(services)
    try:
        dist = await svc.get_distribution(field, buckets=buckets)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "field": dist.field,
        "min": dist.min,
        "max": dist.max,
        "null_count": dist.null_count,
        "finite_count": dist.finite_count,
        "non_finite_count": dist.non_finite_count,
        "buckets": [
            {"lower": b.lower, "upper": b.upper, "count": b.count}
            for b in dist.buckets
        ],
    }


@router.get("/fields")
async def list_fields():
    return {
        "numeric": [
            {"field": m.field, "label": m.label, "format": m.format}
            for m in FIELD_METADATA
            if m.field in SCREENING_NUMERIC_FIELDS
        ],
        "categorical": [
            {"field": m.field, "label": m.label, "format": m.format}
            for m in FIELD_METADATA
            if m.field in SCREENING_CATEGORICAL_FIELDS
        ],
    }


@router.post("/targets")
async def add_targets(
    request: Request,
    payload: TargetsRequest,
    services: ServiceContainer = Depends(get_services),
):
    svc = _require_service(services)
    enforce_heavy_request_limit(
        request,
        scope="screening-targets",
        detail="Too many target add requests",
    )
    try:
        result = await svc.add_to_targets(payload.company_ids)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "requested": result.requested,
        "added": result.added,
        "already_present": result.already_present,
        "skipped": result.skipped,
    }
