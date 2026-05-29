"""ScreeningUniverseService の単体テスト."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.screening_universe import (
    ScreeningUniverseService,
)
from tests.fixtures.sec_company_tickers_payload import sec_universe_payload
from tests.fixtures.yahoo_screening_responses import (
    yahoo_full_response,
    yahoo_ratelimit_side_effect,
)


@pytest.fixture
def sec_client():
    c = MagicMock()
    c.list_universe = AsyncMock(return_value=[
        {"ticker": e["ticker"], "cik": e["cik"], "name": e["name"], "exchange": e["exchange"]}
        for e in _normalize_payload(sec_universe_payload())
    ])
    return c


@pytest.fixture
def yahoo_client():
    c = MagicMock()
    c.get_screening_info = AsyncMock(return_value=None)
    return c


def _normalize_payload(payload: dict) -> list[dict]:
    fields = payload["fields"]
    idx = {f: i for i, f in enumerate(fields)}
    out = []
    for row in payload["data"]:
        out.append({
            "ticker": str(row[idx["ticker"]] or ""),
            "cik": f"{int(row[idx['cik']]):010d}",
            "name": str(row[idx["name"]] or ""),
            "exchange": str(row[idx["exchange"]] or ""),
        })
    return out


class TestRefreshUniverse:
    @pytest.mark.asyncio
    async def test_inserts_new_companies(self, session, sec_client, yahoo_client):
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        result = await svc.refresh_universe()

        assert result.fetched >= 18    # 15 + 3 anomalies that pass through (1 skipped is 9999003)
        assert result.inserted >= 15   # at least 15 normal entries
        assert result.skipped >= 2     # ticker="" and name="" rows
        # AAPL must exist
        co = await session.get(Company, "US_AAPL")
        assert co is not None
        assert co.ticker == "AAPL"
        assert co.market == "Nasdaq"
        assert co.accounting_standard == "US-GAAP"

    @pytest.mark.asyncio
    async def test_inserts_unknown_exchange_as_UNKNOWN(self, session, sec_client, yahoo_client):
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        await svc.refresh_universe()
        co = await session.get(Company, "US_UNKEX")
        assert co is not None
        assert co.market == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_accounting_standard(
        self, session, sec_client, yahoo_client,
    ):
        # 既存 TSM が IFRS で登録されている前提
        session.add(Company(
            id="US_TSM", ticker="TSM",
            name="OLD NAME",  # name は更新されることを併せて確認
            market="OLD_MARKET",
            accounting_standard="IFRS",
            cik="0001046179",
        ))
        await session.flush()

        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        await svc.refresh_universe()
        co = await session.get(Company, "US_TSM")
        assert co.accounting_standard == "IFRS"   # 上書きされていない
        assert co.name == "Taiwan Semiconductor Manufacturing Co"  # 更新されている
        assert co.market == "NYSE"                  # 更新されている

    @pytest.mark.asyncio
    async def test_idempotent_second_call_inserts_nothing(
        self, session, sec_client, yahoo_client,
    ):
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=sec_client,
            yahoo_client=yahoo_client,
        )
        first = await svc.refresh_universe()
        second = await svc.refresh_universe()
        assert second.inserted == 0
        assert second.fetched == first.fetched




def _seed_company(session, id, ticker):
    session.add(Company(
        id=id, ticker=ticker, name=ticker,
        market="Nasdaq", accounting_standard="US-GAAP",
    ))


class TestEnrichWithYahooBatch:
    @pytest.mark.asyncio
    async def test_fills_all_fields_from_full_response(self, session):
        _seed_company(session, "US_AAPL", "AAPL")
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(
            return_value={"AAPL": yahoo_full_response("AAPL")},
        )
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24, limit=None)

        assert result.attempted == 1
        assert result.succeeded == 1
        assert result.failed == 0
        yahoo.get_screening_info_batch.assert_called_once_with(["AAPL"])

        cache = await session.get(ScreeningCache, "US_AAPL")
        assert cache is not None
        assert cache.trailing_per == 28.4
        assert cache.roe == 1.45
        assert cache.market_cap == 3.5e12
        # production batch API は sector を返さないが、service 層が dict を
        # そのまま渡すことを検証するため個別API用 fixture を流用している
        assert cache.sector == "Technology"
        assert cache.exchange == "Nasdaq"
        assert cache.most_recent_quarter == date(2026, 3, 31)
        assert cache.last_fiscal_year_end == date(2025, 12, 31)

    @pytest.mark.asyncio
    async def test_yahoo_date_strings_are_normalized_before_commit(self, session):
        _seed_company(session, "US_AAPL", "AAPL")
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            "AAPL": {
                "stock_price": 232.0,
                "market_cap": 3.5e12,
                "most_recent_quarter": "2026-03-31",
                "last_fiscal_year_end": "2025-12-31",
            },
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )

        result = await svc.enrich_with_yahoo(stale_hours=24, limit=None)

        assert result.succeeded == 1
        assert result.failed == 0
        cache = await session.get(ScreeningCache, "US_AAPL")
        assert cache is not None
        assert cache.most_recent_quarter == date(2026, 3, 31)
        assert cache.last_fiscal_year_end == date(2025, 12, 31)

    @pytest.mark.asyncio
    async def test_batch_partial_failure_skips_missing(self, session):
        """バッチ内の一部銘柄がレスポンスに含まれない場合はスキップ"""
        for tk in ("AAPL", "MSFT", "FAIL", "TSLA", "JPM"):
            _seed_company(session, f"US_{tk}", tk)
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            "AAPL": yahoo_full_response("AAPL"),
            "MSFT": yahoo_full_response("MSFT"),
            "TSLA": yahoo_full_response("TSLA"),
            "JPM": yahoo_full_response("JPM"),
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.attempted == 5
        assert result.succeeded == 4
        assert result.skipped == 1
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_yahoo_returns_empty_increments_skipped(self, session):
        _seed_company(session, "US_EMPTY", "EMPTY")
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={})
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.skipped == 1
        assert result.succeeded == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_batch_fetch_exception_logs_and_skips_all(self, session, caplog):
        """get_screening_info_batch が例外を投げると全件 skipped 扱い"""
        _seed_company(session, "US_RL", "RL")
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(
            side_effect=yahoo_ratelimit_side_effect(),
        )
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        with caplog.at_level(
            "ERROR", logger="stock_analyze_system.services.screening_universe",
        ):
            result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.skipped == 1
        assert result.succeeded == 0
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert errors
        assert errors[0].exc_info is not None

    @pytest.mark.asyncio
    async def test_batch_db_failure_falls_back_to_individual(self, session, caplog):
        """バッチDB保存失敗時は個別upsertにフォールバック"""
        _seed_company(session, "US_AAPL", "AAPL")
        _seed_company(session, "US_MSFT", "MSFT")
        # rollback() 後も Company 行が残るように flush ではなく commit する
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            "AAPL": {"stock_price": 150.0, "trailing_per": 25.0},
            "MSFT": {"stock_price": 300.0, "trailing_per": 30.0},
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )

        async def broken_bulk(*args, **kwargs):
            raise RuntimeError("DB deadlock")
        svc._screening_repo.bulk_upsert_cache = broken_bulk

        with caplog.at_level(
            "WARNING", logger="stock_analyze_system.services.screening_universe",
        ):
            result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.succeeded == 2
        assert result.failed == 0
        assert result.skipped == 0

        session.expire_all()
        cache = await session.get(ScreeningCache, "US_AAPL")
        assert cache is not None
        assert cache.stock_price == 150.0

    @pytest.mark.asyncio
    async def test_fallback_tracks_failed_count(self, session):
        """フォールバック時に個別upsert失敗をfailedに集計する"""
        _seed_company(session, "US_GOOD", "GOOD")
        _seed_company(session, "US_BAD", "BAD")
        await session.commit()

        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            "GOOD": {"stock_price": 100.0},
            "BAD": {"stock_price": 200.0},
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )

        async def broken_bulk(*args, **kwargs):
            raise RuntimeError("DB deadlock")

        original_upsert = svc._screening_repo.upsert_cache

        async def selective_fail(cid, data):
            if "BAD" in cid:
                raise RuntimeError("constraint violation")
            return await original_upsert(cid, data)

        svc._screening_repo.bulk_upsert_cache = broken_bulk
        svc._screening_repo.upsert_cache = selective_fail

        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.succeeded == 1
        assert result.failed == 1
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_excludes_ticker_none_companies(self, session):
        _seed_company(session, "US_AAPL", "AAPL")
        session.add(Company(id="US_DEFUNCT", ticker=None, name="Def",
                            market="DELISTED", accounting_standard="US-GAAP"))
        await session.commit()
        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(
            return_value={"AAPL": yahoo_full_response("AAPL")},
        )
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24)

        assert result.attempted == 1   # DEFUNCT は eligible に出ない
        yahoo.get_screening_info_batch.assert_called_once_with(["AAPL"])

    @pytest.mark.asyncio
    async def test_limit_truncates_attempted(self, session):
        for i in range(5):
            _seed_company(session, f"US_T{i}", f"T{i}")
        await session.commit()
        yahoo = MagicMock()
        yahoo.get_screening_info_batch = AsyncMock(return_value={
            f"T{i}": yahoo_full_response(f"T{i}") for i in range(3)
        })
        svc = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=yahoo,
        )
        result = await svc.enrich_with_yahoo(stale_hours=24, limit=3)
        assert result.attempted == 3
