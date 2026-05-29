"""Service 組立て層の結合テスト。

setup_services() で実組み立てした ServiceContainer を使い、
in-memory SQLite 上で複数サービス協調シナリオを検証する。
外部 API クライアントはモック、LLM は呼ばない (PageIndex 無効)。
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.cli.container import setup_services
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.services.pageindex import QueryResult
from tests.integration.conftest import build_test_config


class _MockSecClient:
    def __init__(self):
        self._filings: list[dict] = []

    def set_filings(self, data: list[dict]) -> None:
        self._filings = data

    async def list_filings(self, cik: str, max_years: int = 2) -> list[dict]:
        return self._filings


@pytest.fixture
def mock_sec_client(monkeypatch):
    """container.setup_services が関数内 import する SecEdgarClient を差し替える"""
    mock = _MockSecClient()
    monkeypatch.setattr(
        "stock_analyze_system.ingestion.sec_edgar.SecEdgarClient",
        lambda **kw: mock,
    )
    return mock


@pytest.mark.integration
class TestFullSyncFlow:
    async def test_sec_filing_sync_persists_via_assembled_services(
        self, session, mock_sec_client,
    ):
        """企業登録 → SEC filing sync (mocked) → DB 永続化 → filing_service で再取得"""
        mock_sec_client.set_filings([
            {
                "accessionNumber": "0000320193-23-000106",
                "form": "10-K",
                "filingDate": "2023-11-03",
                "reportDate": "2023-09-30",
                "primaryDocument": "aapl-20230930.htm",
            },
        ])
        services = await setup_services(session, build_test_config(pageindex_enabled=False))

        await services.company_service.register_company({
            "ticker": "INTGR", "name": "Integration Corp",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
            "cik": "0000320193",
        })

        count = await services.filing_sync.update_from_sec(
            "US_INTGR", cik="0000320193",
        )
        assert count == 1

        filings = await services.filing_service.list_filings("US_INTGR")
        assert len(filings) == 1
        assert filings[0].accession_no == "0000320193-23-000106"
        assert filings[0].fiscal_year == 2023


@pytest.mark.integration
class TestWatchlistTargetFlow:
    async def test_watchlist_items_persist_across_services(self, session):
        services = await setup_services(session, build_test_config(pageindex_enabled=False))

        await services.company_service.register_company({
            "ticker": "A", "name": "A Corp",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        await services.company_service.register_company({
            "ticker": "B", "name": "B Corp",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })

        wl = await services.watchlist_service.create_watchlist(
            "Tech", description="Tech stocks",
        )
        await services.watchlist_service.add_item(wl.id, "US_A")
        await services.watchlist_service.add_item(wl.id, "US_B")

        wl_with_items = await services.watchlist_service.get_with_items(wl.id)
        company_ids = sorted(item.company_id for item in wl_with_items.items)
        assert company_ids == ["US_A", "US_B"]

    async def test_analysis_target_registration_round_trip(self, session):
        services = await setup_services(session, build_test_config(pageindex_enabled=False))

        await services.company_service.register_company({
            "ticker": "TGT", "name": "Target Corp",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })

        await services.target_service.add_target("US_TGT", source="manual")
        targets = await services.target_service.list_targets()
        assert any(t.company_id == "US_TGT" for t in targets)


@pytest.mark.integration
class TestRagAssembly:
    async def test_non_rag_features_work_when_pageindex_disabled(self, session):
        """ADR-004 amendment §B: pageindex.enabled=false でも RagService は構築される.
        旧 test 名 `test_non_rag_features_work_when_rag_disabled` から rename
        (rag_service は disabled でも non-None になったため)."""
        services = await setup_services(session, build_test_config(pageindex_enabled=False))
        assert services.rag_service is not None
        assert services.rag_service.pageindex_available is False
        assert services.company_service is not None

        await services.company_service.register_company({
            "ticker": "X", "name": "X Corp",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        company = await services.company_service.get_company("US_X")
        assert company is not None
        assert company.ticker == "X"

    async def test_rag_service_wired_when_pageindex_enabled(self, session):
        services = await setup_services(session, build_test_config(pageindex_enabled=True))
        assert services.rag_service is not None
        assert type(services.rag_service).__name__ == "RagService"

    async def test_rag_qa_history_round_trips_via_assembled_service(self, session, tmp_path):
        services = await setup_services(session, build_test_config(pageindex_enabled=True))
        assert services.rag_service is not None

        await services.company_service.register_company({
            "ticker": "RAG",
            "name": "RAG Corp",
            "market": "NASDAQ",
            "accounting_standard": "US-GAAP",
        })
        storage_path = tmp_path / "filings" / "US_RAG" / "2025"
        raw_dir = storage_path / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "primary.html").write_text("<html><body>RAG filing</body></html>")

        filing = Filing(
            company_id="US_RAG",
            source="SEC",
            filing_type="10-K",
            period_type="annual",
            fiscal_year=2025,
            storage_path=str(storage_path),
        )
        session.add(filing)
        await session.flush()

        services.rag_service._pageindex.get_or_create_index = AsyncMock(return_value={})
        services.rag_service._pageindex.query = AsyncMock(return_value=QueryResult(
            answer="Revenue increased.",
            source_pages=[3],
            source_sections=["MD&A"],
            confidence=0.75,
            model="test-model",
        ))

        await services.rag_service.ask_question(filing, "What changed?")
        history = await services.rag_service.get_qa_history("US_RAG")

        assert len(history) == 1
        assert history[0]["question"] == "What changed?"
        assert history[0]["answer"] == "Revenue increased."
        assert history[0]["source_pages"] == [3]
        assert history[0]["source_sections"] == ["MD&A"]
