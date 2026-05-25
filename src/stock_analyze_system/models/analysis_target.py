"""分析対象銘柄モデル"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

class AnalysisTarget(Base):
    __tablename__ = "analysis_targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    criteria: Mapped[str | None] = mapped_column(Text, default=None)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    company = relationship("Company")
