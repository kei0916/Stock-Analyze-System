"""RAG CLIハンドラテスト"""
from __future__ import annotations

import argparse
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli.rag import handle
from stock_analyze_system.services.pageindex import QueryResult
from stock_analyze_system.services.rag_service import AnalysisResult
from tests.conftest import RAG_TEST_MODEL

pytestmark = pytest.mark.rag_model(RAG_TEST_MODEL)


@pytest.fixture
def services():
    svc = MagicMock()
    svc.rag_service = AsyncMock()
    svc.filing_service = AsyncMock()
    svc.company_service = AsyncMock()

    company = MagicMock()
    company.id = "US_AAPL"
    company.name = "Apple Inc."
    svc.company_service.get_company.return_value = company

    filing = MagicMock()
    filing.id = 1
    filing.company_id = "US_AAPL"
    filing.source = "SEC"
    filing.storage_path = "/data/filings/sec/US_AAPL/2025"
    svc.filing_service.get_latest_filing.return_value = filing

    return svc


def make_args(**kwargs):
    args = MagicMock()
    args.json = False
    args.quality = False
    args.model = None
    args.all_companies = False
    for k, v in kwargs.items():
        setattr(args, k, v)
    return args


class TestRagHealth:
    async def test_health_ok(self, services, capsys):
        services.rag_service.health_check.return_value = {
            "status": "ok", "model": "test", "backend": "ollama",
            "base_url": "http://localhost:11434",
        }
        args = make_args(action="health")
        await handle(args, services)

        captured = capsys.readouterr()
        assert "ok" in captured.out
        services.rag_service.health_check.assert_called_once()


class TestRagIndex:
    async def test_index_builds(self, services, capsys):
        tree = {"title": "Doc", "nodes": [
            {"title": "S1"}, {"title": "S2"},
        ]}
        services.rag_service.build_index.return_value = tree

        args = make_args(action="index", company_id="US_AAPL")
        await handle(args, services)

        services.rag_service.build_index.assert_called_once()
        captured = capsys.readouterr()
        assert "2 nodes" in captured.out
        assert "in " in captured.out  # timing present

    async def test_index_logs_fetch_progress_when_storage_missing(
        self, services, capsys,
    ):
        services.filing_service.get_latest_filing.return_value.storage_path = None
        tree = {"title": "Doc", "nodes": []}
        services.rag_service.build_index.return_value = tree

        args = make_args(action="index", company_id="US_AAPL", filing_type="annual_report")
        await handle(args, services)

        captured = capsys.readouterr()
        assert "Filing content not present; fetching from SEC..." in captured.out


class TestRagAnalyze:
    async def test_analyze_runs_all(self, services, capsys):
        qr = QueryResult(
            answer="test", source_pages=[1], source_sections=["S1"],
            confidence=0.9, model="m",
        )
        results = [
            AnalysisResult("business_summary", {"summary": "test"}, qr),
        ]
        services.rag_service.run_full_analysis.return_value = results

        args = make_args(action="analyze", company_id="US_AAPL", type=None)
        await handle(args, services)

        captured = capsys.readouterr()
        assert "business_summary" in captured.out

    async def test_analyze_json_does_not_emit_fetch_progress(
        self, services, capsys,
    ):
        services.filing_service.get_latest_filing.return_value.storage_path = None
        qr = QueryResult(
            answer="test", source_pages=[1], source_sections=["S1"],
            confidence=0.9, model="m",
        )
        results = [
            AnalysisResult("business_summary", {"summary": "test"}, qr),
        ]
        services.rag_service.run_full_analysis.return_value = results

        args = make_args(
            action="analyze", company_id="US_AAPL", type=None, json=True,
            filing_type="annual_report",
        )
        await handle(args, services)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["analysis_type"] == "business_summary"
        assert "Filing content not present" not in captured.out


