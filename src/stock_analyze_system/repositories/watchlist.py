"""ウォッチリストリポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.repositories.base import BaseRepository


class WatchlistRepository(BaseRepository[Watchlist]):
    """Watchlist ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Watchlist)

    async def get_by_name(self, name: str) -> Watchlist | None:
        """名前検索"""
        stmt = select(Watchlist).where(Watchlist.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_item(
        self, watchlist_id: int, company_id: str,
    ) -> WatchlistItem | None:
        """アイテム検索"""
        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_item(
        self, watchlist_id: int, company_id: str,
        status: str = "monitoring", investment_thesis: str | None = None,
    ) -> WatchlistItem:
        """アイテム追加"""
        item = WatchlistItem(
            watchlist_id=watchlist_id, company_id=company_id,
            status=status, investment_thesis=investment_thesis,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def delete_item(self, item: WatchlistItem) -> None:
        """アイテム削除"""
        await self._session.delete(item)
        await self._session.flush()

    async def get_with_items(self, watchlist_id: int) -> Watchlist | None:
        """watchlist と items を eager load して取得"""
        stmt = (
            select(Watchlist)
            .where(Watchlist.id == watchlist_id)
            .options(selectinload(Watchlist.items))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
