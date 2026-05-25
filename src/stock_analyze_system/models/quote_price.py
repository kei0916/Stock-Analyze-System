"""Latest quote price cache model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class QuotePrice(Base):
    __tablename__ = "quote_prices"
    __table_args__ = (
        UniqueConstraint("company_id", "provider", name="uq_quote_price_company_provider"),
        Index("ix_quote_price_provider_status", "provider", "status"),
        Index("ix_quote_price_fetched_at", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="google_sheets")
    provider_symbol: Mapped[str | None] = mapped_column(String(40), default=None)
    price: Mapped[float | None] = mapped_column(default=None)
    currency: Mapped[str | None] = mapped_column(String(3), default=None)
    data_delay_minutes: Mapped[int | None] = mapped_column(default=None)
    as_of: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(String(40), default="missing")
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    raw_value: Mapped[str | None] = mapped_column(String(200), default=None)

    company = relationship("Company")
