"""RAG top-level Q&A page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services, render

router = APIRouter(prefix="/rag")


@router.get("/{company_id}", response_class=HTMLResponse)
async def ask_page(
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
    return render(request, "rag/ask.html", {"company": company})
