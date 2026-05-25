"""企業マスタモデル"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    ticker: Mapped[str | None] = mapped_column(String(10), index=True)
    security_code: Mapped[str | None] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_ja: Mapped[str | None] = mapped_column(String(200))
    market: Mapped[str] = mapped_column(String(20))
    sector: Mapped[str | None] = mapped_column(String(100))
    accounting_standard: Mapped[str] = mapped_column(String(10))
    cik: Mapped[str | None] = mapped_column(String(20))
    edinet_code: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    financial_data = relationship("FinancialData", back_populates="company")
    valuations = relationship("Valuation", back_populates="company")
    filings = relationship("Filing", back_populates="company")
    analyses = relationship("CompanyAnalysis", back_populates="company")
