"""ファイリングサービス"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from stock_analyze_system.repositories.filing import FilingRepository

logger = logging.getLogger(__name__)


class FilingService:
    """ファイリングの登録・検索サービス"""

    def __init__(self, filing_repo: FilingRepository):
        self._repo = filing_repo

    async def upsert_filing(self, company_id: str, data: dict[str, Any]):
        """ファイリングを upsert。accession_no/doc_id で既存検索後、repo.upsert に委譲。"""
        accession_no = data.get("accession_no")
        doc_id = data.get("doc_id")

        if accession_no:
            filters = {"accession_no": accession_no}
        elif doc_id:
            filters = {"doc_id": doc_id}
        else:
            filters = {
                "company_id": company_id,
                "fiscal_year": data["fiscal_year"],
                "filing_type": data["filing_type"],
                "period_type": data["period_type"],
            }
            data = {k: v for k, v in data.items()
                    if k not in ("fiscal_year", "filing_type", "period_type")}

        return await self._repo.upsert(
            {**filters, "company_id": company_id},
            {k: v for k, v in data.items() if k not in filters},
        )

    async def get_latest_filing(self, company_id: str, filing_type: str):
        return await self._repo.get_latest_filing(company_id, filing_type)

    async def get_latest_any_type(self, company_id: str):
        return await self._repo.get_latest_any_type(company_id)

    async def get_filing_by_id(self, filing_id: int):
        return await self._repo.get_by_id(filing_id)

    async def list_by_types(
        self, company_id: str, filing_types: list[str],
        *, since_year: int | None = None,
    ):
        return await self._repo.list_by_types(
            company_id, filing_types, since_year=since_year,
        )

    async def get_latest_with_content(self, company_id: str):
        return await self._repo.get_latest_with_content(company_id)

    async def list_by_recency(self, company_id: str):
        return await self._repo.list_by_recency(company_id)

    async def get_latest_indexed(self, company_id: str):
        return await self._repo.get_latest_indexed(company_id)

    async def list_filings(self, company_id: str, limit: int | None = None):
        return await self._repo.list_filings(company_id, limit=limit)

    @staticmethod
    def get_storage_path(
        base_path: str, source: str, company_id: str,
        fiscal_year: int, period_type: str, filing_type: str, key: str,
    ) -> Path:
        """階層的ストレージパスを構築"""
        return (
            Path(base_path) / source / company_id
            / str(fiscal_year) / period_type / filing_type / key
        )

    @staticmethod
    def compute_content_hash(content: bytes) -> str:
        """SHA-256 ハッシュを計算"""
        return hashlib.sha256(content).hexdigest()
