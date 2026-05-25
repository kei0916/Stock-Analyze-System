"""AnalysisWorker scaffold tests."""
from __future__ import annotations

import signal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository
from stock_analyze_system.services.analysis_worker import AnalysisWorker


@pytest.fixture
async def session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
def fake_clients():
    return MagicMock()


@pytest.fixture
def worker(session_factory, fake_clients):
    return AnalysisWorker(session_factory, AppConfig(), fake_clients, poll_interval=0.05)


def test_init_stores_poll_interval(worker):
    assert worker._poll_interval == 0.05


def test_init_shutdown_flag_starts_false(worker):
    assert worker._shutdown.is_set() is False


def test_request_shutdown_sets_flag(worker):
    worker.request_shutdown()
    assert worker._shutdown.is_set()


def test_install_signal_handlers_registers_sigterm_sigint(monkeypatch, worker):
    registered = {}

    def fake_signal(signum, handler):
        registered[signum] = handler

    monkeypatch.setattr(signal, "signal", fake_signal)

    worker.install_signal_handlers()

    assert signal.SIGTERM in registered
    assert signal.SIGINT in registered

    registered[signal.SIGTERM](signal.SIGTERM, None)
    assert worker._shutdown.is_set()


async def seed_filing(session_factory) -> int:
    async with session_factory() as session:
        company = Company(
            id="US_AAPL",
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
            filing_type="10-K",
            period_type="annual",
            fiscal_year=2024,
            accession_no="0000320193-24-000123",
        )
        session.add(filing)
        await session.commit()
        return filing.id


async def _fetch_filing(session_factory, filing_id: int) -> Filing:
    async with session_factory() as session:
        filing = await session.get(Filing, filing_id)
        assert filing is not None
        return filing


async def _enqueue_pending(session_factory, filing_id: int) -> int:
    filing = await _fetch_filing(session_factory, filing_id)
    async with session_factory() as session:
        job = AnalysisJob(
            company_id=filing.company_id,
            filing_id=filing_id,
            status=JobStatus.PENDING.value,
        )
        session.add(job)
        await session.commit()
        return job.id


async def _get_job(session_factory, job_id: int) -> AnalysisJob:
    async with session_factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None
        return job


class _FakeRagService:
    def __init__(self, events, preflight_result=None):
        self.events = events
        self.seen_filings = []
        self._preflight_result = preflight_result or {
            "status": "ok",
            "model": "test-model",
            "response_head": '{"ok": 1}',
            "diagnostic": {},
        }

    async def preflight(self):
        return self._preflight_result

    async def run_full_analysis_stream(self, filing):
        self.seen_filings.append(filing)
        for event in self.events:
            if isinstance(event, BaseException):
                raise event
            yield event


def _install_fake_setup(monkeypatch, rag_service, filing):
    container = MagicMock()
    container.rag_service = rag_service
    container.filing_service = MagicMock(
        get_filing_by_id=AsyncMock(return_value=filing),
    )

    async def fake_setup_services(session, config, *, clients=None):
        return container

    monkeypatch.setattr(
        "stock_analyze_system.services.analysis_worker.setup_services",
        fake_setup_services,
    )
    return container


async def test_run_one_job_returns_false_when_no_pending(worker):
    assert await worker.run_one_job() is False


async def test_run_one_job_consumes_exactly_one(worker, session_factory, monkeypatch):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 1},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {"event": "done", "index": 0, "analysis_type": "business"},
            {"event": "complete"},
        ]),
        filing,
    )

    assert await worker.run_one_job() is True
    assert (await _get_job(session_factory, job_id)).status == JobStatus.COMPLETED.value
    assert await worker.run_one_job() is False


async def test_run_one_job_completes_successfully(
    worker,
    session_factory,
    monkeypatch,
):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    rag_service = _FakeRagService([
        {"event": "started", "total": 4},
        {"event": "phase", "index": 0, "analysis_type": "business"},
        {"event": "done", "index": 0, "analysis_type": "business"},
        {"event": "phase", "index": 1, "analysis_type": "mda"},
        {"event": "done", "index": 1, "analysis_type": "mda"},
        {"event": "phase", "index": 2, "analysis_type": "risk"},
        {"event": "done", "index": 2, "analysis_type": "risk"},
        {"event": "phase", "index": 3, "analysis_type": "outlook"},
        {"event": "done", "index": 3, "analysis_type": "outlook"},
        {"event": "complete"},
    ])
    _install_fake_setup(monkeypatch, rag_service, filing)

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert rag_service.seen_filings == [filing]
    assert job.status == JobStatus.COMPLETED.value
    assert job.completed_at is not None
    assert job.progress_current == 4
    assert job.current_analysis_type is None


