"""Analysis, Watchlist, Screening, Target, DocumentIndex リポジトリのテスト"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.company_analysis import (
    PIPELINE_EXTRACTOR,
    CompanyAnalysis,
)
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.models.analysis_target import AnalysisTarget
from stock_analyze_system.repositories.analysis import AnalysisRepository
from stock_analyze_system.repositories.watchlist import WatchlistRepository
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.repositories.target import TargetRepository
from stock_analyze_system.repositories.document_index import DocumentIndexRepository


async def _setup_company_and_filing(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    )
    session.add(f)
    await session.flush()
    return f


# --- AnalysisRepository ---

async def test_analysis_get_by_type(session):
    """分析タイプ別取得ができること (現行 extractor パイプライン行)."""
    f = await _setup_company_and_filing(session)
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="financial_summary",
        result_json='{"summary": "test"}', model_name="test-model",
        pipeline="extractor",
    ))
    await session.flush()
    repo = AnalysisRepository(session)
    result = await repo.get_by_type("US_AAPL", f.id, "financial_summary")
    assert result is not None
    assert result.analysis_type == "financial_summary"


async def test_analysis_get_analyses(session):
    """企業+ファイリングの分析結果一覧を取得できること (extractor 行)."""
    f = await _setup_company_and_filing(session)
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="type_a",
        result_json='{}', model_name="test-model",
        pipeline="extractor",
    ))
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="type_b",
        result_json='{}', model_name="test-model",
        pipeline="extractor",
    ))
    await session.flush()
    repo = AnalysisRepository(session)
    results = await repo.get_analyses("US_AAPL", f.id)
    assert len(results) == 2


async def test_analysis_get_by_type_excludes_legacy_pipeline_rows(session):
    """ADR-004: pipeline IS NULL の PageIndex 時代の行は cache 対象から除外される."""
    f = await _setup_company_and_filing(session)
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="business_summary",
        result_json='{"summary": "legacy"}', model_name="qwen-legacy",
        pipeline=None,  # PageIndex 時代の行
    ))
    await session.flush()
    repo = AnalysisRepository(session)

    assert await repo.get_by_type("US_AAPL", f.id, "business_summary") is None
    assert await repo.get_analyses("US_AAPL", f.id) == []


async def test_analysis_upsert_preserves_legacy_row_when_writing_extractor(session):
    """ADR-004: legacy NULL 行と extractor 行は同じ filing/type で共存する."""
    f = await _setup_company_and_filing(session)
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="business_summary",
        result_json='{"summary": "legacy"}', model_name="qwen-legacy",
        pipeline=None,
    ))
    await session.flush()

    repo = AnalysisRepository(session)
    await repo.upsert(
        {
            "company_id": "US_AAPL",
            "filing_id": f.id,
            "analysis_type": "business_summary",
            "pipeline": PIPELINE_EXTRACTOR,
        },
        {"result_json": '{"summary": "extractor"}', "model_name": "qwen-new"},
    )

    rows = (await session.execute(
        select(CompanyAnalysis).where(
            CompanyAnalysis.company_id == "US_AAPL",
            CompanyAnalysis.filing_id == f.id,
            CompanyAnalysis.analysis_type == "business_summary",
        ).order_by(CompanyAnalysis.pipeline.asc().nulls_first())
    )).scalars().all()

    assert len(rows) == 2
    assert rows[0].pipeline is None
    assert rows[0].result_json == '{"summary": "legacy"}'
    assert rows[1].pipeline == PIPELINE_EXTRACTOR
    assert rows[1].result_json == '{"summary": "extractor"}'


async def test_analysis_list_recent_filters_pipeline_extractor(session):
    f = await _setup_company_and_filing(session)
    session.add_all([
        CompanyAnalysis(
            company_id="US_AAPL", filing_id=f.id,
            analysis_type="legacy", result_json="{}",
            model_name="legacy-model", pipeline=None,
        ),
        CompanyAnalysis(
            company_id="US_AAPL", filing_id=f.id,
            analysis_type="business_summary", result_json="{}",
            model_name="extractor-model", pipeline="extractor",
        ),
    ])
    await session.flush()
    repo = AnalysisRepository(session)

    rows = await repo.list_recent_extractor(limit=10)

    assert [r.analysis_type for r in rows] == ["business_summary"]


async def test_analysis_count_supports_pipeline_filter(session):
    """LSP: BaseRepository.count(**filters) を継承し pipeline kwarg で絞り込める."""

    f = await _setup_company_and_filing(session)
    session.add_all([
        CompanyAnalysis(
            company_id="US_AAPL", filing_id=f.id,
            analysis_type="legacy", result_json="{}",
            model_name="legacy-model", pipeline=None,
        ),
        CompanyAnalysis(
            company_id="US_AAPL", filing_id=f.id,
            analysis_type="mda", result_json="{}",
            model_name="extractor-model", pipeline="extractor",
        ),
    ])
    await session.flush()
    repo = AnalysisRepository(session)

    # unfiltered count exposes legacy rows
    assert await repo.count() == 2
    # opt-in extractor-only count
    assert await repo.count(pipeline="extractor") == 1
    # filters compose with other columns
    assert await repo.count(company_id="US_AAPL") == 2


# --- WatchlistRepository ---

async def test_watchlist_get_by_name(session):
    """名前でウォッチリストを取得できること"""
    session.add(Watchlist(name="My List"))
    await session.flush()
    repo = WatchlistRepository(session)
    result = await repo.get_by_name("My List")
    assert result is not None
    assert result.name == "My List"


async def test_watchlist_find_item(session):
    """ウォッチリストアイテムを検索できること"""
    wl = Watchlist(name="Test")
    session.add(wl)
    await session.flush()
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    item = WatchlistItem(watchlist_id=wl.id, company_id="US_AAPL")
    session.add(item)
    await session.flush()
    repo = WatchlistRepository(session)
    result = await repo.find_item(wl.id, "US_AAPL")
    assert result is not None


# --- ScreeningRepository ---

async def test_screening_upsert_and_get_cache(session):
    """スクリーニングキャッシュの upsert と取得"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ScreeningRepository(session)
    await repo.upsert_cache("US_AAPL", {"stock_price": 185.0, "per": 28.5})
    result = await repo.get_cache("US_AAPL")
    assert result is not None
    assert result.stock_price == 185.0


