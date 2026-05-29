"""shared/clients.py のユニットテスト"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from stock_analyze_system.config import AppConfig, LlmConfig, PageIndexConfig
from stock_analyze_system.shared.clients import (
    ClientBundle,
    build_client_bundle,
    dispose_clients,
)


def _make_config(*, pageindex_enabled: bool) -> AppConfig:
    config = AppConfig()
    config.pageindex = PageIndexConfig(enabled=pageindex_enabled)
    config.llm = LlmConfig()
    return config


def test_build_client_bundle_without_pageindex():
    """ADR-004 amendment §B: LlmClient は常時構築 (定型分析が PageIndex 非依存に
    なったため worker / RagService から常に必要)。`PdfConverter` だけが
    pageindex.enabled 条件下に残る。"""
    config = _make_config(pageindex_enabled=False)
    bundle = build_client_bundle(config)
    assert bundle.sec is not None
    assert bundle.edinet is not None
    assert bundle.yahoo is not None
    assert bundle.fmp is not None
    assert bundle.llm is not None
    assert bundle.pdf_converter is None


def test_client_bundle_is_owned_by_shared_clients():
    assert ClientBundle.__module__ == "stock_analyze_system.shared.clients"


def test_build_client_bundle_with_pageindex():
    config = _make_config(pageindex_enabled=True)
    bundle = build_client_bundle(config)
    assert bundle.llm is not None
    assert bundle.pdf_converter is not None


async def test_dispose_clients_calls_close_on_each():
    bundle = MagicMock()
    bundle.sec.close = AsyncMock()
    bundle.edinet.close = AsyncMock()
    bundle.yahoo.close = AsyncMock()
    bundle.fmp.close = AsyncMock()
    # llm / pdf_converter は close が無いケースも想定
    bundle.llm = None
    bundle.pdf_converter = None

    await dispose_clients(bundle)

    bundle.sec.close.assert_awaited_once()
    bundle.edinet.close.assert_awaited_once()
    bundle.yahoo.close.assert_awaited_once()
    bundle.fmp.close.assert_awaited_once()


async def test_dispose_clients_skips_iterated_client_without_close():
    bundle = MagicMock()
    bundle.sec = MagicMock(spec=[])  # close 属性なし
    bundle.edinet.close = AsyncMock()
    bundle.fmp.close = AsyncMock()
    bundle.yahoo = MagicMock(spec=[])
    bundle.llm = None
    bundle.pdf_converter = None

    await dispose_clients(bundle)

    bundle.edinet.close.assert_awaited_once()
    bundle.fmp.close.assert_awaited_once()


async def test_dispose_clients_swallows_exceptions(caplog):
    bundle = MagicMock()
    bundle.sec.close = AsyncMock(side_effect=RuntimeError("boom"))
    bundle.edinet.close = AsyncMock()
    bundle.fmp.close = AsyncMock()
    bundle.yahoo = MagicMock(spec=[])
    bundle.llm = None
    bundle.pdf_converter = None

    # 例外を raise せず、ログに warning を出す
    with caplog.at_level("WARNING", logger="stock_analyze_system.shared.clients"):
        await dispose_clients(bundle)

    bundle.edinet.close.assert_awaited_once()
    bundle.fmp.close.assert_awaited_once()
    assert any(
        "sec" in r.getMessage() and "boom" in r.getMessage()
        for r in caplog.records
    )
