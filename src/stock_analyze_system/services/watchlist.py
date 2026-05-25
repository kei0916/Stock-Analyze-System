"""ウォッチリストサービス"""
from __future__ import annotations

import logging

from stock_analyze_system.exceptions import DuplicateError, NotFoundError
from stock_analyze_system.repositories.watchlist import WatchlistRepository

logger = logging.getLogger(__name__)


class WatchlistService:
    """ウォッチリストの CRUD サービス"""

    def __init__(self, watchlist_repo: WatchlistRepository):
        self._repo = watchlist_repo

    async def create_watchlist(self, name: str, description: str | None = None):
        """ウォッチリストを作成（名前重複で DuplicateError）"""
        existing = await self._repo.get_by_name(name)
        if existing is not None:
            raise DuplicateError(f"Watchlist '{name}' already exists")
        return await self._repo.upsert({"name": name}, {"description": description})

    async def list_watchlists(self):
        return await self._repo.list_all()

    async def add_item(
        self, watchlist_id: int, company_id: str,
        status: str = "monitoring", investment_thesis: str | None = None,
    ):
        """アイテムを追加（重複で DuplicateError）"""
        wl = await self._repo.get_by_id(watchlist_id)
        if wl is None:
            raise NotFoundError(f"Watchlist {watchlist_id} not found")
        existing = await self._repo.find_item(watchlist_id, company_id)
        if existing is not None:
            raise DuplicateError(
                f"Company {company_id} already in watchlist {watchlist_id}",
            )
        return await self._repo.add_item(
            watchlist_id, company_id,
            status=status, investment_thesis=investment_thesis,
        )

    async def remove_item(self, watchlist_id: int, company_id: str):
        """アイテムを削除（未検出で NotFoundError）"""
        item = await self._repo.find_item(watchlist_id, company_id)
        if item is None:
            raise NotFoundError(
                f"Company {company_id} not in watchlist {watchlist_id}",
            )
        await self._repo.delete_item(item)

    async def get_with_items(self, watchlist_id: int):
        """watchlist と items を eager load して取得"""
        return await self._repo.get_with_items(watchlist_id)
