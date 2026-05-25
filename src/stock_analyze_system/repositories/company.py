"""企業リポジトリ"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Company ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Company)

    async def find_by_identifier(self, query: str) -> Company | None:
        """ticker / security_code / company_id いずれでも検索"""
        q = query.upper()
        stmt = select(Company).where(
            or_(
                Company.ticker == q,
                Company.security_code == q,
                Company.id == q,
                Company.id == f"US_{q}",
                Company.id == f"JP_{q}",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_cik(self, cik: str) -> Company | None:
        """CIKで企業を検索する。"""
        stmt = select(Company).where(Company.cik == cik)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, query: str, limit: int = 20) -> list[Company]:
        """名前/ticker/security_code/日本語名で部分一致検索"""
        pattern = f"%{query}%"
        stmt = (
            select(Company)
            .where(
                or_(
                    Company.name.ilike(pattern),
                    Company.ticker.ilike(pattern),
                    Company.security_code.ilike(pattern),
                    Company.name_ja.ilike(pattern),
                )
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_existing_ids(self, ids: list[str]) -> set[str]:
        """与えた id の中で companies に実在する id を set で返す.

        Used by ScreeningService.add_to_targets to count `skipped` ids that
        do not correspond to a real company.
        """
        if not ids:
            return set()
        stmt = select(Company.id).where(Company.id.in_(ids))
        result = await self._session.execute(stmt)
        return set(result.scalars().all())