class TestRagAsk:
    async def test_ask_question(self, services, capsys):
        qr = QueryResult(
            answer="Revenue was $100B",
            source_pages=[5, 6],
            source_sections=["Revenue"],
            confidence=0.9,
            model=RAG_TEST_MODEL,
        )
        services.rag_service.ask_question.return_value = qr

        args = make_args(
            action="ask", company_id="US_AAPL", question="What was revenue?",
        )
        await handle(args, services)

        captured = capsys.readouterr()
        assert "100B" in captured.out

    async def test_ask_logs_fetch_progress_when_storage_missing(
        self, services, capsys,
    ):
        services.filing_service.get_latest_filing.return_value.storage_path = None
        qr = QueryResult(
            answer="Revenue was $100B",
            source_pages=[5, 6],
            source_sections=["Revenue"],
            confidence=0.9,
            model=RAG_TEST_MODEL,
        )
        services.rag_service.ask_question.return_value = qr

        args = make_args(
            action="ask", company_id="US_AAPL", question="What was revenue?",
            filing_type="annual_report",
        )
        await handle(args, services)

        captured = capsys.readouterr()
        assert "Filing content not present; fetching from SEC..." in captured.out

    async def test_ask_json_output_is_not_corrupted_by_progress(
        self, services, capsys,
    ):
        services.filing_service.get_latest_filing.return_value.storage_path = None
        qr = QueryResult(
            answer="Revenue was $100B",
            source_pages=[5, 6],
            source_sections=["Revenue"],
            confidence=0.9,
            model=RAG_TEST_MODEL,
        )
        services.rag_service.ask_question.return_value = qr

        args = make_args(
            action="ask", company_id="US_AAPL", question="What was revenue?",
            json=True, filing_type="annual_report",
        )
        await handle(args, services)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["answer"] == "Revenue was $100B"
        assert "Filing content not present" not in captured.out
        assert "Querying" not in captured.out


class TestRagStatus:
    async def test_status_shows_indices(self, services, capsys):
        services.rag_service.get_index_status.return_value = [
            {"filing_id": 1, "model_name": "m", "page_count": 50,
             "node_count": 12, "created_at": "2026-03-22"},
        ]

        args = make_args(action="status", company_id="US_AAPL")
        await handle(args, services)

        captured = capsys.readouterr()
        assert "50" in captured.out


class TestRagShow:
    async def test_show_analyses(self, services, capsys):
        services.rag_service.get_analyses.return_value = [
            {"analysis_type": "business_summary",
             "result_json": {"summary": "Apple makes iPhones"},
             "model_name": "m", "created_at": "2026-03-22"},
        ]

        args = make_args(
            action="show", company_id="US_AAPL", filing_id=1, json=True,
        )
        await handle(args, services)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["analysis_type"] == "business_summary"


class TestRagNotConfigured:
    async def test_handle_rag_not_configured(self, services, capsys):
        services.rag_service = None
        args = make_args(action="health")

        assert await handle(args, services) == 1
        captured = capsys.readouterr()
        assert "not configured" in captured.err


class TestRagHealthExtra:
    async def test_health_json_output(self, services, capsys):
        health_data = {
            "status": "ok", "model": "qwen3.5:27b", "backend": "ollama",
            "base_url": "http://localhost:11434",
        }
        services.rag_service.health_check.return_value = health_data
        args = make_args(action="health", json=True)
        await handle(args, services)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["status"] == "ok"
        assert parsed["model"] == "qwen3.5:27b"

    async def test_health_error_exits(self, services, capsys):
        services.rag_service.health_check.return_value = {
            "status": "error", "model": "m", "backend": "ollama",
            "base_url": "http://localhost:11434", "error": "connection refused",
        }
        args = make_args(action="health")

        assert await handle(args, services) == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err


