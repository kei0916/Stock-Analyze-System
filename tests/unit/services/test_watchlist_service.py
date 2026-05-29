"""WatchlistService のテスト"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.services.watchlist import WatchlistService
from stock_analyze_system.exceptions import NotFoundError, DuplicateError


class TestWatchlistService:
    async def test_create_watchlist(self):
        repo = AsyncMock()
        repo.get_by_name.return_value = None
        mock_wl = MagicMock(id=1)
        mock_wl.name = "My List"
        repo.upsert.return_value = mock_wl
        svc = WatchlistService(repo)
        result = await svc.create_watchlist("My List")
        assert result.name == "My List"

    async def test_create_watchlist_duplicate(self):
        repo = AsyncMock()
        repo.get_by_name.return_value = MagicMock(name="My List")
        svc = WatchlistService(repo)
        with pytest.raises(DuplicateError):
            await svc.create_watchlist("My List")

    async def test_add_item(self):
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(id=1)
        repo.find_item.return_value = None
        svc = WatchlistService(repo)
        await svc.add_item(1, "US_AAPL")

    async def test_add_item_duplicate(self):
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(id=1)
        repo.find_item.return_value = MagicMock()
        svc = WatchlistService(repo)
        with pytest.raises(DuplicateError):
            await svc.add_item(1, "US_AAPL")

    async def test_remove_item(self):
        item = MagicMock(id=42)
        repo = AsyncMock()
        repo.find_item.return_value = item
        repo.delete.return_value = True
        svc = WatchlistService(repo)
        await svc.remove_item(1, "US_AAPL")

    async def test_remove_item_not_found(self):
        repo = AsyncMock()
        repo.find_item.return_value = None
        svc = WatchlistService(repo)
        with pytest.raises(NotFoundError):
            await svc.remove_item(1, "US_AAPL")
