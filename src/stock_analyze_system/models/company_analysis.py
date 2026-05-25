"""企業分析結果モデル"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

PIPELINE_EXTRACTOR = "extractor"


class CompanyAnalysis(Base):
    __tablename__ = "company_analyses"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "filing_id", "analysis_type", "pipeline",
            name="uq_analysis_key",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"))
    analysis_type: Mapped[str] = mapped_column(String(30))
    result_json: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(100))
    # NULL on rows written by the pre-extractor pipeline; filtered out of cache lookup.
    pipeline: Mapped[str | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    company = relationship("Company", back_populates="analyses")
    filing = relationship("Filing")
