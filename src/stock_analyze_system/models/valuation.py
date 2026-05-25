"""バリュエーションモデル"""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

class Valuation(Base):
    __tablename__ = "valuations"
    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_valuation_company_date"),
        Index("ix_valuation_company_date", "company_id", "date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    date: Mapped[date] = mapped_column(Date)
    stock_price: Mapped[float | None] = mapped_column(default=None)
    market_cap: Mapped[float | None] = mapped_column(default=None)
    per: Mapped[float | None] = mapped_column(default=None)
    pbr: Mapped[float | None] = mapped_column(default=None)
    ev_ebitda: Mapped[float | None] = mapped_column(default=None)
    psr: Mapped[float | None] = mapped_column(default=None)
    fcf_yield: Mapped[float | None] = mapped_column(default=None)
    last_updated: Mapped[datetime] = mapped_column(server_default=func.now())
    company = relationship("Company", back_populates="valuations")
