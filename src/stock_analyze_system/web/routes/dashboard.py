"""Dashboard route."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.web.dependencies import get_services, render

router = APIRouter()


@dataclass(frozen=True)
class WatchlistPreviewRow:
    company_id: str
    name: str
    market: str | None
    ticker: str | None
    price: float | None
    currency: str | None
    per: float | None
    pbr: float | None
    market_cap: float | None


@dataclass(frozen=True)
class RecentSyncRow:
    company_id: str
    status: str
    fetched_at: datetime | None
    error_message: str | None


@dataclass(frozen=True)
class RecentAnalysisRow:
    company_id: str
    analysis_type: str
    model_name: str
    created_at: datetime | None


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    quote_svc = services.quote_service
    analysis_svc = services.analysis_service

    company_count = await services.company_service.count_companies()
    targets = await services.target_service.list_targets()
    watchlists = await services.watchlist_service.list_watchlists()

    watchlist_items_total = 0
    preview_watchlist = None
    preview_rows: list[WatchlistPreviewRow] = []
    for w in watchlists:
        full = await services.watchlist_service.get_with_items(w.id)
        if full and full.items:
            watchlist_items_total += len(full.items)
            if preview_watchlist is None:
                preview_watchlist = full
    if preview_watchlist is not None:
        head_items = preview_watchlist.items[:4]
        company_ids = [it.company_id for it in head_items]
        quotes = (
            await quote_svc.get_latest_many(company_ids)
            if quote_svc is not None else {}
        )
        for it in head_items:
            comp = await services.company_service.get_company(it.company_id)
            val = await services.valuation_service.get_latest(it.company_id)
            quote = quotes.get(it.company_id)
            preview_rows.append(WatchlistPreviewRow(
                company_id=it.company_id,
                name=comp.name if comp else it.company_id,
                market=comp.market if comp else None,
                ticker=(comp.ticker or comp.security_code) if comp else None,
                price=quote.price if quote else (val.stock_price if val else None),
                currency=quote.currency if quote else (val.currency if val else None),
                per=val.per if val else None,
                pbr=val.pbr if val else None,
                market_cap=val.market_cap if val else None,
            ))

    recent_syncs = [
        RecentSyncRow(
            company_id=q.company_id, status=q.status,
            fetched_at=q.fetched_at, error_message=q.error_message,
        )
        for q in (await quote_svc.list_recent(limit=5) if quote_svc else [])
    ]
    last_sync_at = (
        await quote_svc.latest_fetched_at() if quote_svc else None
    )

    analysis_count = 0
    legacy_analysis_count = 0
    recent_analyses: list[RecentAnalysisRow] = []
    if analysis_svc is not None:
        extractor_count = await analysis_svc.count_extractor()
        total_count = await analysis_svc.count_all_pipelines()
        analysis_count = extractor_count
        legacy_analysis_count = max(total_count - extractor_count, 0)
        recent_analyses = [
            RecentAnalysisRow(
                company_id=a.company_id, analysis_type=a.analysis_type,
                model_name=a.model_name, created_at=a.created_at,
            )
            for a in await analysis_svc.list_recent(limit=5)
        ]

    return render(request, "dashboard.html", {
        "company_count": company_count,
        "target_count": len(targets),
        "watchlist_count": len(watchlists),
        "watchlist_items_total": watchlist_items_total,
        "analysis_count": analysis_count,
        "legacy_analysis_count": legacy_analysis_count,
        "preview_watchlist": preview_watchlist,
        "preview_rows": preview_rows,
        "recent_syncs": recent_syncs,
        "recent_analyses": recent_analyses,
        "last_sync_at": last_sync_at,
    })
