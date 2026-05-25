"""JSON API endpoints."""

from __future__ import annotations

import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.models.enums import (
    ADR004_SUPPORTED_DESC,
    FilingType,
    PeriodType,
    is_adr004_supported,
)
from stock_analyze_system.services.filing_content import (
    filing_content_exists_for_source,
    filing_raw_html_exists,
)
from stock_analyze_system.web.auth import get_client_key
from stock_analyze_system.web.dependencies import get_services

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks")

# ADR-004 amendment 2026-05-17 §A: 分析候補は SEC 4 種に固定.
# 単一情報源は `models.enums.ADR004_FILING_TYPES` (frozenset[FilingType]).
ANALYSIS_FILING_TYPES = [
    FilingType.TEN_K,
    FilingType.TWENTY_F,
    FilingType.TEN_Q,
    FilingType.SIX_K,
]


def _filing_to_option(filing, *, fallback: bool = False) -> dict:
    """Filing を rag_filing_options 用の dict に変換する.

    `content_available` は filing.source に応じて判定する: SEC は ADR-004
    amendment §A の要請で raw HTML 必須、EDINET 等の PDF パイプラインは
    converted.pdf も真とみなす。ヘルパーを SEC 専用に固定したくないので
    `filing_content_exists_for_source` 経由で判定し、将来 EDINET 一覧用
    エンドポイントから再利用しても安全に動くようにする。
    """

    return {
        "id": filing.id,
        "filing_type": filing.filing_type,
        "period_type": filing.period_type,
        "fiscal_year": filing.fiscal_year,
        "period_end": filing.period_end.isoformat() if filing.period_end else None,
        "filed_at": filing.filed_at.isoformat() if filing.filed_at else None,
        "content_available": filing_content_exists_for_source(
            filing.source, filing.storage_path,
        ),
        "is_fallback_default": fallback,
    }


def _financial_to_dict(fd) -> dict:
    gross_profit: float | None = None
    if fd.revenue is not None and fd.cogs is not None:
        gross_profit = fd.revenue - fd.cogs
    return {
        "fiscal_year_end": fd.fiscal_year_end.isoformat() if fd.fiscal_year_end else None,
        "period_type": fd.period_type,
        "accounting_standard": fd.accounting_standard,
        "currency": fd.currency,
        "revenue": fd.revenue,
        "cogs": fd.cogs,
        "gross_profit": gross_profit,
        "operating_income": fd.operating_income,
        "net_income": fd.net_income,
        "eps": fd.eps,
        "fcf": fd.fcf,
        "ebitda": fd.ebitda,
        "operating_cf": fd.operating_cf,
        "capex": fd.capex,
        "total_assets": fd.total_assets,
        "equity": fd.equity,
    }


def _valuation_to_dict(v) -> dict:
    return {
        "date": v.date.isoformat() if v.date else None,
        "last_updated": v.last_updated.isoformat() if v.last_updated else None,
        "currency": v.currency,
        "stock_price": v.stock_price,
        "market_cap": v.market_cap,
        "per": v.per,
        "pbr": v.pbr,
        "ev_ebitda": v.ev_ebitda,
        "psr": v.psr,
        "fcf_yield": v.fcf_yield,
    }


def _serialize_metric_row(row: dict) -> dict:
    out = dict(row)
    fye = out.get("fiscal_year_end")
    if fye is not None and hasattr(fye, "isoformat"):
        out["fiscal_year_end"] = fye.isoformat()
    return out


@router.get("/{company_id}/financials/{period}")
async def get_financials(
    company_id: str,
    period: PeriodType,
    services: ServiceContainer = Depends(get_services),
):
    records = await services.financial_service.get_timeseries(
        company_id,
        period_type=period,
        years=10,
    )
    return [_financial_to_dict(r) for r in records]


@router.get("/{company_id}/valuations")
async def get_valuations(
    company_id: str,
    years: int = 5,
    services: ServiceContainer = Depends(get_services),
):
    if not 1 <= years <= 20:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="years must be between 1 and 20",
        )
    records = await services.valuation_service.get_history(company_id, years=years)
    return [_valuation_to_dict(r) for r in records]