class TestRagIndexExtra:
    async def test_index_all_companies(self, services, capsys):
        target1 = MagicMock()
        target1.company_id = "US_AAPL"
        target2 = MagicMock()
        target2.company_id = "US_MSFT"
        services.target_service = AsyncMock()
        services.target_service.list_targets.return_value = [target1, target2]

        filing1 = MagicMock()
        filing1.id = 1
        filing2 = MagicMock()
        filing2.id = 2
        services.filing_service.get_latest_filing.side_effect = [filing1, filing2]

        tree = {"title": "Doc", "nodes": [], "node_count": 10}
        services.rag_service.build_index.return_value = tree

        args = make_args(action="index", company_id=None, all_companies=True, filing_type="annual_report")
        await handle(args, services)

        assert services.rag_service.build_index.call_count == 2
        captured = capsys.readouterr()
        assert "US_AAPL" in captured.out
        assert "US_MSFT" in captured.out

    async def test_index_no_company_no_all_exits(self, services, capsys):
        args = make_args(action="index", company_id=None, all_companies=False, filing_type="annual_report")

        assert await handle(args, services) == 1
        captured = capsys.readouterr()
        assert "--all" in captured.err


class TestRagAnalyzeExtra:
    async def test_analyze_single_type(self, services, capsys):
        qr = QueryResult(
            answer="test", source_pages=[1], source_sections=["S1"],
            confidence=0.9, model="m",
        )
        result = AnalysisResult("business_summary", {"summary": "Apple sells phones"}, qr)
        services.rag_service.run_analysis.return_value = result

        args = make_args(action="analyze", company_id="US_AAPL", type="business_summary", filing_type="annual_report")
        await handle(args, services)

        services.rag_service.run_analysis.assert_called_once()
        captured = capsys.readouterr()
        assert "business_summary" in captured.out

    async def test_analyze_json_output(self, services, capsys):
        qr = QueryResult(
            answer="test", source_pages=[1], source_sections=["S1"],
            confidence=0.9, model="m",
        )
        results = [AnalysisResult("business_summary", {"summary": "test"}, qr)]
        services.rag_service.run_full_analysis.return_value = results

        args = make_args(action="analyze", company_id="US_AAPL", type=None, json=True, filing_type="annual_report")
        await handle(args, services)

        captured = capsys.readouterr()
        # Output starts with a progress line; find the JSON portion
        json_part = captured.out[captured.out.index("["):]
        parsed = json.loads(json_part)
        assert parsed[0]["analysis_type"] == "business_summary"


class TestRagStatusExtra:
    async def test_status_empty(self, services, capsys):
        services.rag_service.get_index_status.return_value = []
        args = make_args(action="status", company_id="US_AAPL")
        await handle(args, services)

        captured = capsys.readouterr()
        assert "No indices found" in captured.out


async def test_rag_ask_exits_when_pageindex_disabled(monkeypatch, capsys):
    """ADR-004 amendment §B: pageindex.enabled=false で `rag ask` を実行すると
    明示エラー + exit 1 (Web 側の 503 と等価)."""
    from stock_analyze_system.services.rag_service import PageIndexDisabledError

    svc = MagicMock()
    svc.rag_service = MagicMock()
    svc.rag_service.ask_question = AsyncMock(
        side_effect=PageIndexDisabledError(
            "pageindex.enabled=false; ask_question は無効化されています"
        ),
    )
    company_mock = MagicMock()
    company_mock.id = "US_AAPL"
    filing_mock = MagicMock()
    filing_mock.storage_path = "/data/auto/fetched"
    from stock_analyze_system.cli import helpers as cli_helpers
    monkeypatch.setattr(
        cli_helpers, "require_company_and_filing",
        AsyncMock(return_value=(company_mock, filing_mock)),
    )

    args = argparse.Namespace(
        action="ask",
        company_id="US_AAPL",
        filing_type="10-K",
        question="What is the revenue?",
        json=False,
    )

    assert await handle(args, svc) == 1
    assert "PageIndex is disabled" in capsys.readouterr().err


