from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import DateTime, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_analyze_system.models.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(nullable=False)
    ticker: Mapped[str] = mapped_column(nullable=False)
    date: Mapped[date_type] = mapped_column(nullable=False)
    open: Mapped[float | None]
    high: Mapped[float | None]
    low: Mapped[float | None]
    close: Mapped[float | None]
    volume: Mapped[float | None]
    source: Mapped[str] = mapped_column(default="stooq")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_price_history_company_date"),
        Index("idx_price_history_company_date", "company_id", "date"),
        Index("idx_price_history_date", "date"),
    )