async def test_run_one_job_relies_on_terminal_status_to_clear_current_type(
    worker, session_factory, monkeypatch,
):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 1},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {"event": "done", "index": 0, "analysis_type": "business"},
            {"event": "complete"},
        ]),
        filing,
    )

    async def fail_clear(self, job_id):  # noqa: ARG001
        raise AssertionError("clear_current_type should not be called separately")

    monkeypatch.setattr(AnalysisJobRepository, "clear_current_type", fail_clear)

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.COMPLETED.value
    assert job.current_analysis_type is None


async def test_run_one_job_partial_failure(worker, session_factory, monkeypatch):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 4},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {
                "event": "error",
                "index": 0,
                "analysis_type": "business",
                "message": "request timeout",
            },
            {"event": "phase", "index": 1, "analysis_type": "mda"},
            {"event": "done", "index": 1, "analysis_type": "mda"},
            {"event": "phase", "index": 2, "analysis_type": "risk"},
            {"event": "done", "index": 2, "analysis_type": "risk"},
            {"event": "phase", "index": 3, "analysis_type": "outlook"},
            {"event": "done", "index": 3, "analysis_type": "outlook"},
            {"event": "complete"},
        ]),
        filing,
    )

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert job.completed_at is not None
    assert job.progress_current == 4
    assert job.error_details["failed_types"][0]["type"] == "business"


async def test_run_one_job_skipped_event_does_not_fail_job(
    worker,
    session_factory,
    monkeypatch,
):
    """ADR-004 review: `skipped` event (e.g., 10-Q business_summary structural
    absence) must advance progress without populating failed_types or marking
    the job FAILED."""
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 4},
            {"event": "phase", "index": 0, "analysis_type": "business_summary"},
            {"event": "skipped", "index": 0, "analysis_type": "business_summary",
             "reason": "structurally_absent"},
            {"event": "phase", "index": 1, "analysis_type": "risk_factors"},
            {"event": "done", "index": 1, "analysis_type": "risk_factors"},
            {"event": "phase", "index": 2, "analysis_type": "mda"},
            {"event": "done", "index": 2, "analysis_type": "mda"},
            {"event": "phase", "index": 3, "analysis_type": "competitors"},
            {"event": "skipped", "index": 3, "analysis_type": "competitors",
             "reason": "structurally_absent"},
            {"event": "complete"},
        ]),
        filing,
    )

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.COMPLETED.value
    assert job.progress_current == 4
    # No failed_types should be set when only skipped + done events occurred.
    assert job.error_details is None or not job.error_details.get("failed_types")


async def test_run_one_job_error_event_advances_progress(
    worker,
    session_factory,
    monkeypatch,
):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 1},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {
                "event": "error",
                "index": 0,
                "analysis_type": "business",
                "message": "timeout",
            },
            {"event": "complete"},
        ]),
        filing,
    )

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert job.progress_current == 1
    assert job.current_analysis_type is None
    assert job.error_details["failed_types"][0]["type"] == "business"


async def test_run_one_job_separates_extraction_error_from_failed_types(
    worker,
    session_factory,
    monkeypatch,
):
    """ADR-004: section extraction 失敗 (event.analysis_type is None) は
    failed_types ではなく error_details["extraction_error"] に分離。
    PageIndex の index_build_error とは別系統で UI が区別する前提を満たす。"""
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    diagnostic = {"phase": "section_extraction", "filing_type": "10-K"}
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "extracting"},
            {
                "event": "error",
                "analysis_type": None,
                "message": "Unable to parse filing HTML",
                "diagnostic": diagnostic,
            },
            {"event": "complete"},
        ]),
        filing,
    )

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert "extraction_error" in job.error_details
    assert job.error_details["extraction_error"]["diagnostic"] == diagnostic
    assert "parse filing" in job.error_details["extraction_error"]["message"].lower()
    # legacy index_build_error キーは ADR-004 後の定型分析では使われない
    assert "index_build_error" not in job.error_details
    assert not job.error_details.get("failed_types")


