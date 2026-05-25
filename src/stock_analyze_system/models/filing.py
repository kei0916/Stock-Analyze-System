"""提出書類モデル"""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (Index("ix_filing_company_year", "company_id", "fiscal_year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source: Mapped[str] = mapped_column(String(10))
    filing_type: Mapped[str] = mapped_column(String(10))
    period_type: Mapped[str] = mapped_column(String(10))
    fiscal_year: Mapped[int] = mapped_column()
    period_end: Mapped[date | None] = mapped_column(Date, default=None)
    filed_at: Mapped[date | None] = mapped_column(Date, default=None)
    accession_no: Mapped[str | None] = mapped_column(String(30), unique=True, default=None)
    doc_id: Mapped[str | None] = mapped_column(String(30), unique=True, default=None)
    storage_path: Mapped[str | None] = mapped_column(Text, default=None)
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    last_updated: Mapped[datetime] = mapped_column(server_default=func.now())
    company = relationship("Company", back_populates="filings")