async def test_rag_index_exits_when_pageindex_disabled(monkeypatch, capsys):
    """`rag index` も同じ exit 経路."""
    from stock_analyze_system.services.rag_service import PageIndexDisabledError

    svc = MagicMock()
    svc.rag_service = MagicMock()
    svc.rag_service.build_index = AsyncMock(
        side_effect=PageIndexDisabledError(
            "pageindex.enabled=false; build_index は無効化されています"
        ),
    )
    company_mock = MagicMock()
    company_mock.id = "US_AAPL"
    filing_mock = MagicMock()
    filing_mock.storage_path = "/data/auto/fetched"
    from stock_analyze_system.cli import helpers as cli_helpers
    monkeypatch.setattr(
        cli_helpers, "require_company",
        AsyncMock(return_value=company_mock),
    )
    monkeypatch.setattr(
        cli_helpers, "require_latest_filing",
        AsyncMock(return_value=filing_mock),
    )

    args = argparse.Namespace(
        action="index",
        company_id="US_AAPL",
        filing_type="10-K",
        all_companies=False,
        json=False,
    )

    assert await handle(args, svc) == 1
    assert "PageIndex is disabled" in capsys.readouterr().err


async def test_rag_status_exits_when_pageindex_disabled(capsys):
    """`rag status` も同じ exit 経路."""
    from stock_analyze_system.services.rag_service import PageIndexDisabledError

    svc = MagicMock()
    svc.rag_service = MagicMock()
    svc.rag_service.get_index_status = AsyncMock(
        side_effect=PageIndexDisabledError(
            "pageindex.enabled=false; get_index_status は無効化されています"
        ),
    )

    args = argparse.Namespace(
        action="status",
        company_id="US_AAPL",
        json=False,
    )

    assert await handle(args, svc) == 1
    assert "PageIndex is disabled" in capsys.readouterr().err


async def test_rag_analyze_returns_code_when_filing_unsupported(monkeypatch, capsys):
    from stock_analyze_system.cli import helpers as cli_helpers
    from stock_analyze_system.services.rag_service import (
        UnsupportedFilingForExtractorError,
    )

    svc = MagicMock()
    svc.rag_service = MagicMock()
    svc.rag_service.run_full_analysis = AsyncMock(
        side_effect=UnsupportedFilingForExtractorError("unsupported filing"),
    )
    company_mock = MagicMock()
    company_mock.id = "JP_7203"
    filing_mock = MagicMock()
    filing_mock.storage_path = "/data/edinet"
    monkeypatch.setattr(
        cli_helpers, "require_company_and_filing",
        AsyncMock(return_value=(company_mock, filing_mock)),
    )

    args = argparse.Namespace(
        action="analyze",
        company_id="JP_7203",
        filing_type="annual_report",
        type=None,
        json=False,
    )

    assert await handle(args, svc) == 2
    assert "unsupported filing" in capsys.readouterr().err


async def test_rag_analyze_exits_cleanly_when_raw_html_missing(monkeypatch, capsys):
    from stock_analyze_system.cli import helpers as cli_helpers
    from stock_analyze_system.services.filing_section_extractor import (
        ExtractionInputMissingError,
    )

    svc = MagicMock()
    svc.rag_service = MagicMock()
    svc.rag_service.run_full_analysis = AsyncMock(
        side_effect=ExtractionInputMissingError(
            "raw HTML not found for filing_id=1"
        ),
    )

    company_mock = MagicMock()
    company_mock.id = "US_AAPL"
    filing_mock = MagicMock()
    filing_mock.id = 1
    filing_mock.source = "SEC"
    filing_mock.storage_path = "/data/converted-only"
    monkeypatch.setattr(
        cli_helpers, "require_company_and_filing",
        AsyncMock(return_value=(company_mock, filing_mock)),
    )

    args = argparse.Namespace(
        action="analyze",
        company_id="US_AAPL",
        filing_type="10-K",
        type=None,
        json=False,
    )

    exit_code = await handle(args, svc)

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "raw HTML not found" in captured.err
    assert "Traceback" not in captured.err