async def test_run_one_job_fails_fast_when_preflight_returns_error(
    worker,
    session_factory,
    monkeypatch,
):
    """ADR-004: preflight (step-3 用 LLM probe) 失敗は extraction_error 配下に格納し、
    PageIndex の index_build_error と区別する."""
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    preflight_diag = {
        "kind": "llm_probe",
        "model": "test-model",
        "content_len": 0,
    }
    stream_started = {"called": False}

    class _Rag:
        async def preflight(self):
            return {
                "status": "error",
                "model": "test-model",
                "reason": "Connection refused",
                "diagnostic": preflight_diag,
            }

        async def run_full_analysis_stream(self, filing):
            stream_started["called"] = True
            if False:
                yield  # pragma: no cover (generator hint)

    _install_fake_setup(monkeypatch, _Rag(), filing)

    assert await worker.run_one_job() is True

    assert stream_started["called"] is False
    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    ee = job.error_details.get("extraction_error")
    assert ee is not None
    assert "preflight" in ee["message"].lower()
    assert ee["diagnostic"] == preflight_diag
    assert "index_build_error" not in job.error_details
    assert not job.error_details.get("failed_types")


async def test_run_one_job_proceeds_when_preflight_ok(
    worker,
    session_factory,
    monkeypatch,
):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)

    class _Rag:
        async def preflight(self):
            return {
                "status": "ok", "model": "m", "response_head": '{"ok":1}', "diagnostic": {},
            }

        async def run_full_analysis_stream(self, filing):
            yield {"event": "started", "total": 1}
            yield {"event": "phase", "index": 0, "analysis_type": "business"}
            yield {"event": "done", "index": 0, "analysis_type": "business"}
            yield {"event": "complete"}

    _install_fake_setup(monkeypatch, _Rag(), filing)

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.COMPLETED.value


async def test_run_one_job_keeps_per_type_failures_in_failed_types(
    worker,
    session_factory,
    monkeypatch,
):
    """analysis-stage 失敗 (event.analysis_type が具体的なタイプ) は
    引き続き failed_types に積み、index_build_error は付かない."""
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 2},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            {
                "event": "error",
                "index": 0,
                "analysis_type": "business",
                "message": "timeout",
            },
            {"event": "phase", "index": 1, "analysis_type": "mda"},
            {"event": "done", "index": 1, "analysis_type": "mda"},
            {"event": "complete"},
        ]),
        filing,
    )

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert job.error_details.get("failed_types") == [
        {"type": "business", "message": "timeout"},
    ]
    assert "index_build_error" not in job.error_details


async def test_run_one_job_unexpected_exception(
    worker,
    session_factory,
    monkeypatch,
):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 4},
            RuntimeError("stream exploded"),
        ]),
        filing,
    )

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert job.completed_at is not None
    assert "stream exploded" in job.error_details["reason"]


async def test_run_one_job_clears_current_type_when_stream_raises_after_phase(
    worker, session_factory, monkeypatch,
):
    filing_id = await seed_filing(session_factory)
    filing = await _fetch_filing(session_factory, filing_id)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(
        monkeypatch,
        _FakeRagService([
            {"event": "started", "total": 1},
            {"event": "phase", "index": 0, "analysis_type": "business"},
            RuntimeError("stream exploded after phase"),
        ]),
        filing,
    )

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert job.current_analysis_type is None
    assert "stream exploded after phase" in job.error_details["reason"]


async def test_run_one_job_filing_missing(worker, session_factory, monkeypatch):
    filing_id = await seed_filing(session_factory)
    job_id = await _enqueue_pending(session_factory, filing_id)
    _install_fake_setup(monkeypatch, _FakeRagService([]), None)

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert job.completed_at is not None
    assert f"filing_id={filing_id} not found" in job.error_details["reason"]


async def test_run_one_job_fails_on_company_mismatch(
    worker, session_factory, monkeypatch,
):
    """job.company_id と filing.company_id がズレた内部 job は実行しない."""
    filing_id = await seed_filing(session_factory)
    job_id = await _enqueue_pending(session_factory, filing_id)
    filing = await _fetch_filing(session_factory, filing_id)
    filing.company_id = "US_MSFT"

    rag_service = _FakeRagService([
        {"event": "started", "total": 1},
        {"event": "phase", "index": 0, "analysis_type": "business"},
        {"event": "done", "index": 0, "analysis_type": "business"},
        {"event": "complete"},
    ])
    _install_fake_setup(monkeypatch, rag_service, filing)

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    assert "belongs to US_MSFT" in job.error_details["reason"]
    assert "job.company_id=US_AAPL" in job.error_details["reason"]
    assert rag_service.seen_filings == []


