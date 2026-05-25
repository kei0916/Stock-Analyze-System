"""ジェネリックCRUDリポジトリ基盤"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select, func as sa_func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

_SQLITE_SAFE_BOUND_PARAMETERS = 900


class BaseRepository(Generic[T]):
    """ジェネリックCRUDリポジトリ"""

    def __init__(self, session: AsyncSession, model: type[T]):
        self._session = session
        self._model = model

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get_by_id(self, id: Any) -> T | None:
        return await self._session.get(self._model, id)

    async def list_all(self, **filters) -> list[T]:
        stmt = select(self._model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model, key) == value)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, filters: dict, data: dict, label: str = "") -> T:
        stmt = select(self._model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model, key) == value)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing

        obj = self._model(**{**filters, **data})
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def delete(self, id: Any) -> bool:
        obj = await self.get_by_id(id)
        if obj is None:
            return False
        await self._session.delete(obj)
        await self._session.flush()
        return True

    async def count(self, **filters) -> int:
        stmt = select(sa_func.count()).select_from(self._model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model, key) == value)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _bulk_upsert_native(
        self,
        rows: list[dict],
        *,
        index_elements: list[str],
        update_columns: list[str],
    ) -> None:
        if not rows:
            return

        max_columns = max(len(row) for row in rows)
        batch_size = max(1, _SQLITE_SAFE_BOUND_PARAMETERS // max_columns)

        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            stmt = sqlite_insert(self._model).values(batch)
            if update_columns:
                stmt = stmt.on_conflict_do_update(
                    index_elements=index_elements,
                    set_={col: stmt.excluded[col] for col in update_columns},
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)
            await self._session.execute(stmt)
        await self._session.flush()

    async def _bulk_upsert_by_natural_key(
        self,
        records: list[dict],
        natural_key_cols: Sequence[str],
        *,
        scope_key: str | None = None,
        scope_value: Any = None,
    ) -> int:
        """自然キーで一括 UPSERT する。"""
        if not records:
            return 0

        if scope_key is not None:
            rows = [{scope_key: scope_value, **r} for r in records]
            index_elements = [scope_key, *natural_key_cols]
        else:
            rows = list(records)
            index_elements = list(natural_key_cols)

        update_columns = [c for c in rows[0].keys() if c not in index_elements]
        await self._bulk_upsert_native(
            rows,
            index_elements=index_elements,
            update_columns=update_columns,
        )
        return len(records)
