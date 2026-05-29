# tests/unit/services/test_rag_service.py
"""RagService単体テスト"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.company_analysis import PIPELINE_EXTRACTOR
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.rag_qa_history import RagQaHistoryRepository
from stock_analyze_system.services.pageindex import QueryResult
from stock_analyze_system.services.filing_section_extractor import (
    ExtractionInputMissingError,
    FilingSectionExtractor,
)
from stock_analyze_system.services.rag_service import AnalysisResult, RagService
from tests.conftest import RAG_TEST_MODEL

pytestmark = pytest.mark.rag_model(RAG_TEST_MODEL)


@pytest.fixture
def pageindex_service():
    svc = AsyncMock()
    svc.query.return_value = QueryResult(
        answer='{"summary": "test"}',
        source_pages=[1, 2],
        source_sections=["Section 1"],
        confidence=0.9,
        model=RAG_TEST_MODEL,
    )
    return svc


@pytest.fixture
def analysis_repo():
    repo = AsyncMock()
    repo.get_by_type.return_value = None
    return repo


@pytest.fixture
def filing_content_service():
    svc = AsyncMock()

    async def _ensure_content(filing):
        filing.storage_path = "/data/auto/fetched"
        return filing

    svc.ensure_content.side_effect = _ensure_content
    return svc


@pytest.fixture
def llm_client():
    client = AsyncMock()
    client.health_check.return_value = {"status": "ok", "model": "test", "backend": "ollama", "base_url": "http://localhost:11434"}
    client.completion = AsyncMock(return_value='{"summary": "test"}')
    client.resolve_model = MagicMock(return_value=RAG_TEST_MODEL)
    return client


@pytest.fixture
def section_extractor_default():
    """ADR-004: 定型分析 4 種が常に章テキストを得られる前提のデフォルト fake."""
    ext = AsyncMock()
    ext.extract.return_value = {
        "business_summary": "Business: deterministic section text.",
        "risk_factors": "Risks: deterministic section text.",
        "mda": "MD&A: deterministic section text.",
        "competitors": "Competition: deterministic section text.",
    }
    return ext


@pytest.fixture
def service(
    pageindex_service,
    analysis_repo,
    llm_client,
    filing_content_service,
    section_extractor_default,
):
    return RagService(
        pageindex_service=pageindex_service,
        analysis_repo=analysis_repo,
        llm_client=llm_client,
        filing_content_service=filing_content_service,
        section_extractor=section_extractor_default,
    )


class TestRunAnalysis:
    async def test_run_analysis_json_decode_error(self, service, llm_client):
        llm_client.completion = AsyncMock(return_value="not valid json")

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        result = await service.run_analysis(filing, "business_summary")

        assert isinstance(result, AnalysisResult)
        assert result.result_json == {"raw_answer": "not valid json"}

    async def test_runs_single_analysis(
        self, service, section_extractor_default, pageindex_service, llm_client,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        result = await service.run_analysis(filing, "business_summary")

        assert isinstance(result, AnalysisResult)
        assert result.analysis_type == "business_summary"
        section_extractor_default.extract.assert_awaited_once_with(filing)
        llm_client.completion.assert_awaited_once()
        pageindex_service.get_or_create_index.assert_not_called()
        pageindex_service.query.assert_not_called()
        service._analysis_repo.upsert.assert_called_once()
        filters = service._analysis_repo.upsert.call_args.args[0]
        assert filters["pipeline"] == PIPELINE_EXTRACTOR

    async def test_unknown_analysis_type_raises(self, service):
        filing = MagicMock()
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"
        with pytest.raises(ValueError, match="Unknown analysis type"):
            await service.run_analysis(filing, "nonexistent")


class TestRunFullAnalysis:
    async def test_runs_all_4_types(self, service, pageindex_service):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        results = await service.run_full_analysis(filing)

        assert len(results) == 4
        types = {r.analysis_type for r in results}
        assert types == {"business_summary", "risk_factors", "mda", "competitors"}
        assert service._analysis_repo.upsert.call_count == 4

    async def test_returns_cached_analysis(
        self, service, analysis_repo, pageindex_service,
    ):
        cached = MagicMock()
        cached.analysis_type = "business_summary"
        cached.result_json = '{"summary": "cached"}'
        analysis_repo.get_by_type.return_value = cached

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        results = await service.run_full_analysis(filing)
        # All 4 types attempted, but business_summary uses cache
        assert len(results) == 4
        pageindex_service.query.assert_not_called()

    async def test_run_full_analysis_partial_cache(
        self, service, analysis_repo, llm_client,
    ):
        cached = MagicMock()
        cached.analysis_type = "business_summary"
        cached.result_json = '{"summary": "cached"}'
        cached.model_name = RAG_TEST_MODEL
        # First call returns cached, remaining 3 return None
        analysis_repo.get_by_type.side_effect = [cached, None, None, None]

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        results = await service.run_full_analysis(filing)

        assert len(results) == 4
        # Only 3 uncached types should have triggered the LLM call
        assert llm_client.completion.call_count == 3

    async def test_run_full_analysis_json_decode_in_loop(
        self, service, analysis_repo, llm_client,
    ):
        llm_client.completion = AsyncMock(return_value="not json")
        analysis_repo.get_by_type.return_value = None

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        results = await service.run_full_analysis(filing)

        assert len(results) == 4
        for r in results:
            assert r.result_json == {"raw_answer": "not json"}

    async def test_run_full_analysis_propagates_runtime_errors(
        self, service, llm_client, analysis_repo,
    ):
        """ADR-004: run_full_analysis (CLI 経路) は章欠落だけ silent skip し、
        LLM/save/cache の runtime 失敗は raise を保持する。stream の
        per-type error event とは異なる契約。"""
        llm_client.completion = AsyncMock(return_value="")
        analysis_repo.get_by_type.return_value = None

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.filing_type = "10-K"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        with pytest.raises(ValueError, match="empty"):
            await service.run_full_analysis(filing)

    async def test_empty_llm_response_raises_not_cached_as_success(
        self, service, llm_client, analysis_repo,
    ):
        """ADR-004 review: empty LLM content (Qwen3.6 reasoning_content runaway
        の典型症状) を成功キャッシュに含めない。raise → worker が failed_types
        に積む経路に流す。"""
        llm_client.completion = AsyncMock(return_value="")
        analysis_repo.get_by_type.return_value = None

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.filing_type = "10-K"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        with pytest.raises(ValueError, match="empty"):
            await service.run_analysis(filing, "business_summary")

        analysis_repo.upsert.assert_not_called()

    async def test_run_analysis_saves_structural_placeholder_when_raw_html_missing(
        self, pageindex_service, analysis_repo, llm_client, tmp_path,
    ):
        """10-Q の構造上存在しないタイプは raw HTML 欠落時も placeholder を残す."""
        (tmp_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=None,
            section_extractor=FilingSectionExtractor(),
        )
        filing = MagicMock()
        filing.id = 10
        filing.company_id = "US_AAPL"
        filing.source = "SEC"
        filing.filing_type = "10-Q"
        filing.storage_path = str(tmp_path)

        result = await service.run_analysis(filing, "business_summary")

        assert result.analysis_type == "business_summary"
        assert result.result_json["_status"] == "not_applicable"
        filters = analysis_repo.upsert.await_args.args[0]
        assert filters["analysis_type"] == "business_summary"
        assert filters["pipeline"] == PIPELINE_EXTRACTOR

    async def test_run_analysis_raises_when_raw_html_missing_for_required_type(
        self, pageindex_service, analysis_repo, llm_client, tmp_path,
    ):
        (tmp_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=None,
            section_extractor=FilingSectionExtractor(),
        )
        filing = MagicMock()
        filing.id = 11
        filing.company_id = "US_AAPL"
        filing.source = "SEC"
        filing.filing_type = "10-Q"
        filing.storage_path = str(tmp_path)

        with pytest.raises(ExtractionInputMissingError, match="raw HTML"):
            await service.run_analysis(filing, "risk_factors")
        analysis_repo.upsert.assert_not_called()

    async def test_run_full_analysis_raises_when_raw_html_missing(
        self, pageindex_service, analysis_repo, llm_client, tmp_path,
    ):
        """converted.pdf だけの filing は成功空結果ではなく入力欠落で fail-fast."""
        (tmp_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=None,
            section_extractor=FilingSectionExtractor(),
        )
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.source = "SEC"
        filing.filing_type = "10-K"
        filing.storage_path = str(tmp_path)

        with pytest.raises(ExtractionInputMissingError, match="raw HTML"):
            await service.run_full_analysis(filing)
        analysis_repo.upsert.assert_not_called()

    async def test_run_full_analysis_saves_structural_placeholders_before_raw_html_missing_raise(
        self, pageindex_service, analysis_repo, llm_client, tmp_path,
    ):
        """fail-fast は維持しつつ、旧来の構造上空 placeholder cache は保存する."""
        (tmp_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=None,
            section_extractor=FilingSectionExtractor(),
        )
        filing = MagicMock()
        filing.id = 12
        filing.company_id = "US_AAPL"
        filing.source = "SEC"
        filing.filing_type = "10-Q"
        filing.storage_path = str(tmp_path)

        with pytest.raises(ExtractionInputMissingError, match="raw HTML"):
            await service.run_full_analysis(filing)

        saved_types = [
            call.args[0]["analysis_type"]
            for call in analysis_repo.upsert.await_args_list
        ]
        assert saved_types == ["business_summary", "competitors"]


class TestUnsupportedExtractorFilings:
    async def test_run_full_analysis_rejects_edinet_pdf_filing(
        self, service, analysis_repo,
    ):
        from stock_analyze_system.services.rag_service import (
            UnsupportedFilingForExtractorError,
        )

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "JP_7203"
        filing.source = "EDINET"
        filing.filing_type = "annual_report"
        filing.storage_path = "/data/edinet"

        with pytest.raises(UnsupportedFilingForExtractorError, match="SEC"):
            await service.run_full_analysis(filing)

        analysis_repo.upsert.assert_not_called()

    async def test_run_analysis_rejects_edinet_pdf_filing(
        self, service, analysis_repo,
    ):
        from stock_analyze_system.services.rag_service import (
            UnsupportedFilingForExtractorError,
        )

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "JP_7203"
        filing.source = "EDINET"
        filing.filing_type = "annual_report"
        filing.storage_path = "/data/edinet"

        with pytest.raises(UnsupportedFilingForExtractorError, match="annual_report"):
            await service.run_analysis(filing, "business_summary")

        analysis_repo.upsert.assert_not_called()

    async def test_stream_yields_error_complete_for_unsupported_filing(
        self, service, analysis_repo,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "JP_7203"
        filing.source = "EDINET"
        filing.filing_type = "annual_report"
        filing.storage_path = "/data/edinet"

        events = [evt async for evt in service.run_full_analysis_stream(filing)]

        assert [evt["event"] for evt in events] == ["error", "complete"]
        assert events[0]["analysis_type"] is None
        assert "annual_report" in events[0]["message"]
        analysis_repo.upsert.assert_not_called()


class TestAskQuestion:
    async def test_ask_returns_query_result(self, service, pageindex_service):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        result = await service.ask_question(filing, "What is the revenue?")

        assert isinstance(result, QueryResult)
        assert result.answer == '{"summary": "test"}'
        pageindex_service.get_or_create_index.assert_called_once()
        pageindex_service.query.assert_called_once()

    async def test_ask_persists_qa_history(
        self, pageindex_service, analysis_repo, llm_client,
    ):
        qa_history_repo = AsyncMock()
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            qa_history_repo=qa_history_repo,
        )
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        await service.ask_question(filing, "What is the revenue?")

        qa_history_repo.add.assert_awaited_once_with(
            company_id="US_AAPL",
            filing_id=1,
            question="What is the revenue?",
            answer='{"summary": "test"}',
            source_pages=[1, 2],
            source_sections=["Section 1"],
            model_name=RAG_TEST_MODEL,
            confidence=0.9,
        )

    async def test_ask_history_persistence_failure_keeps_session_usable(
        self, session, pageindex_service, analysis_repo, llm_client,
    ):
        class FailingAfterFlushRagQaHistoryRepository(RagQaHistoryRepository):
            async def add(self, **kwargs):
                row = await super().add(**kwargs)
                self._session.add(Company(
                    id="US_AAPL",
                    ticker="DUP",
                    name="Duplicate Corp",
                    market="NASDAQ",
                    accounting_standard="US-GAAP",
                ))
                await self._session.flush()
                return row

        session.add(Company(
            id="US_AAPL",
            ticker="AAPL",
            name="Apple",
            market="NASDAQ",
            accounting_standard="US-GAAP",
        ))
        await session.flush()
        filing = Filing(
            company_id="US_AAPL",
            source="SEC",
            filing_type="10-K",
            period_type="annual",
            fiscal_year=2025,
            storage_path="/data/filings/sec/US_AAPL/2025",
        )
        session.add(filing)
        await session.flush()

        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            qa_history_repo=FailingAfterFlushRagQaHistoryRepository(session),
        )

        result = await service.ask_question(filing, "What is the revenue?")

        assert result.answer == '{"summary": "test"}'

        session.add(Company(
            id="US_NEXT",
            ticker="NEXT",
            name="Next Corp",
            market="NASDAQ",
            accounting_standard="US-GAAP",
        ))
        await session.flush()
        persisted = await session.scalar(select(Company).where(Company.id == "US_NEXT"))
        assert persisted is not None

    async def test_get_qa_history_returns_empty_when_repository_unavailable(
        self, service,
    ):
        assert await service.get_qa_history("US_AAPL") == []


class TestGetIndexStatus:
    async def test_returns_index_list(self, service, pageindex_service):
        idx = MagicMock()
        idx.filing_id = 1
        idx.model_name = RAG_TEST_MODEL
        idx.page_count = 50
        idx.node_count = 10
        idx.created_at = "2026-03-22"
        pageindex_service.get_indices_for_company.return_value = [idx]

        result = await service.get_index_status("US_AAPL")

        assert len(result) == 1
        assert result[0]["filing_id"] == 1
        assert result[0]["node_count"] == 10


class TestGetAnalyses:
    async def test_returns_analyses_list(self, service):
        a = MagicMock()
        a.analysis_type = "business_summary"
        a.result_json = '{"summary": "test"}'
        a.model_name = RAG_TEST_MODEL
        a.created_at = "2026-03-22"
        service._analysis_repo.get_analyses.return_value = [a]

        result = await service.get_analyses("US_AAPL", 1)

        assert len(result) == 1
        assert result[0]["analysis_type"] == "business_summary"
        assert result[0]["result_json"] == {"summary": "test"}

    async def test_get_analyses_empty(self, service):
        service._analysis_repo.get_analyses.return_value = []

        result = await service.get_analyses("US_AAPL", 1)

        assert result == []


class TestHealthCheck:
    async def test_health_delegates_to_llm_client(self, service, llm_client):
        result = await service.health_check()
        assert result["status"] == "ok"
        llm_client.health_check.assert_called_once()


class TestEnsureFilingContent:
    async def test_build_index_auto_fetches_when_storage_missing(
        self, service, filing_content_service, pageindex_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None

        await service.build_index(filing)

        filing_content_service.ensure_content.assert_awaited_once_with(filing)
        pageindex_service.get_or_create_index.assert_called_once_with(filing)

    async def test_run_analysis_auto_fetches_when_storage_missing(
        self, service, filing_content_service, section_extractor_default,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None

        await service.run_analysis(filing, "business_summary")

        filing_content_service.ensure_content.assert_awaited_once_with(filing)
        section_extractor_default.extract.assert_awaited_once()

    async def test_run_full_analysis_auto_fetches_when_storage_missing(
        self, service, filing_content_service, section_extractor_default,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None

        await service.run_full_analysis(filing)

        filing_content_service.ensure_content.assert_awaited_once_with(filing)
        section_extractor_default.extract.assert_awaited_once()

    async def test_run_full_analysis_auto_fetches_when_sec_has_only_pdf(
        self, service, filing_content_service, section_extractor_default, tmp_path,
    ):
        (tmp_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.source = "SEC"
        filing.filing_type = "10-K"
        filing.storage_path = str(tmp_path)

        await service.run_full_analysis(filing)

        filing_content_service.ensure_content.assert_awaited_once_with(filing)
        section_extractor_default.extract.assert_awaited_once()

    async def test_ask_question_auto_fetches_when_storage_missing(
        self, service, filing_content_service, pageindex_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None

        await service.ask_question(filing, "test?")

        filing_content_service.ensure_content.assert_awaited_once_with(filing)
        pageindex_service.get_or_create_index.assert_called_once_with(filing)


class TestRunFullAnalysisStream:
    async def test_iteration_events_emits_error_when_cached_json_invalid(
        self, service, analysis_repo,
    ):
        """壊れた cached.result_json (手動投入や旧スキーマ残骸) で
        _cached_to_result が json.JSONDecodeError を投げても、generator 外に
        漏らさず per-type error event に変換すること。漏らすと worker は
        generic Exception ハンドラに落ち per-type の進捗が止まる。"""
        broken = MagicMock()
        broken.model_name = RAG_TEST_MODEL
        broken.result_json = "not json"
        analysis_repo.get_by_type.return_value = broken

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_X"
        filing.filing_type = "10-K"
        sections = {
            "business_summary": "x", "risk_factors": "x",
            "mda": "x", "competitors": "x",
        }

        events = [
            e async for e in service._iteration_events(
                filing, 0, 4, "business_summary", sections,
            )
        ]
        kinds = [e["event"] for e in events]
        assert "error" in kinds
        err = next(e for e in events if e["event"] == "error")
        assert err["analysis_type"] == "business_summary"

    async def test_iteration_events_is_async_generator(self, service):
        """per-type ループは async generator で 1 イベントずつ yield されなければ
        ならない (list を返す coroutine 化すると worker の update_progress が
        バースト書きになり live UI 進捗が崩れる)。"""
        import inspect

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.filing_type = "10-K"
        sections = {
            "business_summary": "x", "risk_factors": "x",
            "mda": "x", "competitors": "x",
        }
        result = service._iteration_events(filing, 0, 4, "business_summary", sections)
        assert inspect.isasyncgen(result), (
            f"Expected async generator, got {type(result).__name__}"
        )

    async def test_emits_fetching_then_extracting_when_storage_missing(
        self, service, filing_content_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        kinds = [e["event"] for e in events]

        assert kinds[0] == "fetching"
        # ADR-004: section extractor phase replaces PageIndex indexing phase.
        assert kinds[1] == "extracting"
        assert kinds[2] == "started"
        assert kinds[-1] == "complete"
        filing_content_service.ensure_content.assert_awaited_once_with(filing)

    async def test_skips_fetch_when_storage_content_exists(
        self, service, filing_content_service, tmp_path,
    ):
        storage_dir = tmp_path / "filing"
        (storage_dir / "raw").mkdir(parents=True)
        (storage_dir / "raw" / "filing.htm").write_text("present")
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = str(storage_dir)

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        kinds = [e["event"] for e in events]

        assert "fetching" not in kinds
        filing_content_service.ensure_content.assert_not_called()

    async def test_re_fetches_when_storage_path_is_stale(
        self, service, filing_content_service, tmp_path,
    ):
        stale_dir = tmp_path / "stale"
        stale_dir.mkdir()
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = str(stale_dir)

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        kinds = [e["event"] for e in events]

        assert kinds[0] == "fetching"
        filing_content_service.ensure_content.assert_awaited_once_with(filing)

    async def test_emits_fetching_error_complete_when_fetch_fails(
        self, service, filing_content_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None
        filing_content_service.ensure_content.side_effect = RuntimeError("boom")

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        kinds = [e["event"] for e in events]

        assert kinds == ["fetching", "error", "complete"]
        assert events[1]["analysis_type"] is None
        assert "本体取得に失敗しました: boom" == events[1]["message"]

    async def test_emits_download_error_when_no_content_service(
        self, pageindex_service, analysis_repo, llm_client,
    ):
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=None,
        )
        filing = MagicMock()
        filing.id = 1
        filing.storage_path = None

        events = [evt async for evt in service.run_full_analysis_stream(filing)]

        assert [e["event"] for e in events] == ["error", "complete"]
        assert events[0]["analysis_type"] is None
        assert "filings download" in events[0]["message"]

    async def test_preflight_uses_llm_completion_not_pageindex(
        self, service, pageindex_service, llm_client,
    ):
        """ADR-004 alignment: preflight は step 3 と同じ LlmClient.completion を
        小さな probe で叩く。PageIndex.preflight は ask_question 用に独立。"""
        pageindex_service.preflight = AsyncMock(return_value={"status": "should_not_be_called"})
        llm_client.completion = AsyncMock(return_value="ok")

        result = await service.preflight()

        assert result["status"] == "ok"
        llm_client.completion.assert_awaited_once()
        pageindex_service.preflight.assert_not_called()

    async def test_preflight_returns_error_when_llm_returns_empty(
        self, service, llm_client,
    ):
        """空応答 (Qwen3.6 reasoning_content 暴走の典型症状) は status=error."""
        llm_client.completion = AsyncMock(return_value="")

        result = await service.preflight()

        assert result["status"] == "error"
        assert "empty" in result.get("reason", "").lower()

    async def test_preflight_returns_error_when_llm_raises(
        self, service, llm_client,
    ):
        """LLM が例外を投げたら status=error で reason に str(exc) を載せる."""
        llm_client.completion = AsyncMock(side_effect=RuntimeError("Connection refused"))

        result = await service.preflight()

        assert result["status"] == "error"
        assert "Connection refused" in result.get("reason", "")

    async def test_section_extractor_error_flows_to_error_event(
        self, service, section_extractor_default, filing_content_service, tmp_path,
    ):
        """ADR-004: FilingSectionExtractor が例外を出したら error イベントに変換する.

        旧 PageIndex の IndexBuildError(diagnostic=...) 経路は定型分析からは外れたが、
        extractor 段の失敗 (HTML 破損 / parse 例外) は同様に 1 つの error イベントで
        全 4 タイプ分の analysis を止める設計を維持する."""
        storage_dir = tmp_path / "filing"
        (storage_dir / "raw").mkdir(parents=True)
        (storage_dir / "raw" / "filing.htm").write_text("present")
        filing = MagicMock()
        filing.id = 99
        filing.company_id = "US_RXRX"
        filing.storage_path = str(storage_dir)

        section_extractor_default.extract.side_effect = RuntimeError(
            "Unable to parse filing HTML",
        )

        events = [evt async for evt in service.run_full_analysis_stream(filing)]

        assert [e["event"] for e in events] == ["extracting", "error", "complete"]
        err_evt = events[1]
        assert err_evt["analysis_type"] is None
        assert "Unable to parse filing HTML" in err_evt["message"]

    async def test_raw_html_missing_flows_to_extraction_error_event(
        self, pageindex_service, analysis_repo, llm_client, tmp_path,
    ):
        """raw HTML 欠落は per-type error ではなく extraction-level error."""
        (tmp_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=None,
            section_extractor=FilingSectionExtractor(),
        )
        filing = MagicMock()
        filing.id = 99
        filing.company_id = "US_RXRX"
        filing.filing_type = "10-K"
        filing.storage_path = str(tmp_path)

        events = [evt async for evt in service.run_full_analysis_stream(filing)]

        assert [e["event"] for e in events] == ["extracting", "error", "complete"]
        err_evt = events[1]
        assert err_evt["analysis_type"] is None
        assert "raw HTML" in err_evt["message"]


class TestRunFullAnalysisViaSectionExtractor:
    """ADR-004: 定型分析は FilingSectionExtractor + LlmClient.completion 経路を使う."""

    @pytest.fixture
    def section_extractor(self):
        ext = AsyncMock()
        ext.extract.return_value = {
            "business_summary": "Business: We sell widgets.",
            "risk_factors": "Risks: market volatility.",
            "mda": "MD&A: Revenue grew 10%.",
            "competitors": "Competition: rival X is the main threat.",
        }
        return ext

    @pytest.fixture
    def extractor_service(
        self,
        pageindex_service,
        analysis_repo,
        llm_client,
        filing_content_service,
        section_extractor,
    ):
        llm_client.completion = AsyncMock(return_value='{"summary": "ok"}')
        llm_client.resolve_model = MagicMock(return_value=RAG_TEST_MODEL)
        return RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=filing_content_service,
            section_extractor=section_extractor,
        )

    async def test_run_full_analysis_uses_extractor_not_pageindex(
        self,
        extractor_service,
        section_extractor,
        pageindex_service,
        llm_client,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/storage"
        filing.filing_type = "10-K"

        results = await extractor_service.run_full_analysis(filing)

        assert len(results) == 4
        section_extractor.extract.assert_awaited_once_with(filing)
        pageindex_service.get_or_create_index.assert_not_called()
        pageindex_service.query.assert_not_called()
        assert llm_client.completion.await_count == 4


class TestStructurallyEmptySections:
    """ADR-004 review fix: 10-Q business_summary / competitors と 6-K
    risk_factors / competitors は filing 種別の構造上空になる。これを worker が
    失敗扱いしないよう、stream は `skipped` を emit し、非 stream はキャッシュに
    placeholder を残し、両者の挙動を揃える。"""

    @pytest.fixture
    def extractor_10q(self):
        ext = AsyncMock()
        ext.extract.return_value = {
            "business_summary": "",  # 10-Q structural absence
            "risk_factors": "Risks: market headwinds.",
            "mda": "MD&A: revenue declined.",
            "competitors": "",  # 10-Q structural absence
        }
        return ext

    @pytest.fixture
    def service_10q(
        self,
        pageindex_service,
        analysis_repo,
        llm_client,
        filing_content_service,
        extractor_10q,
    ):
        llm_client.completion = AsyncMock(return_value='{"summary": "ok"}')
        llm_client.resolve_model = MagicMock(return_value=RAG_TEST_MODEL)
        return RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=filing_content_service,
            section_extractor=extractor_10q,
        )

    async def test_stream_emits_skipped_not_error_for_10q_structural_absence(
        self, service_10q,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_TEM"
        filing.filing_type = "10-Q"
        filing.storage_path = "/data/storage"

        events = [e async for e in service_10q.run_full_analysis_stream(filing)]
        # Strip routing-only events; keep per-analysis outcomes.
        outcomes = [(e.get("event"), e.get("analysis_type"))
                    for e in events
                    if e.get("event") in ("done", "skipped", "cached", "error")]

        assert ("skipped", "business_summary") in outcomes
        assert ("skipped", "competitors") in outcomes
        assert ("done", "risk_factors") in outcomes
        assert ("done", "mda") in outcomes
        # Worker promotes `error` to failed_types; structural absences must NOT
        # take that path.
        assert not any(kind == "error" for kind, _ in outcomes)

    async def test_nonstream_returns_placeholder_for_structural_absence(
        self, service_10q,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_TEM"
        filing.filing_type = "10-Q"
        filing.storage_path = "/data/storage"

        results = await service_10q.run_full_analysis(filing)

        # All 4 analysis types are accounted for (no silent skip).
        by_type = {r.analysis_type: r for r in results}
        assert set(by_type) == {"business_summary", "risk_factors", "mda", "competitors"}
        # Structural absences carry a not_applicable sentinel so the UI can
        # render "適用外" and the cache hit on next run avoids recomputation.
        assert by_type["business_summary"].result_json.get("_status") == "not_applicable"
        assert by_type["competitors"].result_json.get("_status") == "not_applicable"
        assert by_type["mda"].result_json.get("_status") != "not_applicable"

    async def test_stream_emits_skipped_when_cached_row_is_placeholder(
        self,
        pageindex_service,
        analysis_repo,
        llm_client,
        filing_content_service,
        extractor_10q,
    ):
        """ADR-004 review fix: 過去 run で placeholder を cache に残した場合、
        次回 run は `cached` ではなく `skipped` を emit する (label の整合性)。
        cached だと UI が "(キャッシュ使用)" を表示してしまい placeholder と
        誤認させるため、structural placeholder は常に `skipped` で通す。"""
        from stock_analyze_system.services.rag_service import _PLACEHOLDER_MODEL

        # 過去 run で保存された placeholder 行を模した cached object
        placeholder_cached = MagicMock()
        placeholder_cached.model_name = _PLACEHOLDER_MODEL
        placeholder_cached.result_json = '{"_status": "not_applicable"}'

        # business_summary はキャッシュ済 placeholder、他は通常
        def get_by_type(_company_id, _filing_id, atype):
            if atype == "business_summary":
                return placeholder_cached
            return None

        analysis_repo.get_by_type.side_effect = get_by_type
        llm_client.completion = AsyncMock(return_value='{"summary": "ok"}')
        llm_client.resolve_model = MagicMock(return_value=RAG_TEST_MODEL)
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=filing_content_service,
            section_extractor=extractor_10q,
        )

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_TEM"
        filing.filing_type = "10-Q"
        filing.storage_path = "/data/storage"

        events = [e async for e in service.run_full_analysis_stream(filing)]
        outcomes = [(e.get("event"), e.get("analysis_type"))
                    for e in events
                    if e.get("event") in ("done", "skipped", "cached", "error")]

        # cached placeholder は skipped として通す。"cached" ではない。
        assert ("skipped", "business_summary") in outcomes
        assert ("cached", "business_summary") not in outcomes

    async def test_nonstream_skips_unexpected_empty_section_rather_than_raising(
        self,
        pageindex_service,
        analysis_repo,
        llm_client,
        filing_content_service,
    ):
        """CLI rag analyze は部分結果を返したい。10-K で 1 章が取り逃しになっても、
        残りの 3 章は処理して results に積み、最後に返す (stream 挙動と整合)。"""
        ext = AsyncMock()
        ext.extract.return_value = {
            "business_summary": "",  # 10-K では本来あるべき — 取りこぼし
            "risk_factors": "Risk text",
            "mda": "MDA text",
            "competitors": "Competition text",
        }
        analysis_repo.get_by_type.return_value = None
        llm_client.completion = AsyncMock(return_value='{"summary": "ok"}')
        llm_client.resolve_model = MagicMock(return_value=RAG_TEST_MODEL)
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=filing_content_service,
            section_extractor=ext,
        )
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_RXRX"
        filing.filing_type = "10-K"
        filing.storage_path = "/data/storage"

        results = await service.run_full_analysis(filing)

        # 3 件は通り、business_summary は (raise せず) 結果から欠落する
        by_type = {r.analysis_type for r in results}
        assert by_type == {"risk_factors", "mda", "competitors"}

    async def test_stream_emits_error_for_unexpected_empty_section(
        self,
        pageindex_service,
        analysis_repo,
        llm_client,
        filing_content_service,
    ):
        """10-K の business_summary が空なのは extractor の取りこぼし — error."""
        ext = AsyncMock()
        ext.extract.return_value = {
            "business_summary": "",  # 10-K では構造上必ずある — 取りこぼし
            "risk_factors": "ok",
            "mda": "ok",
            "competitors": "ok",
        }
        llm_client.completion = AsyncMock(return_value='{"summary": "ok"}')
        llm_client.resolve_model = MagicMock(return_value=RAG_TEST_MODEL)
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=filing_content_service,
            section_extractor=ext,
        )
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_RXRX"
        filing.filing_type = "10-K"
        filing.storage_path = "/data/storage"

        events = [e async for e in service.run_full_analysis_stream(filing)]
        error_events = [e for e in events
                        if e.get("event") == "error"
                        and e.get("analysis_type") == "business_summary"]

        assert len(error_events) == 1


class TestAnalysisResult:
    def test_to_dict(self):
        qr = QueryResult(
            answer="test", source_pages=[1], source_sections=["S1"],
            confidence=0.9, model="m",
        )
        ar = AnalysisResult(
            analysis_type="business_summary", result_json={"key": "val"},
            query_result=qr,
        )
        d = ar.to_dict()
        assert d["analysis_type"] == "business_summary"
        assert d["result_json"] == {"key": "val"}
        assert d["query_result"]["answer"] == "test"


class TestPageIndexIndependence:
    """ADR-004 amendment §B: pageindex_service=None でも定型分析は動く。
    PageIndex 経路は明示的なエラーで disabled を伝える."""

    @pytest.fixture
    def service_no_pageindex(
        self,
        analysis_repo,
        llm_client,
        filing_content_service,
        section_extractor_default,
    ):
        return RagService(
            pageindex_service=None,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            qa_history_repo=None,
            filing_content_service=filing_content_service,
            section_extractor=section_extractor_default,
        )

    async def test_run_full_analysis_works_without_pageindex(
        self, service_no_pageindex,
    ):
        # pageindex_available property は Step 3.4 で追加. 実装前は AttributeError
        # で fail し、test が red になることを保証する (定型分析自体は _pageindex を
        # 触らないので、property assertion 無しだと現行実装で偶発 pass する).
        assert service_no_pageindex.pageindex_available is False

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/auto/fetched"
        filing.filing_type = "10-K"

        results = await service_no_pageindex.run_full_analysis(filing)
        # extractor は 4 種すべて返す fixture なので 4 件返る
        assert len(results) == 4
        types = {r.analysis_type for r in results}
        assert types == {"business_summary", "risk_factors", "mda", "competitors"}

    async def test_run_full_analysis_stream_works_without_pageindex(
        self, service_no_pageindex,
    ):
        assert service_no_pageindex.pageindex_available is False

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/auto/fetched"
        filing.filing_type = "10-K"

        events = [e async for e in service_no_pageindex.run_full_analysis_stream(filing)]
        # 最後が complete、途中に extracting / started / phase / done が出る
        assert events[-1] == {"event": "complete"}
        assert any(e.get("event") == "extracting" for e in events)
        assert any(e.get("event") == "done" for e in events)

    async def test_ask_question_raises_when_pageindex_disabled(
        self, service_no_pageindex,
    ):
        from stock_analyze_system.services.rag_service import PageIndexDisabledError
        filing = MagicMock()
        filing.storage_path = "/data/auto/fetched"
        with pytest.raises(PageIndexDisabledError):
            await service_no_pageindex.ask_question(filing, "What is the revenue?")

    async def test_build_index_raises_when_pageindex_disabled(
        self, service_no_pageindex,
    ):
        from stock_analyze_system.services.rag_service import PageIndexDisabledError
        filing = MagicMock()
        filing.storage_path = "/data/auto/fetched"
        with pytest.raises(PageIndexDisabledError):
            await service_no_pageindex.build_index(filing)

    async def test_get_index_status_raises_when_pageindex_disabled(
        self, service_no_pageindex,
    ):
        from stock_analyze_system.services.rag_service import PageIndexDisabledError
        with pytest.raises(PageIndexDisabledError):
            await service_no_pageindex.get_index_status("US_AAPL")
