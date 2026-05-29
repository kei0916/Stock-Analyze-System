"""Analysis targets routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.exceptions import NotFoundError
from stock_analyze_system.web.dependencies import get_services, render

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/targets")


async def _ensure_target_company(
    company_id: str,
    services: ServiceContainer,
):
    normalized = company_id.strip().upper()
    company = await services.company_service.get_company(normalized)
    if company is not None:
        return company

    sec_entry = None
    if normalized.startswith("US_"):
        ticker = normalized.removeprefix("US_")
        if ticker:
            sec_entry = await services.filing_sync.find_sec_company_by_ticker(ticker)
    elif normalized.startswith("SEC_"):
        cik = normalized.removeprefix("SEC_")
        sec_entry = await services.filing_sync.find_sec_company_by_cik(cik)
        if sec_entry is None and cik.isdigit():
            sec_entry = {
                "cik": cik.zfill(10),
                "name": f"CIK {cik.zfill(10)}",
                "ticker": None,
                "exchange": None,
            }

    if sec_entry is None:
        return None

    return await services.company_service.register_sec_filer(
        cik=sec_entry["cik"],
        name=sec_entry.get("name") or normalized,
        ticker=sec_entry.get("ticker"),
        exchange=sec_entry.get("exchange"),
    )


@router.get("", response_class=HTMLResponse)
async def list_page(
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    targets = await services.target_service.list_targets()
    return render(request, "targets/list.html", {"targets": targets})


@router.post("")
async def add(
    company_id: str = Form(...),
    services: ServiceContainer = Depends(get_services),
):
    company = await _ensure_target_company(company_id, services)
    if company is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )
    await services.target_service.add_target(company.id)
    valuation_result = await services.job_service.update_valuation_for_company(company.id)
    if valuation_result.errors:
        logger.warning(
            "Initial valuation update for %s completed with errors: %s",
            company.id,
            valuation_result.errors,
        )
    return RedirectResponse(
        url="/targets", status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{company_id}/delete")
async def remove(
    company_id: str,
    services: ServiceContainer = Depends(get_services),
):
    try:
        await services.target_service.remove_target(company_id)
    except NotFoundError as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=str(e),
        ) from e
    return RedirectResponse(
        url="/targets", status_code=status.HTTP_303_SEE_OTHER,
    )
