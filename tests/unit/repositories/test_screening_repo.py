"""ScreeningRepository.bulk_upsert_cache のテスト"""

from __future__ import annotations

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.screening import ScreeningRepository


def _seed_companies(session, *cids: str) -> None:
    for cid in cids:
        ticker = cid.split("_", 1)[1]
        session.add(
            Company(
                id=cid,
                ticker=ticker,
                name=ticker,
                market="Nasdaq",
                accounting_standard="US-GAAP",
            )
        )


class TestBulkUpsertCache:
    async def test_preserves_omitted_columns_on_update(self, session):
        """payloadに存在しない列は既存値を上書きしない"""
        _seed_companies(session, "US_AAPL", "US_MSFT")
        await session.flush()
        repo = ScreeningRepository(session)

        await repo.upsert_cache(
            "US_AAPL",
            {
                "stock_price": 100.0,
                "trailing_per": 20.0,
                "sector": "Technology",
                "roe": 0.15,
            },
        )
        await session.flush()

        await repo.bulk_upsert_cache(
            [
                ("US_AAPL", {"stock_price": 150.0, "market_cap": 2_000_000_000_000}),
                ("US_MSFT", {"stock_price": 300.0, "trailing_per": 25.0}),
            ]
        )
        await session.flush()
        session.expire_all()

        aapl = await repo.get_cache("US_AAPL")
        assert aapl.stock_price == 150.0
        assert aapl.market_cap == 2_000_000_000_000
        assert aapl.trailing_per == 20.0
        assert aapl.sector == "Technology"
        assert aapl.roe == 0.15

        msft = await repo.get_cache("US_MSFT")
        assert msft.stock_price == 300.0
        assert msft.trailing_per == 25.0

    async def test_mixed_key_shapes(self, session):
        """payload毎にキー集合が異なっても、各キーは正しい列だけ更新される"""
        _seed_companies(session, "US_AAPL", "US_MSFT")
        await session.flush()
        repo = ScreeningRepository(session)

        await repo.upsert_cache(
            "US_AAPL",
            {"stock_price": 100.0, "trailing_per": 20.0},
        )
        await repo.upsert_cache(
            "US_MSFT",
            {"stock_price": 200.0, "market_cap": 1e12},
        )
        await session.flush()

        await repo.bulk_upsert_cache(
            [
                ("US_AAPL", {"stock_price": 150.0}),
                ("US_MSFT", {"stock_price": 300.0, "pbr": 5.0}),
            ]
        )
        await session.flush()
        session.expire_all()

        aapl = await repo.get_cache("US_AAPL")
        assert aapl.stock_price == 150.0
        assert aapl.trailing_per == 20.0

        msft = await repo.get_cache("US_MSFT")
        assert msft.stock_price == 300.0
        assert msft.market_cap == 1e12
        assert msft.pbr == 5.0

    async def test_empty_payloads(self, session):
        """空リストの場合は何もしない"""
        repo = ScreeningRepository(session)
        result = await repo.bulk_upsert_cache([])
        assert result == 0

    async def test_all_new_inserts(self, session):
        """全件新規insert"""
        _seed_companies(session, "US_AAPL", "US_MSFT")
        await session.flush()
        repo = ScreeningRepository(session)

        await repo.bulk_upsert_cache(
            [
                ("US_AAPL", {"stock_price": 100.0, "trailing_per": 20.0}),
                ("US_MSFT", {"stock_price": 200.0, "trailing_per": 25.0}),
            ]
        )
        await session.flush()
        session.expire_all()

        aapl = await repo.get_cache("US_AAPL")
        assert aapl.stock_price == 100.0
        assert aapl.trailing_per == 20.0

    async def test_empty_after_normalize(self, session):
        """normalize後にupdatable列がゼロでもクラッシュしない (DO NOTHING fallback)"""
        _seed_companies(session, "US_X")
        await session.flush()
        repo = ScreeningRepository(session)

        # unknown_column は ScreeningCache に無い → normalize で除外され key_set 空
        await repo.bulk_upsert_cache([("US_X", {"unknown_column": "foo"})])
        await session.flush()
        # クラッシュしないことが本テストの主目的
