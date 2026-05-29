"""ScreeningService の単体テスト."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.repositories.target import TargetRepository
from stock_analyze_system.services.analysis_target import AnalysisTargetService
from stock_analyze_system.services.screening import (
    SCREENING_NUMERIC_FIELDS,
    FilterClause,
    ScreenSpec,
    ScreeningService,
    SortSpec,
)
from tests.fixtures.screening_universe import screening_universe_seeds


def _svc():
    return ScreeningService(
        screening_repo=MagicMock(),
        company_repo=MagicMock(),
        target_service=MagicMock(),
    )


class TestValidate:
    def test_unknown_field_rejected(self):
        with pytest.raises(ValueError, match="unknown field"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("company_id", "gte", 0)
            ]))

    def test_sql_injection_in_field_rejected(self):
        with pytest.raises(ValueError, match="unknown field"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per; DROP TABLE companies", "gte", 0)
            ]))

    def test_eq_on_numeric_rejected(self):
        with pytest.raises(ValueError, match="not allowed on numeric"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "eq", 15)
            ]))

    def test_in_on_numeric_rejected(self):
        with pytest.raises(ValueError, match="not allowed on numeric"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "in", [1, 2])
            ]))

    def test_gte_on_categorical_rejected(self):
        with pytest.raises(ValueError, match="not allowed on categorical"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("sector", "gte", 1)
            ]))

    def test_between_inverted_range_rejected(self):
        with pytest.raises(ValueError, match="lower must be <= upper"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "between", (15, 5))
            ]))

    def test_between_single_value_rejected(self):
        with pytest.raises(ValueError, match="2-tuple"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("trailing_per", "between", (15,))
            ]))

    def test_in_with_non_list_value_rejected(self):
        with pytest.raises(ValueError, match="list/tuple"):
            _svc()._validate(ScreenSpec(filters=[
                FilterClause("sector", "in", "Nasdaq")
            ]))

    def test_limit_zero_rejected(self):
        with pytest.raises(ValueError, match="limit"):
            _svc()._validate(ScreenSpec(limit=0))

    def test_limit_over_1000_rejected(self):
        with pytest.raises(ValueError, match="limit"):
            _svc()._validate(ScreenSpec(limit=1001))

    def test_negative_offset_rejected(self):
        with pytest.raises(ValueError, match="offset"):
            _svc()._validate(ScreenSpec(offset=-1))

    def test_unknown_sort_field_rejected(self):
        with pytest.raises(ValueError, match="unknown sort field"):
            _svc()._validate(ScreenSpec(sort=SortSpec("company_id")))

    def test_valid_spec_passes(self):
        _svc()._validate(ScreenSpec(
            filters=[
                FilterClause("trailing_per", "between", (0, 15)),
                FilterClause("roe", "gte", 0.15),
                FilterClause("sector", "in", ["Technology"]),
            ],
            sort=SortSpec("market_cap"),
            limit=50,
            offset=0,
        ))


async def _seed_universe(session) -> ScreeningService:
    for seed in screening_universe_seeds():
        session.add(Company(**seed.company))
    await session.flush()
    for seed in screening_universe_seeds():
        if seed.cache is not None:
            session.add(ScreeningCache(company_id=seed.company["id"], **seed.cache))
    await session.flush()
    return ScreeningService(
        screening_repo=ScreeningRepository(session),
        company_repo=CompanyRepository(session),
        target_service=AnalysisTargetService(TargetRepository(session)),
    )


async def _seed_uncached_company(
    session,
    *,
    company_id: str = "US_NOCACHE",
    ticker: str = "NOCACHE",
    market: str = "NYSE",
    sector: str = "Utilities",
) -> None:
    session.add(Company(
        id=company_id,
        ticker=ticker,
        name="No Cache Corp",
        market=market,
        accounting_standard="US-GAAP",
        cik="0002222222",
        sector=sector,
    ))
    await session.flush()


class TestRunScreen:
    @pytest.mark.asyncio
    async def test_unconditional_screen_includes_sec_companies_without_cache(self, session):
        svc = await _seed_universe(session)
        await _seed_uncached_company(session)

        result = await svc.run_screen(ScreenSpec(limit=50))

        by_id = {it.company_id: it for it in result.items}
        assert result.total_matched == 16  # 15 cached + 1 uncached ticker/CIK company
        assert "US_NOCACHE" in by_id
        assert by_id["US_NOCACHE"].ticker == "NOCACHE"
        assert by_id["US_NOCACHE"].sector == "Utilities"
        assert all(v is None for v in by_id["US_NOCACHE"].metrics.values())

    @pytest.mark.asyncio
    async def test_numeric_filter_excludes_uncached_unless_include_null(self, session):
        svc = await _seed_universe(session)
        await _seed_uncached_company(session)

        default = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "gte", 0)],
            limit=50,
        ))
        with_null = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "gte", 0)],
            include_null=True,
            limit=50,
        ))

        assert "US_NOCACHE" not in {it.company_id for it in default.items}
        assert "US_NOCACHE" in {it.company_id for it in with_null.items}

    @pytest.mark.asyncio
    async def test_exchange_filter_uses_company_market_when_cache_missing(self, session):
        svc = await _seed_universe(session)
        await _seed_uncached_company(session, market="AMEX")

        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("exchange", "eq", "AMEX")],
            limit=50,
        ))

        ids = {it.company_id for it in result.items}
        assert ids == {"US_NOCACHE"}

    @pytest.mark.asyncio
    async def test_default_sort_is_market_cap_desc(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(limit=20))
        ids = [it.company_id for it in result.items]
        assert ids[0] == "US_AAPL"   # mc=3.5T 最大
        assert ids[1] == "US_MSFT"   # mc=3.0T 次

    @pytest.mark.asyncio
    async def test_returns_full_metrics_dict(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(limit=1))
        item = result.items[0]
        assert set(item.metrics.keys()) == set(SCREENING_NUMERIC_FIELDS)

    @pytest.mark.asyncio
    async def test_excludes_null_by_default(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "gte", 0)],
        ))
        # PLTR / IZEA / CETX は trailing_per=None で除外、 BRK-A など 9 件残る
        ids = {it.company_id for it in result.items}
        assert "US_PLTR" not in ids
        assert "US_IZEA" not in ids
        assert "US_CETX" not in ids
        assert "US_AAPL" in ids

    @pytest.mark.asyncio
    async def test_includes_null_when_include_null_true(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "gte", 0)],
            include_null=True,
        ))
        ids = {it.company_id for it in result.items}
        assert "US_PLTR" in ids   # trailing_per=None でも include_null=True で残る

    @pytest.mark.asyncio
    async def test_between_inclusive_at_boundaries(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("trailing_per", "between", (9.5, 28.4))],
        ))
        ids = {it.company_id for it in result.items}
        # BRK-A (9.5) と BRK-B (9.5) と AAPL (28.4) が含まれる (BETWEEN inclusive)
        assert {"US_BRK-A", "US_BRK-B", "US_AAPL"}.issubset(ids)

    @pytest.mark.asyncio
    async def test_handles_inf_excludes_under_lte_threshold(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("psr", "lte", 100)],
        ))
        ids = {it.company_id for it in result.items}
        assert "US_CETX" not in ids   # psr=inf で除外

    @pytest.mark.asyncio
    async def test_handles_nan_excluded(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("pbr", "gte", 0)],
        ))
        ids = {it.company_id for it in result.items}
        assert "US_CETX" not in ids   # pbr=NaN は SQL で常に false

    @pytest.mark.asyncio
    async def test_offset_beyond_total_returns_empty(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(limit=10, offset=1000))
        assert result.items == []
        assert result.total_matched > 0

    @pytest.mark.asyncio
    async def test_categorical_eq_case_sensitive(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("exchange", "eq", "nasdaq")],   # 小文字
        ))
        assert result.items == []

    @pytest.mark.asyncio
    async def test_unicode_sector_filter(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("sector", "eq", "技術")],
        ))
        ids = {it.company_id for it in result.items}
        assert ids == {"US_SONY"}

    @pytest.mark.asyncio
    async def test_negative_roe_passes_gte_negative_threshold(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("roe", "gte", -0.5)],
            limit=50,
        ))
        ids = {it.company_id for it in result.items}
        assert "US_PLTR" in ids   # roe=-0.12

    @pytest.mark.asyncio
    async def test_dash_in_ticker_preserved_in_response(self, session):
        svc = await _seed_universe(session)
        result = await svc.run_screen(ScreenSpec(
            filters=[FilterClause("exchange", "eq", "NYSE")],
            limit=50,
        ))
        ids = {it.company_id for it in result.items}
        assert "US_BRK-A" in ids


class TestGetDistribution:
    @pytest.mark.asyncio
    async def test_buckets_partition_correctly(self, session):
        # custom seed: roe = 0.0..0.9 in 10-step
        for i in range(10):
            session.add(Company(
                id=f"US_T{i}", ticker=f"T{i}", name=f"T{i}",
                market="Nasdaq", accounting_standard="US-GAAP",
            ))
        await session.flush()
        for i in range(10):
            session.add(ScreeningCache(
                company_id=f"US_T{i}", roe=i * 0.1,
            ))
        await session.flush()
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        dist = await svc.get_distribution("roe", buckets=5)
        assert dist.min == 0.0
        assert dist.max == 0.9
        # 10 値 / 5 buckets = 2 per bucket (last bucket is inclusive on upper)
        assert sum(b.count for b in dist.buckets) == 10
        assert all(b.count == 2 for b in dist.buckets)

    @pytest.mark.asyncio
    async def test_rejects_categorical_field(self, session):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="numeric"):
            await svc.get_distribution("sector")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("buckets", [0, 101])
    async def test_rejects_buckets_outside_1_to_100(self, session, buckets):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="buckets"):
            await svc.get_distribution("trailing_per", buckets=buckets)

    @pytest.mark.asyncio
    async def test_all_null_column_returns_zero_count(self, session):
        session.add(Company(
            id="US_X", ticker="X", name="X",
            market="Nasdaq", accounting_standard="US-GAAP",
        ))
        session.add(ScreeningCache(company_id="US_X", roe=None))
        await session.flush()
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        dist = await svc.get_distribution("roe", buckets=5)
        assert dist.min is None
        assert dist.max is None
        assert dist.finite_count == 0
        assert dist.null_count == 1
        assert dist.buckets == []

    @pytest.mark.asyncio
    async def test_constant_column_collapses_to_single_bucket(self, session):
        for i in range(3):
            session.add(Company(
                id=f"US_C{i}", ticker=f"C{i}", name=f"C{i}",
                market="Nasdaq", accounting_standard="US-GAAP",
            ))
        await session.flush()
        for i in range(3):
            session.add(ScreeningCache(company_id=f"US_C{i}", beta=1.0))
        await session.flush()
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        dist = await svc.get_distribution("beta", buckets=5)
        assert dist.min == 1.0
        assert dist.max == 1.0
        assert len(dist.buckets) == 1
        assert dist.buckets[0].count == 3

    @pytest.mark.asyncio
    async def test_excludes_inf_from_min_max(self, session):
        svc = await _seed_universe(session)   # CETX has psr=inf, de_ratio=inf
        dist = await svc.get_distribution("psr", buckets=5)
        assert dist.max != float("inf")
        assert dist.non_finite_count >= 1   # CETX (psr=inf) counted


class TestAddToTargets:
    @pytest.mark.asyncio
    async def test_rejects_empty_list(self, session):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="non-empty"):
            await svc.add_to_targets([])

    @pytest.mark.asyncio
    async def test_rejects_over_100_ids(self, session):
        svc = ScreeningService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            target_service=AnalysisTargetService(TargetRepository(session)),
        )
        with pytest.raises(ValueError, match="max 100"):
            await svc.add_to_targets([f"US_T{i}" for i in range(101)])

    @pytest.mark.asyncio
    async def test_dedupes_duplicate_ids(self, session):
        svc = await _seed_universe(session)
        result = await svc.add_to_targets(["US_AAPL", "US_AAPL"])
        assert result.requested == 2
        assert result.added == 1
        assert result.already_present == 0

    @pytest.mark.asyncio
    async def test_skips_unknown_company_ids(self, session):
        svc = await _seed_universe(session)
        result = await svc.add_to_targets(["US_AAPL", "US_NONEXISTENT"])
        assert result.added == 1
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_counts_already_present_correctly(self, session):
        svc = await _seed_universe(session)
        first = await svc.add_to_targets(["US_AAPL"])
        assert first.added == 1
        second = await svc.add_to_targets(["US_AAPL"])
        assert second.added == 0
        assert second.already_present == 1
        assert second.skipped == 0