@router.get("/{company_id}/metrics")
async def get_metrics(
    company_id: str,
    period: PeriodType = PeriodType.ANNUAL,
    services: ServiceContainer = Depends(get_services),
):
    records = await services.financial_service.get_timeseries(
        company_id,
        period_type=period,
        years=10,
    )
    rows = services.financial_service.compute_timeseries_metrics(records)
    return [_serialize_metric_row(r) for r in rows]


class AskRequest(BaseModel):
    question: str
    filing_id: int | None = None
    filing_type: FilingType = FilingType.TEN_K


def _get_rag_service(services: ServiceContainer):
    """ADR-004 amendment §B: 定型分析 (rag_analyze) で使う. rag_service は
    常時 non-None だが、defense-in-depth で None ガードを残す
    (将来 setup_services が失敗するケース、monkeypatch で None を入れる test との互換用)."""
    if services.rag_service is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is not available.",
        )
    return services.rag_service


def _get_pageindex_rag_service(services: ServiceContainer):
    """ADR-004 amendment §B: PageIndex 経路 (ask_question / build_index /
    get_index_status / get_qa_history) で使う. pageindex.enabled=false 時は
    rate limit を消費する前に 503 で early return する."""
    rag = services.rag_service
    if rag is None or not rag.pageindex_available:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PageIndex is disabled. Set pageindex.enabled=true to use ask/index.",
        )
    return rag


async def _resolve_filing(
    services: ServiceContainer,
    company_id: str,
    filing_id: int | None,
    filing_type: FilingType,
):
    if filing_id is not None:
        filing = await services.filing_service.get_filing_by_id(filing_id)
        if filing is None or filing.company_id != company_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"filing_id={filing_id} not found for {company_id}",
            )
        return filing
    filing = await services.filing_service.get_latest_filing(
        company_id,
        filing_type,
    )
    if filing is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No {filing_type} filings for {company_id}",
        )
    return filing


def _enforce_heavy_request_limit(
    request: Request,
    *,
    scope: str,
    detail: str,
) -> None:
    limiter = request.app.state.heavy_rate_limiter
    key = get_client_key(request, scope)
    if limiter.try_acquire(key) is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


