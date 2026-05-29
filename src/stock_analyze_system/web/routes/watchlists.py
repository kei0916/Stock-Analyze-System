"""Watchlist routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.exceptions import DuplicateError
from stock_analyze_system.web.dependencies import get_services, render

router = APIRouter(prefix="/watchlists")


@router.get("", response_class=HTMLResponse)
async def list_page(
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    watchlists = await services.watchlist_service.list_watchlists()
    return render(request, "watchlists/list.html", {"watchlists": watchlists})


@router.post("")
async def create(
    name: str = Form(...),
    description: str = Form(""),
    services: ServiceContainer = Depends(get_services),
):
    try:
        await services.watchlist_service.create_watchlist(
            name, description or None,
        )
    except DuplicateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    return RedirectResponse(
        url="/watchlists", status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{watchlist_id}", response_class=HTMLResponse)
async def detail_page(
    watchlist_id: int,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    wl = await services.watchlist_service.get_with_items(watchlist_id)
    if wl is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found",
        )
    return render(
        request,
        "watchlists/detail.html",
        {"watchlist": wl, "items": wl.items},
    )