async def test_screening_upsert_normalizes_external_payload(session):
    """Yahoo等の外部payloadをDB型に正規化して保存する"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ScreeningRepository(session)

    await repo.upsert_cache("US_AAPL", {
        "stock_price": 185.0,
        "most_recent_quarter": "2026-03-31",
        "last_fiscal_year_end": "2025-12-31",
        "pbr": float("nan"),
        "psr": float("inf"),
        "ignored_vendor_key": "drop me",
    })

    result = await repo.get_cache("US_AAPL")
    assert result is not None
    assert result.most_recent_quarter == date(2026, 3, 31)
    assert result.last_fiscal_year_end == date(2025, 12, 31)
    assert result.pbr is None
    assert result.psr is None


async def test_screening_upsert_normalizes_realistic_date_and_value_forms(session):
    """外部payloadの現実的な日付・数値表現をDB境界で正規化する"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ScreeningRepository(session)

    await repo.upsert_cache("US_AAPL", {
        "per": 28.5,
        "stock_price": float("nan"),
        "pbr": Decimal("Infinity"),
        "psr": Decimal("-Infinity"),
        "eps": Decimal("NaN"),
        "most_recent_quarter": date(2026, 3, 31),
        "last_fiscal_year_end": datetime(2025, 12, 31, 23, 59, 59),
        "ignored_vendor_key": "drop me",
    })
    result = await repo.get_cache("US_AAPL")
    assert result is not None
    assert result.trailing_per == 28.5
    assert result.stock_price is None
    assert result.pbr is None
    assert result.psr is None
    assert result.eps is None
    assert result.most_recent_quarter == date(2026, 3, 31)
    assert result.last_fiscal_year_end == date(2025, 12, 31)
    assert not hasattr(result, "ignored_vendor_key")


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (datetime(2026, 3, 31, 4, 5, 6), date(2026, 3, 31)),
        (
            int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp()),
            date(2026, 4, 1),
        ),
        (
            datetime(2026, 4, 2, 12, 30, tzinfo=timezone.utc).timestamp(),
            date(2026, 4, 2),
        ),
        ("2026-03-31T04:05:06+00:00", date(2026, 3, 31)),
        ("not-a-date", None),
    ],
)
async def test_screening_upsert_normalizes_date_field_forms(
    session, raw_value, expected,
):
    """date列に入る外部表現をdateまたはNoneへ正規化する"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ScreeningRepository(session)

    await repo.upsert_cache("US_AAPL", {"most_recent_quarter": raw_value})

    result = await repo.get_cache("US_AAPL")
    assert result is not None
    assert result.most_recent_quarter == expected


# --- TargetRepository ---

async def test_target_list_and_find(session):
    """ターゲット一覧と企業別検索"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = TargetRepository(session)
    target = AnalysisTarget(company_id="US_AAPL", source="manual")
    session.add(target)
    await session.flush()
    results = await repo.list_targets()
    assert len(results) == 1
    found = await repo.find_by_company("US_AAPL")
    assert found is not None


