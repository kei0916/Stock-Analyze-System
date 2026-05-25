"""WatchlistRepository のテスト"""
import pytest

from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.repositories.watchlist import WatchlistRepository


@pytest.fixture
async def watchlist_repo(session):
    return WatchlistRepository(session)


@pytest.fixture
async def sample_watchlist(session, sample_company):
    wl = Watchlist(name="test_watchlist")
    session.add(wl)
    await session.flush()
    return wl


class TestGetByName:
    async def test_found(self, session, watchlist_repo, sample_watchlist):
        result = await watchlist_repo.get_by_name("test_watchlist")
        assert result is not None
        assert result.name == "test_watchlist"

    async def test_not_found(self, watchlist_repo):
        result = await watchlist_repo.get_by_name("nonexistent")
        assert result is None


class TestAddItem:
    async def test_adds_item(self, watchlist_repo, sample_watchlist):
        item = await watchlist_repo.add_item(
            sample_watchlist.id, "US_AAPL",
            status="watching", investment_thesis="Strong brand",
        )
        assert item.company_id == "US_AAPL"
        assert item.status == "watching"
        assert item.investment_thesis == "Strong brand"

    async def test_default_status(self, watchlist_repo, sample_watchlist):
        item = await watchlist_repo.add_item(sample_watchlist.id, "US_AAPL")
        assert item.status == "monitoring"


class TestDeleteItem:
    async def test_deletes_item(self, session, watchlist_repo, sample_watchlist):
        item = await watchlist_repo.add_item(sample_watchlist.id, "US_AAPL")
        await watchlist_repo.delete_item(item)
        found = await watchlist_repo.find_item(sample_watchlist.id, "US_AAPL")
        assert found is None


class TestFindItem:
    async def test_finds_existing(self, watchlist_repo, sample_watchlist):
        await watchlist_repo.add_item(sample_watchlist.id, "US_AAPL")
        found = await watchlist_repo.find_item(sample_watchlist.id, "US_AAPL")
        assert found is not None
        assert found.company_id == "US_AAPL"

    async def test_returns_none_for_missing(self, watchlist_repo, sample_watchlist):
        found = await watchlist_repo.find_item(sample_watchlist.id, "US_NONEXIST")
        assert found is None


class TestGetWithItems:
    async def test_get_with_items_loads_items_eagerly(self, session, watchlist_repo, sample_company):
        """get_with_items が relationship を eager load すること"""
        wl = Watchlist(name="tech")
        session.add(wl)
        await session.flush()
        session.add(WatchlistItem(
            watchlist_id=wl.id, company_id="US_AAPL", status="monitoring",
        ))
        await session.flush()

        loaded = await watchlist_repo.get_with_items(wl.id)

        assert loaded is not None
        # selectinload 済みなので items は既に読み込まれている
        assert len(loaded.items) == 1
        assert loaded.items[0].company_id == "US_AAPL"

    async def test_get_with_items_empty_list(self, session, watchlist_repo, sample_company):
        """get_with_items が items なしでも動作すること"""
        wl = Watchlist(name="empty")
        session.add(wl)
        await session.flush()

        loaded = await watchlist_repo.get_with_items(wl.id)

        assert loaded is not None
        assert loaded.items == []

    async def test_get_with_items_none_if_missing(self, watchlist_repo):
        result = await watchlist_repo.get_with_items(999)
        assert result is None
