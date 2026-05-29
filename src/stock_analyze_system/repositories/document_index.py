"""ドキュメントインデックスリポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.document_index import DocumentIndex
from stock_analyze_system.repositories.base import BaseRepository


class DocumentIndexRepository(BaseRepository[DocumentIndex]):
    """DocumentIndex ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, DocumentIndex)

    async def get_by_filing(self, filing_id: int) -> DocumentIndex | None:
        """filing_id で検索"""
        stmt = select(DocumentIndex).where(
            DocumentIndex.filing_id == filing_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_index(
        self, filing_id: int, company_id: str, data: dict,
    ) -> DocumentIndex:
        """インデックスを upsert"""
        return await self.upsert(
            {"filing_id": filing_id},
            {"company_id": company_id, **data},
        )
