"""ファイリングリポジトリ"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.document_index import DocumentIndex
from stock_analyze_system.models.enums import FilingSource
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.base import BaseRepository


class FilingRepository(BaseRepository[Filing]):
    """Filing ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Filing)

    async def get_latest_filing(
        self, company_id: str, filing_type: str,
    ) -> Filing | None:
        """最新ファイリングを取得"""
        stmt = (
            select(Filing)
            .where(
                Filing.company_id == company_id,
                Filing.filing_type == filing_type,
            )
            .order_by(Filing.fiscal_year.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filings(
        self, company_id: str, limit: int | None = None,
    ) -> list[Filing]:
        """企業のファイリング一覧（fiscal_year 降順）"""
        stmt = (
            select(Filing)
            .where(Filing.company_id == company_id)
            .order_by(Filing.fiscal_year.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_any_type(
        self, company_id: str,
    ) -> Filing | None:
        """全 type のうち最新ファイリングを返す (period_end / filed_at の新しい順)"""
        stmt = (
            select(Filing)
            .where(Filing.company_id == company_id)
            .order_by(
                Filing.period_end.desc().nulls_last(),
                Filing.filed_at.desc().nulls_last(),
                Filing.fiscal_year.desc(),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_types(
        self,
        company_id: str,
        filing_types: list[str],
        *,
        since_year: int | None = None,
    ) -> list[Filing]:
        """指定された filing_type の filings を新しい順で返す"""
        stmt = (
            select(Filing)
            .where(
                Filing.company_id == company_id,
                Filing.filing_type.in_(filing_types),
            )
            .order_by(
                Filing.period_end.desc().nulls_last(),
                Filing.fiscal_year.desc(),
            )
        )
        if since_year is not None:
            stmt = stmt.where(Filing.fiscal_year >= since_year)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _find_existing_keys(
        self, column, company_id: str, values: list[str],
    ) -> set[str]:
        if not values:
            return set()
        stmt = select(column).where(
            Filing.company_id == company_id,
            column.in_(values),
        )
        result = await self._session.execute(stmt)
        return {v for v in result.scalars().all() if v is not None}

    async def find_existing_accessions(
        self, company_id: str, accessions: list[str],
    ) -> set[str]:
        return await self._find_existing_keys(
            Filing.accession_no, company_id, accessions,
        )

    async def find_existing_doc_ids(
        self, company_id: str, doc_ids: list[str],
    ) -> set[str]:
        return await self._find_existing_keys(
            Filing.doc_id, company_id, doc_ids,
        )

    async def update_storage(
        self, filing_id: int, storage_path: str, content_hash: str,
    ) -> None:
        """指定 filing の storage_path / content_hash を更新する (idempotent)。"""
        stmt = (
            update(Filing)
            .where(Filing.id == filing_id)
            .values(storage_path=storage_path, content_hash=content_hash)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_latest_with_content(self, company_id: str) -> Filing | None:
        """storage_path が NULL でない filing のうち、period_end → fiscal_year の
        順で最新を返す。"""
        stmt = (
            select(Filing)
            .where(
                Filing.company_id == company_id,
                Filing.storage_path.isnot(None),
            )
            .order_by(
                Filing.period_end.desc().nulls_last(),
                Filing.filed_at.desc().nulls_last(),
                Filing.fiscal_year.desc(),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_recency(self, company_id: str) -> list[Filing]:
        """全 type の filings を period_end / filed_at の新しい順で返す。"""
        stmt = (
            select(Filing)
            .where(Filing.company_id == company_id)
            .order_by(
                Filing.period_end.desc().nulls_last(),
                Filing.filed_at.desc().nulls_last(),
                Filing.fiscal_year.desc(),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_indexed(self, company_id: str) -> Filing | None:
        """document_index に登録がある filing のうち、period_end → fiscal_year の
        順で最新を返す。"""
        stmt = (
            select(Filing)
            .join(DocumentIndex, DocumentIndex.filing_id == Filing.id)
            .where(Filing.company_id == company_id)
            .order_by(
                Filing.period_end.desc().nulls_last(),
                Filing.filed_at.desc().nulls_last(),
                Filing.fiscal_year.desc(),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_company_identifiers(
        self, company_id: str,
    ) -> tuple[str | None, str | None]:
        stmt = select(Company.cik, Company.edinet_code).where(Company.id == company_id)
        result = await self._session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None, None
        return row[0], row[1]

    async def bulk_upsert(
        self, company_id: str, records: list[dict], *, source: FilingSource,
    ) -> int:
        if source is FilingSource.SEC:
            key_col = "accession_no"
        elif source is FilingSource.EDINET:
            key_col = "doc_id"
        else:
            raise ValueError(f"unknown source: {source}")
        if not records:
            return 0
        rows = [{"company_id": company_id, **r} for r in records]
        natural_key_cols = ("company_id", key_col)
        update_cols = [c for c in rows[0].keys() if c not in natural_key_cols]
        await self._bulk_upsert_native(
            rows,
            index_elements=[key_col],
            update_columns=update_cols,
        )
        return len(records)
