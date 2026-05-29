"""スクリーニングキャッシュモデル"""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import BigInteger, Date, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

class ScreeningCache(Base):
    __tablename__ = "screening_cache"
    __table_args__ = (
        Index("ix_screening_cache_updated_at", "updated_at"),
        Index("ix_screening_cache_roe", "roe"),
    )
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    stock_price: Mapped[float | None] = mapped_column(default=None)
    market_cap: Mapped[float | None] = mapped_column(default=None)
    trailing_per: Mapped[float | None] = mapped_column(default=None)
    eps: Mapped[float | None] = mapped_column(default=None)
    forward_per: Mapped[float | None] = mapped_column(default=None)
    pbr: Mapped[float | None] = mapped_column(default=None)
    psr: Mapped[float | None] = mapped_column(default=None)
    ev_ebitda: Mapped[float | None] = mapped_column(default=None)
    dividend_yield: Mapped[float | None] = mapped_column(default=None)
    roe: Mapped[float | None] = mapped_column(default=None)
    operating_margin: Mapped[float | None] = mapped_column(default=None)
    net_margin: Mapped[float | None] = mapped_column(default=None)
    revenue_growth: Mapped[float | None] = mapped_column(default=None)
    earnings_growth: Mapped[float | None] = mapped_column(default=None)
    de_ratio: Mapped[float | None] = mapped_column(default=None)
    peg_ratio: Mapped[float | None] = mapped_column(default=None)
    fcf_yield: Mapped[float | None] = mapped_column(default=None)
    sector: Mapped[str | None] = mapped_column(String(100), default=None)
    industry: Mapped[str | None] = mapped_column(String(200), default=None)
    exchange: Mapped[str | None] = mapped_column(String(20), default=None)
    beta: Mapped[float | None] = mapped_column(default=None)
    volume: Mapped[int | None] = mapped_column(BigInteger, default=None)
    most_recent_quarter: Mapped[date | None] = mapped_column(Date, default=None)
    last_fiscal_year_end: Mapped[date | None] = mapped_column(Date, default=None)
    trailing_eps_date: Mapped[str | None] = mapped_column(String(30), default=None)
    company = relationship("Company")