async def test_run_one_job_rejects_non_sec_filing(
    worker, session_factory, monkeypatch,
):
    """ADR-004 amendment §A defense-in-depth: API 境界 (analysis_jobs.py:73)
    を bypass した EDINET / 非対応 filing_type が worker に流れても、
    extractor / LLM 呼び出しの前に extraction_error で明示失敗する.

    旧実装は SEC-only 検査が API のみで、DB 直書き / 旧 pending job が
    EDINET でも worker で実行され、extractor の `failed_types` に紛れて
    「取りこぼし」と誤認される運用切り分け事故があった."""
    filing_id = await seed_filing(session_factory)
    job_id = await _enqueue_pending(session_factory, filing_id)

    # API 境界 bypass を simulate: filing を seed 後に mutate.
    # worker は filing_service mock 経由でこの instance を受け取る.
    filing = await _fetch_filing(session_factory, filing_id)
    filing.source = "EDINET"
    filing.filing_type = "annual_report"

    rag_service = _FakeRagService([])
    _install_fake_setup(monkeypatch, rag_service, filing)

    assert await worker.run_one_job() is True

    job = await _get_job(session_factory, job_id)
    assert job.status == JobStatus.FAILED.value
    err = job.error_details
    assert "extraction_error" in err, (
        "non-SEC filing must surface as extraction_error, not failed_types"
    )
    msg = err["extraction_error"]["message"]
    assert "unsupported filing" in msg
    assert "source=EDINET" in msg
    assert "filing_type=annual_report" in msg
    # extractor / LLM 呼び出しに到達しないこと (validation は preflight より前)
    assert rag_service.seen_filings == []


def _extract_section_21_table(runbook: str) -> str:
    """runbook §2.1 の error_details table 範囲だけを抜き出す.

    全文検索だとコメント・補注・別セクションの偶発的ヒットでも assertion が
    通ってしまうため、key 同期検査は §2.1 (表開始) ~ §2.2 (次の見出し) の
    範囲に限定する."""
    start = runbook.find("### 2.1 ")
    assert start >= 0, "runbook §2.1 header missing"
    end = runbook.find("### 2.2 ", start)
    assert end > start, "runbook §2.2 header missing or before §2.1"
    return runbook[start:end]


def test_runbook_error_details_keys_match_worker_constants():
    """ADR-004 §A15: runbook §2.1 の error_details 表が worker の実装定数と
    同期していることを検査. ERROR_DETAILS_KEYS を変更したら runbook も更新する.

    検査範囲は §2.1 section だけ (全文検索だと別セクション/コメントの偶発
    ヒットですり抜ける)."""
    from pathlib import Path
    from stock_analyze_system.services.analysis_worker import (
        ERROR_DETAILS_KEYS,
    )

    # tests/unit/services/test_analysis_worker.py から repo root へ 3 つ上る
    # (相対 cwd に依存しないよう __file__ で anchor する).
    repo_root = Path(__file__).resolve().parents[3]
    runbook = (repo_root / "docs/analysis-jobs-runbook.md").read_text(encoding="utf-8")
    table = _extract_section_21_table(runbook)

    for key in ERROR_DETAILS_KEYS:
        assert f'"{key}"' in table, (
            f"runbook §2.1 table missing error_details key: {key}; "
            "update docs/analysis-jobs-runbook.md §2.1 table"
        )
    # legacy 行も §2.1 内に明示的に残す (ADR-004 前のジョブ識別のため)
    assert '"index_build_error"' in table, (
        "runbook §2.1 must document legacy index_build_error key for older jobs"
    )

    # 構造上空の章 (10-Q business_summary 等) は failed_types ではなく
    # skipped + _status="not_applicable" で扱われる (rag_service._process_one).
    # 旧版 runbook は "ファイリングに該当章がありません" を failed_types の
    # message として例示していたため、運用切り分けが逆になる drift を
    # 防ぐためここで検査する.
    assert "ファイリングに該当章がありません" not in runbook, (
        "runbook must not describe structurally-absent chapters as failed_types; "
        "they are stored as placeholder with _status=\"not_applicable\" and the "
        "job completes successfully (see rag_service._process_one + "
        "_save_placeholder)"
    )
    # 正常仕様の説明側 (構造上空は error_details に出ない) は残っているか.
    assert "is_structurally_empty" in runbook, (
        "runbook must explain that is_structurally_empty paths skip the failure "
        "channel (otherwise operators look for non-existent failed_types entries)"
    )
    assert '_status="not_applicable"' in runbook, (
        "runbook must reference the not_applicable placeholder sentinel so "
        "operators can map UI '適用外' display to the underlying DB state"
    )
