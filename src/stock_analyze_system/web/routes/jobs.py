"""Jobs routes — manual sync triggers."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.datastructures import URL

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.auth import get_client_key
from stock_analyze_system.web.dependencies import get_services, render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs")
_USER_SAFE_ERROR = "ジョブの実行に失敗しました。詳細はサーバーログを確認してください。"
_RATE_LIMIT_ERROR = "リクエストが多すぎます。しばらく待ってから再試行してください。"


def _error_redirect(message: str) -> RedirectResponse:
    url = URL("/jobs").include_query_params(error=message)
    return RedirectResponse(url=str(url), status_code=status.HTTP_303_SEE_OTHER)


def _success_redirect() -> RedirectResponse:
    return RedirectResponse(url="/jobs", status_code=status.HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse)
async def list_page(request: Request, error: str | None = None):
    return render(request, "jobs/list.html", {"error": error})


@router.post("/sync")
async def sync_company(
    request: Request,
    company_id: str = Form(...),
    services: ServiceContainer = Depends(get_services),
):
    limiter = request.app.state.heavy_rate_limiter
    key = get_client_key(request, "jobs-sync")
    if limiter.try_acquire(key) is None:
        return _error_redirect(_RATE_LIMIT_ERROR)
    try:
        await services.job_service.sync_company(company_id)
    except Exception:
        logger.exception("sync_company failed for %s", company_id)
        return _error_redirect(_USER_SAFE_ERROR)
    return _success_redirect()


@router.post("/daily")
async def daily(
    request: Request,
    market: str = Form("us"),
    services: ServiceContainer = Depends(get_services),
):
    limiter = request.app.state.heavy_rate_limiter
    key = get_client_key(request, "jobs-daily")
    if limiter.try_acquire(key) is None:
        return _error_redirect(_RATE_LIMIT_ERROR)
    try:
        await services.job_service.run_daily_update(market)
    except Exception:
        logger.exception("daily update failed for market=%s", market)
        return _error_redirect(_USER_SAFE_ERROR)
    return _success_redirect()