async def test_target_bulk_add(session):
    """一括追加（重複スキップ）"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = TargetRepository(session)
    count = await repo.bulk_add([
        {"company_id": "US_AAPL", "source": "screening"},
        {"company_id": "US_MSFT", "source": "screening"},
    ])
    assert count == 2
    # 重複追加 → スキップ
    count = await repo.bulk_add([
        {"company_id": "US_AAPL", "source": "screening"},
    ])
    assert count == 0


async def test_target_bulk_add_intra_batch_duplicates(session):
    """同一バッチ内の重複 company_id は 1 回だけ挿入される (ON CONFLICT DO NOTHING)."""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = TargetRepository(session)
    count = await repo.bulk_add([
        {"company_id": "US_AAPL", "source": "screening"},
        {"company_id": "US_AAPL", "source": "screening"},  # intra-batch dup
        {"company_id": "US_MSFT", "source": "screening"},
    ])
    assert count == 2
    targets = await repo.list_targets()
    assert len(targets) == 2


async def test_target_bulk_add_partial_existing_returns_only_new_count(session):
    """既存 + 新規の混在バッチで、新規分の件数のみが返ることを確認."""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_GOOG", ticker="GOOG", name="Google",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = TargetRepository(session)
    await repo.bulk_add([{"company_id": "US_AAPL", "source": "manual"}])
    count = await repo.bulk_add([
        {"company_id": "US_AAPL", "source": "screening"},  # existing
        {"company_id": "US_MSFT", "source": "screening"},  # new
        {"company_id": "US_GOOG", "source": "screening"},  # new
    ])
    assert count == 2
    targets = await repo.list_targets()
    assert len(targets) == 3


# --- DocumentIndexRepository ---

async def test_document_index_save_and_get(session):
    """インデックスの保存と取得"""
    f = await _setup_company_and_filing(session)
    repo = DocumentIndexRepository(session)
    di = await repo.save_index(
        filing_id=f.id, company_id="US_AAPL",
        data={"index_json": '{"nodes": []}', "model_name": "test",
              "page_count": 10, "node_count": 5},
    )
    assert di.id is not None
    result = await repo.get_by_filing(f.id)
    assert result is not None
    assert result.page_count == 10


class TestScreeningRepositoryEligible:
    @pytest.mark.asyncio
    async def test_lists_companies_without_cache_excluding_ticker_none(self, session):
        """ScreeningCache 未登録 かつ ticker not NULL の company を返す."""
        session.add_all([
            Company(id="US_AAPL", ticker="AAPL", name="Apple",
                    market="Nasdaq", accounting_standard="US-GAAP"),
            Company(id="US_MSFT", ticker="MSFT", name="MS",
                    market="Nasdaq", accounting_standard="US-GAAP"),
            Company(id="US_DEFUNCT", ticker=None, name="Def",
                    market="DELISTED", accounting_standard="US-GAAP"),
        ])
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=24, limit=None)

        ids = sorted([cid for cid, _ in eligible])
        assert ids == ["US_AAPL", "US_MSFT"]

    @pytest.mark.asyncio
    async def test_lists_stale_cache_rows(self, session):
        """updated_at が stale_hours 超過の cache は eligible."""
        session.add(Company(id="US_AAPL", ticker="AAPL", name="Apple",
                            market="Nasdaq", accounting_standard="US-GAAP"))
        session.add(Company(id="US_MSFT", ticker="MSFT", name="MS",
                            market="Nasdaq", accounting_standard="US-GAAP"))
        await session.flush()
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        fresh = datetime.now(timezone.utc) - timedelta(hours=1)
        session.add(ScreeningCache(company_id="US_AAPL", updated_at=old))
        session.add(ScreeningCache(company_id="US_MSFT", updated_at=fresh))
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=24, limit=None)

        ids = [cid for cid, _ in eligible]
        assert ids == ["US_AAPL"]

    @pytest.mark.asyncio
    async def test_stale_hours_none_returns_all_with_ticker(self, session):
        """stale_hours=None で全件 (キャッシュ存在問わず) eligible."""
        session.add(Company(id="US_AAPL", ticker="AAPL", name="Apple",
                            market="Nasdaq", accounting_standard="US-GAAP"))
        await session.flush()
        session.add(ScreeningCache(
            company_id="US_AAPL",
            updated_at=datetime.now(timezone.utc),
        ))
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=None, limit=None)

        assert [cid for cid, _ in eligible] == ["US_AAPL"]

    @pytest.mark.asyncio
    async def test_limit_truncates_eligible_set(self, session):
        for i in range(5):
            session.add(Company(
                id=f"US_T{i}", ticker=f"T{i}", name=f"T{i}",
                market="Nasdaq", accounting_standard="US-GAAP",
            ))
        await session.flush()

        repo = ScreeningRepository(session)
        eligible = await repo.list_eligible_for_enrich(stale_hours=24, limit=2)

        assert len(eligible) == 2


class TestCompanyRepositoryFindExistingIds:
    @pytest.mark.asyncio
    async def test_returns_set_of_existing_ids(self, session):
        session.add_all([
            Company(id="US_AAPL", ticker="AAPL", name="Apple",
                    market="Nasdaq", accounting_standard="US-GAAP"),
            Company(id="US_MSFT", ticker="MSFT", name="MS",
                    market="Nasdaq", accounting_standard="US-GAAP"),
        ])
        await session.flush()

        repo = CompanyRepository(session)
        result = await repo.find_existing_ids(["US_AAPL", "US_MSFT", "US_NOPE"])

        assert result == {"US_AAPL", "US_MSFT"}

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_set(self, session):
        repo = CompanyRepository(session)
        result = await repo.find_existing_ids([])
        assert result == set()