@router.post("/{company_id}/rag/ask")
async def rag_ask(
    request: Request,
    company_id: str,
    payload: AskRequest,
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_pageindex_rag_service(services)
    filing = await _resolve_filing(
        services,
        company_id,
        payload.filing_id,
        payload.filing_type,
    )
    _enforce_heavy_request_limit(
        request,
        scope=f"rag-ask:{company_id}",
        detail="Too many RAG requests",
    )
    result = await rag.ask_question(filing, payload.question)
    return {
        "answer": result.answer,
        "source_pages": result.source_pages,
        "source_sections": result.source_sections,
    }


@router.post("/{company_id}/rag/index")
async def rag_index(
    request: Request,
    company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_pageindex_rag_service(services)
    filing = await _resolve_filing(services, company_id, filing_id, filing_type)
    _enforce_heavy_request_limit(
        request,
        scope=f"rag-index:{company_id}",
        detail="Too many index requests",
    )
    tree = await rag.build_index(filing)
    structure = tree.get("structure") if isinstance(tree, dict) else None
    return {"node_count": len(structure) if structure else 0}


@router.post("/{company_id}/rag/analyze", deprecated=True)
async def rag_analyze(
    request: Request,
    company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,
    services: ServiceContainer = Depends(get_services),
):
    """[DEPRECATED] 全タイプの定型分析を実行し、進捗を NDJSON でストリームする。

    新規利用は POST /api/analysis-jobs を推奨 (バックグラウンド実行)。
    本エンドポイントは互換目的で残されているが、次回リリースで削除予定。
    """
    logger.warning(
        "DEPRECATED: POST /api/stocks/%s/rag/analyze is deprecated. "
        "Use POST /api/analysis-jobs instead.",
        company_id,
    )
    rag = _get_rag_service(services)
    filing = await _resolve_filing(services, company_id, filing_id, filing_type)
    if not is_adr004_supported(filing):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"定型分析は {ADR004_SUPPORTED_DESC} の filing のみ対応です",
        )
    _enforce_heavy_request_limit(
        request,
        scope=f"rag-analyze:{company_id}",
        detail="Too many analyze requests",
    )

    async def stream():
        try:
            async for event in rag.run_full_analysis_stream(filing):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("rag analyze stream failed for %s", company_id)
            yield (
                json.dumps(
                    {"event": "error", "message": f"内部エラー: {exc}"},
                    ensure_ascii=False,
                )
                + "\n"
            )
            yield json.dumps({"event": "complete"}, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/{company_id}/rag/analyses")
async def rag_analyses(
    company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,
    services: ServiceContainer = Depends(get_services),
):
    """保存済み定型分析を返す.

    ADR-004 amendment §B: 定型分析は PageIndex 非依存のため、
    pageindex.enabled=false でも保存済み結果を返す.
    """
    if services.rag_service is None:
        return []  # defense-in-depth (rag_service 常時 non-None 想定)
    if filing_id is not None:
        filing = await services.filing_service.get_filing_by_id(filing_id)
        if filing is None or filing.company_id != company_id:
            return []
        return await services.rag_service.get_analyses(company_id, filing.id)
    filing = await services.filing_service.get_latest_filing(
        company_id,
        filing_type,
    )
    if filing is None:
        return []
    return await services.rag_service.get_analyses(company_id, filing.id)


@router.get("/{company_id}/rag/filing_options")
async def rag_filing_options(
    company_id: str,
    years: int = 10,
    services: ServiceContainer = Depends(get_services),
):
    """RAG タブの定型分析切り替え用 filing リスト.

    ADR-004 amendment §A: `default` / `annual_options` ともに SEC source の
    10-K / 10-Q / 20-F / 6-K のみを返す. EDINET annual_report は extractor
    非対応のため最新であっても出さない.

    - `default`: ADR-004 対象のうち、インデックス済み → 本体取得済み → 最新 の優先順
    - `annual_options`: 過去 `years` 年分の ADR-004 対象を新しい順
    """
    since_year = date.today().year - years
    analysis_filings = await services.filing_service.list_by_types(
        company_id,
        [str(t) for t in ANALYSIS_FILING_TYPES],
        since_year=since_year,
    )
    # defense-in-depth: list_by_types は filing_type だけで filter するため
    # source != "SEC" の偶発被りを再フィルタする.
    analysis_filings = [f for f in analysis_filings if is_adr004_supported(f)]

    default_filing = None
    fallback_used = False
    if services.rag_service is not None and services.rag_service.pageindex_available:
        candidate = await services.filing_service.get_latest_indexed(company_id)
        if is_adr004_supported(candidate) and filing_raw_html_exists(candidate.storage_path):
            default_filing = candidate
    if default_filing is None:
        # indexed lookup が空のときだけ全件 list_by_recency を取得し、
        # content あり > content 無し (fallback) の順で 1 度の走査で決める.
        all_filings_by_recency = await services.filing_service.list_by_recency(company_id)
        fallback_candidate = None
        for filing in all_filings_by_recency:
            if not is_adr004_supported(filing):
                continue
            if filing_raw_html_exists(filing.storage_path):
                default_filing = filing
                break
            if fallback_candidate is None:
                fallback_candidate = filing
        if default_filing is None and fallback_candidate is not None:
            default_filing = fallback_candidate
            fallback_used = True
    return {
        "default": (
            _filing_to_option(default_filing, fallback=fallback_used) if default_filing else None
        ),
        "annual_options": [_filing_to_option(f) for f in analysis_filings],
    }


@router.get("/{company_id}/rag/history")
async def rag_history(
    company_id: str,
    limit: int = 50,
    services: ServiceContainer = Depends(get_services),
):
    """過去の自由質問 Q&A 履歴を新しい順で返す.

    ADR-004 amendment §B: Q&A 履歴の **閲覧** は PageIndex 非依存
    (`RagService.get_qa_history` は `_qa_history_repo is None` だけを見る).
    新規 Q&A は ask_question (PageIndex 経路) 経由でしか追加されないため、
    PageIndex 無効状態では「過去ログ閲覧のみ」になる. PageIndex 無効化で
    既存履歴が UI から消える regression を避けるため、ここでは
    `pageindex_available` を guard にしない.
    """
    if services.rag_service is None:
        return []
    return await services.rag_service.get_qa_history(company_id, limit=limit)
