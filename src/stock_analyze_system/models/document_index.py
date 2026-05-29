"""PageIndex ツリーインデックスモデル"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

class DocumentIndex(Base):
    __tablename__ = "document_indices"
    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), unique=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    index_json: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(100))
    page_count: Mapped[int] = mapped_column()
    node_count: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_queried_at: Mapped[datetime | None] = mapped_column(default=None)
    filing = relationship("Filing")
    company = relationship("Company")