async def test_rag_analyze_commits_structural_placeholders_before_missing_raw_html_exit(
    async_engine, tmp_path,
):
    from sqlalchemy import select

    from stock_analyze_system.models.base import get_session
    from stock_analyze_system.models.company import Company
    from stock_analyze_system.models.company_analysis import (
        CompanyAnalysis,
        PIPELINE_EXTRACTOR,
    )
    from stock_analyze_system.models.filing import Filing
    from stock_analyze_system.repositories.analysis import AnalysisRepository
    from stock_analyze_system.services.filing_section_extractor import (
        FilingSectionExtractor,
    )
    from stock_analyze_system.services.rag_service import RagService

    storage_path = tmp_path / "converted-only"
    storage_path.mkdir()
    (storage_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")

    async with get_session(async_engine) as session:
        company = Company(
            id="US_AAPL_RAGCLI",
            ticker="AAPL",
            name="Apple Inc.",
            market="NASDAQ",
            accounting_standard="US-GAAP",
        )
        session.add(company)
        await session.flush()
        filing = Filing(
            company_id=company.id,
            source="SEC",
            filing_type="10-Q",
            period_type="quarterly",
            fiscal_year=2025,
            accession_no="0000320193-25-000001",
            storage_path=str(storage_path),
        )
        session.add(filing)
        await session.flush()
        filing_id = filing.id

    async with get_session(async_engine) as session:
        company = await session.get(Company, "US_AAPL_RAGCLI")
        filing = await session.get(Filing, filing_id)
        svc = MagicMock()
        svc.company_service.get_company = AsyncMock(return_value=company)
        svc.filing_service.get_latest_filing = AsyncMock(return_value=filing)
        svc.rag_service = RagService(
            pageindex_service=AsyncMock(),
            analysis_repo=AnalysisRepository(session),
            llm_client=AsyncMock(),
            filing_content_service=None,
            section_extractor=FilingSectionExtractor(),
        )

        args = argparse.Namespace(
            action="analyze",
            company_id="US_AAPL_RAGCLI",
            filing_type="10-Q",
            type=None,
            json=False,
        )

        assert await handle(args, svc) == 2

    async with get_session(async_engine) as session:
        rows = (
            await session.scalars(
                select(CompanyAnalysis).where(
                    CompanyAnalysis.company_id == "US_AAPL_RAGCLI",
                    CompanyAnalysis.filing_id == filing_id,
                    CompanyAnalysis.pipeline == PIPELINE_EXTRACTOR,
                )
            )
        ).all()

    assert [row.analysis_type for row in rows] == [
        "business_summary",
        "competitors",
    ]


async def test_rag_analyze_works_when_pageindex_disabled(monkeypatch):
    """ADR-004 amendment §B: 定型分析 (analyze) は PageIndex 非依存のため、
    pageindex.enabled=false でも動く."""
    from stock_analyze_system.services.rag_service import AnalysisResult
    from stock_analyze_system.services.pageindex import QueryResult

    svc = MagicMock()
    svc.rag_service = MagicMock()
    svc.rag_service.pageindex_available = False
    fake_result = AnalysisResult(
        analysis_type="business_summary",
        result_json={"summary": "ok"},
        query_result=QueryResult(
            answer='{"summary": "ok"}', source_pages=[],
            source_sections=["business_summary"], confidence=1.0,
            model="test-model",
        ),
    )
    svc.rag_service.run_full_analysis = AsyncMock(return_value=[fake_result])

    company_mock = MagicMock()
    company_mock.id = "US_AAPL"
    filing_mock = MagicMock()
    filing_mock.storage_path = "/data/auto/fetched"
    from stock_analyze_system.cli import helpers as cli_helpers
    monkeypatch.setattr(
        cli_helpers, "require_company_and_filing",
        AsyncMock(return_value=(company_mock, filing_mock)),
    )

    args = argparse.Namespace(
        action="analyze",
        company_id="US_AAPL",
        filing_type="10-K",
        type=None,
        json=True,
    )

    # SystemExit が出ない = pass.
    await handle(args, svc)
    svc.rag_service.run_full_analysis.assert_awaited_once()
