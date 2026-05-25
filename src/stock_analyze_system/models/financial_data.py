"""財務データモデル"""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

FINANCIAL_NATURAL_KEY = ("period_type", "fiscal_year_end", "accounting_standard")
"""company_id を除いた財務データの自然キー（upsert filter 用）"""


class FinancialData(Base):
    __tablename__ = "financial_data"
    __table_args__ = (
        UniqueConstraint("company_id", "period_type", "fiscal_year_end", "accounting_standard", name="uq_financial_natural_key"),
        Index("ix_financial_company_date", "company_id", "fiscal_year_end"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    accounting_standard: Mapped[str] = mapped_column(String(10))
    currency: Mapped[str] = mapped_column(String(3))
    period_type: Mapped[str] = mapped_column(String(10))
    fiscal_year_end: Mapped[date] = mapped_column(Date)
    revenue: Mapped[float | None] = mapped_column(default=None)
    operating_income: Mapped[float | None] = mapped_column(default=None)
    net_income: Mapped[float | None] = mapped_column(default=None)
    total_assets: Mapped[float | None] = mapped_column(default=None)
    equity: Mapped[float | None] = mapped_column(default=None)
    current_assets: Mapped[float | None] = mapped_column(default=None)
    current_liabilities: Mapped[float | None] = mapped_column(default=None)
    total_debt: Mapped[float | None] = mapped_column(default=None)
    cash: Mapped[float | None] = mapped_column(default=None)
    inventory: Mapped[float | None] = mapped_column(default=None)
    cogs: Mapped[float | None] = mapped_column(default=None)
    operating_cf: Mapped[float | None] = mapped_column(default=None)
    capex: Mapped[float | None] = mapped_column(default=None)
    fcf: Mapped[float | None] = mapped_column(default=None)
    ebitda: Mapped[float | None] = mapped_column(default=None)
    eps: Mapped[float | None] = mapped_column(default=None)
    dps: Mapped[float | None] = mapped_column(default=None)
    tax_expense: Mapped[float | None] = mapped_column(default=None)
    income_before_tax: Mapped[float | None] = mapped_column(default=None)
    shares_outstanding: Mapped[float | None] = mapped_column(default=None)
    dividends_paid: Mapped[float | None] = mapped_column(default=None)
    share_repurchases: Mapped[float | None] = mapped_column(default=None)
    last_updated: Mapped[datetime] = mapped_column(server_default=func.now())
    company = relationship("Company", back_populates="financial_data")
