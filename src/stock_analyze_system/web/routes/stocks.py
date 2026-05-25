"""Stocks routes — search + detail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services, render

router = APIRouter(prefix="/stocks")


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    return render(request, "stocks/search.html")


@router.get("/search/results", response_class=HTMLResponse)
async def search_results(
    request: Request,
    q: str = "",
    services: ServiceContainer = Depends(get_services),
):
    companies = []
    if q.strip():
        companies = await services.company_service.search_companies(q.strip(), limit=20)
    return render(request, "stocks/_search_results.html", {"companies": companies})


@router.get("/{company_id}", response_class=HTMLResponse)
async def detail_page(
    company_id: str,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    company = await services.company_service.get_company(company_id)
    if company is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )
    filings = await services.filing_service.list_filings(company_id)
    return render(
        request,
        "stocks/detail.html",
        {"company": company, "filings": filings},
    )
