"""共有クライアントブートストラップ — Web/Worker 両プロセスから使う"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from stock_analyze_system.config import AppConfig

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from stock_analyze_system.ingestion.edinet import EdinetClient
    from stock_analyze_system.ingestion.fmp import FmpClient
    from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
    from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
    from stock_analyze_system.services.llm_client import LlmClient
    from stock_analyze_system.services.pdf_converter import PdfConverter


@dataclass
class ClientBundle:
    """Web/Worker プロセスで共有する外部 API クライアント。"""

    sec: "SecEdgarClient"
    edinet: "EdinetClient"
    yahoo: "YahooFinanceClient"
    fmp: "FmpClient"
    # `llm` is always non-None when constructed via build_client_bundle
    # (ADR-004 amendment §B). The `| None` default supports manual test
    # construction where llm is not needed.
    llm: "LlmClient | None" = None
    pdf_converter: "PdfConverter | None" = None


def build_client_bundle(config: AppConfig) -> ClientBundle:
    """全外部 API クライアントを構築する.

    `LlmClient` は ADR-004 amendment §B により定型分析でも必要なため常に構築する。
    `PdfConverter` は PageIndex (ask_question 経路) でのみ使うため
    `pageindex.enabled` 条件で構築する。"""
    from stock_analyze_system.ingestion.edinet import EdinetClient
    from stock_analyze_system.ingestion.fmp import FmpClient
    from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
    from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
    from stock_analyze_system.services.llm_client import LlmClient

    bundle = ClientBundle(
        sec=SecEdgarClient(
            email=config.sec_edgar.email,
            rate=config.sec_edgar.rate_limit_rps,
        ),
        edinet=EdinetClient(
            api_key=config.edinet.api_key,
            base_url=config.edinet.base_url,
        ),
        yahoo=YahooFinanceClient(rate=config.yahoo_finance.rate_limit_rps),
        fmp=FmpClient(
            api_key=config.fmp.api_key,
            base_url=config.fmp.base_url,
        ),
        llm=LlmClient(config.llm),
    )
    if config.pageindex.enabled:
        from stock_analyze_system.services.pdf_converter import PdfConverter
        bundle.pdf_converter = PdfConverter()
    return bundle


async def dispose_clients(bundle: ClientBundle) -> None:
    """全クライアントの close() を並列実行。個別失敗は warning ログのみ。"""
    op_names: list[str] = []
    close_calls: list[Awaitable[Any]] = []
    for name, client in (
        ("sec", bundle.sec),
        ("edinet", bundle.edinet),
        ("yahoo", bundle.yahoo),
        ("fmp", bundle.fmp),
    ):
        close_fn = getattr(client, "close", None)
        if close_fn is not None:
            op_names.append(name)
            close_calls.append(close_fn())
    if not close_calls:
        return
    results = await asyncio.gather(*close_calls, return_exceptions=True)
    for op, result in zip(op_names, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "dispose: %s close failed: %s",
                op,
                result,
                exc_info=result,
            )
