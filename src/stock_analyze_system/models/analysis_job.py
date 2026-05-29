"""バックグラウンド LLM 分析ジョブモデル"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from stock_analyze_system.models.base import Base
from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"))
    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.PENDING.value,
    )
    progress_current: Mapped[int] = mapped_column(default=0)
    progress_total: Mapped[int] = mapped_column(default=len(ANALYSIS_TYPE_NAMES))
    current_analysis_type: Mapped[str | None] = mapped_column(
        String(30), default=None,
    )
    error_details: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )

    __table_args__ = (
        Index(
            "uq_analysis_jobs_active",
            "company_id", "filing_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )
