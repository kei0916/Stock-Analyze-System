"""スクリーニングキャッシュリポジトリ"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.base import BaseRepository
from stock_analyze_system.services.screening_payload import (
    normalize_screening_cache_payload,
)


class ScreeningRepository(BaseRepository[ScreeningCache]):
    """ScreeningCache ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ScreeningCache)

    async def get_cache(self, company_id: str) -> ScreeningCache | None:
        """キャッシュ取得（PK が company_id）"""
        return await self.get_by_id(company_id)

    async def upsert_cache(self, company_id: str, data: dict) -> ScreeningCache:
        """外部payloadをDB-safeに正規化して ScreeningCache を upsert する。

        Yahoo enrichment などの呼び出し元は ISO 日付文字列や NaN/inf を含む
        vendor payload をそのまま渡してよい。この境界で Date 列・非 finite
        数値・別名キーを永続化可能な値に揃える。
        """
        normalized = normalize_screening_cache_payload(data)
        return await self.upsert({"company_id": company_id}, normalized)

    async def bulk_upsert_cache(
        self, payloads: list[tuple[str, dict]],
    ) -> int:
        """ScreeningCache を一括 upsert.

        payload に存在しない列は既存値を上書きしない。単一 INSERT で複数行を
        渡すと欠落キーが NULL に展開され excluded.col 経由で既存値を上書き
        してしまうため、行ごとにキー集合でグループ化して別 INSERT 文を発行する。

        Args:
            payloads: [(company_id, data_dict), ...] のリスト.

        Returns:
            処理したレコード数.
        """
        if not payloads:
            return 0

        cache_columns = set(ScreeningCache.__table__.columns.keys())
        groups: dict[frozenset[str], list[dict]] = defaultdict(list)
        for company_id, data in payloads:
            normalized = normalize_screening_cache_payload(data)
            key_set = frozenset(normalized.keys())
            groups[key_set].append({"company_id": company_id, **normalized})

        total_rows = 0
        for key_set, records in groups.items():
            update_columns = [c for c in key_set if c in cache_columns]
            await self._bulk_upsert_native(
                records,
                index_elements=["company_id"],
                update_columns=update_columns,
            )
            total_rows += len(records)
        return total_rows

    async def list_stale(self, hours: int = 24) -> list[ScreeningCache]:
        """指定時間以上古いキャッシュ一覧"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = select(ScreeningCache).where(
            ScreeningCache.updated_at < cutoff,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_eligible_for_enrich(
        self,
        stale_hours: int | None,
        limit: int | None,
    ) -> list[tuple[str, str]]:
        """enrich 対象 (cache 未登録 OR cache.updated_at < cutoff) の (company_id, ticker) 一覧.

        Args:
            stale_hours: cache が古いとみなす時間 (hour)。 None なら全件 eligible
                (キャッシュ存在問わず再取得モード)。
            limit: 返却件数の上限。 None なら全件。

        Returns:
            ticker IS NOT NULL に限定した [(company_id, ticker), ...]。
        """
        from stock_analyze_system.models.company import Company

        cutoff: datetime | None
        if stale_hours is None:
            cutoff = None
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)

        stmt = (
            select(Company.id, Company.ticker)
            .outerjoin(ScreeningCache, Company.id == ScreeningCache.company_id)
            .where(Company.ticker.is_not(None))
        )
        if cutoff is not None:
            stmt = stmt.where(
                (ScreeningCache.company_id.is_(None))
                | (ScreeningCache.updated_at < cutoff),
            )
        stmt = stmt.order_by(Company.id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [(row.id, row.ticker) for row in result]
