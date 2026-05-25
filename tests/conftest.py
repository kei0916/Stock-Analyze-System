"""テスト共通フィクスチャ"""
import json
from collections import defaultdict
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.base import Base, create_db_engine, get_session
from stock_analyze_system.models.company import Company  # noqa: F401
from stock_analyze_system.models.financial_data import FinancialData  # noqa: F401
from stock_analyze_system.models.valuation import Valuation  # noqa: F401
from stock_analyze_system.models.filing import Filing  # noqa: F401
from stock_analyze_system.models.company_analysis import CompanyAnalysis  # noqa: F401
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem  # noqa: F401
from stock_analyze_system.models.analysis_target import AnalysisTarget  # noqa: F401
from stock_analyze_system.models.screening import ScreeningCache  # noqa: F401
from stock_analyze_system.models.competitor_group import CompetitorGroup, CompetitorGroupMember  # noqa: F401
from stock_analyze_system.models.document_index import DocumentIndex  # noqa: F401
from stock_analyze_system.models.quote_price import QuotePrice  # noqa: F401
from stock_analyze_system.models.analysis_job import AnalysisJob  # noqa: F401


@pytest.fixture
async def async_engine():
    """インメモリ AsyncSQLite エンジン (高速、PRAGMA リスナー無し)"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def pragma_async_engine(tmp_path):
    """ファイルベース AsyncSQLite (PRAGMA リスナー適用済み、PRAGMA テスト用)"""
    db_path = str(tmp_path / "pragma_test.db")
    engine = await create_db_engine(db_path)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(async_engine):
    """テスト用 AsyncSession（インメモリ DB、テストごとに再作成）"""
    async with get_session(async_engine) as sess:
        yield sess


@pytest.fixture
def config() -> AppConfig:
    """テスト用設定"""
    return AppConfig()


@pytest.fixture
async def sample_company(session):
    """テスト用米国企業"""
    company = Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP", cik="0000320193",
    )
    session.add(company)
    await session.flush()
    return company


@pytest.fixture
async def sample_jp_company(session):
    """テスト用日本企業"""
    company = Company(
        id="JP_7203", security_code="7203", name="Toyota Motor Corporation",
        name_ja="トヨタ自動車株式会社", market="TSE_PRIME",
        accounting_standard="IFRS", edinet_code="E02144",
    )
    session.add(company)
    await session.flush()
    return company


RAG_TEST_MODEL = "openai/Qwen3.6-27B-Q4_K_M.gguf"


# ── RAG Timing Plugin ─────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--rag-timing", action="store_true", default=False, help="RAGテスト実行時間を記録・出力")
    parser.addoption("--rag-timing-file", default=None, help="タイミング結果のJSON出力先")


class RagTimingReport:
    """テスト実行時間を収集しサマリを出力する"""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def add(self, nodeid: str, model: str, duration: float) -> None:
        self.records.append({"test": nodeid, "model": model, "duration_s": round(duration, 4)})

    def summary(self) -> str:
        if not self.records:
            return "No RAG timing records."
        by_model: dict[str, list[float]] = defaultdict(list)
        for r in self.records:
            by_model[r["model"]].append(r["duration_s"])
        lines = ["\n===== RAG Test Timing Summary ====="]
        for model, durations in sorted(by_model.items()):
            total = sum(durations)
            avg = total / len(durations)
            lines.append(f"  {model}: {len(durations)} tests, total={total:.2f}s, avg={avg:.4f}s")
        lines.append(f"  ALL: {len(self.records)} tests, total={sum(r['duration_s'] for r in self.records):.2f}s")
        lines.append("=" * 37)
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.records, indent=2, ensure_ascii=False)


_rag_report_key = pytest.StashKey[RagTimingReport]()


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--rag-timing", default=False):
        config.stash[_rag_report_key] = RagTimingReport()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):  # noqa: ANN001
    outcome = yield
    report = outcome.get_result()
    rag_report = item.config.stash.get(_rag_report_key, None)
    if report.when == "call" and rag_report is not None:
        marker = item.get_closest_marker("rag_model")
        if marker is None:
            return
        rag_report.add(item.nodeid, marker.args[0], report.duration)


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    rag_report = config.stash.get(_rag_report_key, None)
    if rag_report is None or not rag_report.records:
        return
    terminalreporter.write_line(rag_report.summary())
    output_file = config.getoption("--rag-timing-file", default=None)
    if output_file:
        Path(output_file).write_text(rag_report.to_json())
        terminalreporter.write_line(f"Timing data saved to {output_file}")
