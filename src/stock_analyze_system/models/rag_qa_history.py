"""RAG Q&A履歴モデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_analyze_system.models.base import Base


class RagQaHistory(Base):
    __tablename__ = "rag_qa_history"
    __table_args__ = (
        Index("ix_rag_qa_history_company_created", "company_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    filing_id: Mapped[int | None] = mapped_column(ForeignKey("filings.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    source_pages_json: Mapped[str] = mapped_column(Text, default="[]")
    source_sections_json: Mapped[str] = mapped_column(Text, default="[]")
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
