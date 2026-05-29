"""RAG Q&A履歴リポジトリ"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.rag_qa_history import RagQaHistory
from stock_analyze_system.repositories.base import BaseRepository
from stock_analyze_system.shared.json_utils import json_dumps_ja


class RagQaHistoryRepository(BaseRepository[RagQaHistory]):
    """RagQaHistory ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RagQaHistory)

    async def add(
        self,
        *,
        company_id: str,
        filing_id: int | None,
        question: str,
        answer: str,
        source_pages: list,
        source_sections: list,
        model_name: str | None,
        confidence: float | None,
    ) -> RagQaHistory:
        row = RagQaHistory(
            company_id=company_id,
            filing_id=filing_id,
            question=question,
            answer=answer,
            source_pages_json=json_dumps_ja(source_pages or []),
            source_sections_json=json_dumps_ja(source_sections or []),
            model_name=model_name,
            confidence=confidence,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_company(
        self, company_id: str, *, limit: int = 50,
    ) -> list[RagQaHistory]:
        stmt = (
            select(RagQaHistory)
            .where(RagQaHistory.company_id == company_id)
            .order_by(RagQaHistory.created_at.desc(), RagQaHistory.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def to_dict(row: RagQaHistory) -> dict:
        return {
            "id": row.id,
            "company_id": row.company_id,
            "filing_id": row.filing_id,
            "question": row.question,
            "answer": row.answer,
            "source_pages": json.loads(row.source_pages_json or "[]"),
            "source_sections": json.loads(row.source_sections_json or "[]"),
            "model_name": row.model_name,
            "confidence": row.confidence,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
