"""競合グループモデル"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stock_analyze_system.models.base import Base

class CompetitorGroup(Base):
    __tablename__ = "competitor_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    accounting_standard: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    members = relationship("CompetitorGroupMember", back_populates="group", cascade="all, delete-orphan")

class CompetitorGroupMember(Base):
    __tablename__ = "competitor_group_members"
    __table_args__ = (UniqueConstraint("group_id", "company_id", name="uq_group_company"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("competitor_groups.id"))
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    group = relationship("CompetitorGroup", back_populates="members")
    company = relationship("Company")
