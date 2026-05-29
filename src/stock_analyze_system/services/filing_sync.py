"""ファイリング同期サービス（SEC/EDINET → DB）"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from datetime import date as date_type
from datetime import timedelta
from typing import Any

from stock_analyze_system.models.enums import FilingSource, FilingType, PeriodType
from stock_analyze_system.repositories.filing import FilingRepository

logger = logging.getLogger(__name__)

_SEC_ANNUAL_FORMS = frozenset({
    FilingType.TEN_K,
    FilingType.TWENTY_F,
    "40-F",
})


@dataclass(frozen=True)
class FilingSourceAdapter:
    """ソース別の差分を _sync に渡す adapter。"""

    source: FilingSource
    fetch: Callable[[str], Awaitable[list[dict]]]
    key_field: str
    find_existing: Callable[[str, list[str]], Awaitable[set[str]]]
    map_record: Callable[[dict], dict]


def _map_sec_record(raw: dict) -> dict:
    """SEC filing エントリを Filing row dict に変換する。"""
    form = raw["form"]
    report_date = raw.get("reportDate", "")
    filed_date = raw.get("filingDate", "")
    period_type = (
        PeriodType.ANNUAL
        if form in _SEC_ANNUAL_FORMS
        else PeriodType.QUARTERLY
    )
    fiscal_year = int(report_date[:4]) if report_date else int(filed_date[:4])
    row = {
        "source": "SEC",
        "filing_type": form,
        "period_type": period_type,
        "fiscal_year": fiscal_year,
        "accession_no": raw["accessionNumber"],
    }
    if report_date:
        row["period_end"] = date_type.fromisoformat(report_date)
    if filed_date:
        row["filed_at"] = date_type.fromisoformat(filed_date)
    return row


def _map_edinet_record(raw: dict) -> dict:
    """EDINET document エントリを Filing row dict に変換する。"""
    today = date_type.today()
    fiscal_year_str = raw.get("periodEnd", "")[:4]
    fiscal_year = int(fiscal_year_str) if fiscal_year_str.isdigit() else today.year
    doc_type = raw.get("docTypeCode", "")
    period_type = (
        PeriodType.ANNUAL if doc_type in ("120", "130") else PeriodType.QUARTERLY
    )
    filing_type = (
        "annual_report" if period_type == PeriodType.ANNUAL else "quarterly_report"
    )
    return {
        "source": "EDINET",
        "filing_type": filing_type,
        "period_type": period_type,
        "fiscal_year": fiscal_year,
        "doc_id": raw["docID"],
    }


class FilingSyncService:
    """SEC/EDINET からのファイリング取得・登録オーケストレーション"""

    def __init__(
        self,
        filing_repo: FilingRepository,
        sec_client: Any,
        edinet_client: Any,
    ):
        self._repo = filing_repo
        self._sec = sec_client
        self._edinet = edinet_client

    async def _sync(
        self,
        adapter: FilingSourceAdapter,
        company_id: str,
        external_id: str,
    ) -> int:
        """ソース横断の共通 sync パイプライン。"""
        try:
            raw = await adapter.fetch(external_id)
        except (ValueError, OSError, KeyError) as exc:
            logger.warning(
                "filing fetch failed: source=%s company=%s id=%s err=%s",
                adapter.source,
                company_id,
                external_id,
                exc,
            )
            return 0

        if not raw:
            return 0

        keys = [entry[adapter.key_field] for entry in raw if entry.get(adapter.key_field)]
        existing = await adapter.find_existing(company_id, keys)

        new_rows: list[dict] = []
        for entry in raw:
            key_value = entry.get(adapter.key_field)
            if not key_value or key_value in existing:
                continue
            new_rows.append(adapter.map_record(entry))

        if not new_rows:
            return 0

        count = await self._repo.bulk_upsert(
            company_id,
            new_rows,
            source=adapter.source,
        )
        logger.info(
            "Filing update for %s (%s): %d new filings",
            company_id,
            adapter.source,
            count,
        )
        return count

    async def update_from_sec(
        self, company_id: str, cik: str,
    ) -> int:
        """SEC EDGAR からファイリングを取得・登録。戻り値は新規登録数。"""
        adapter = FilingSourceAdapter(
            source=FilingSource.SEC,
            fetch=lambda cik_: self._sec.list_filings(cik_, max_years=2),
            key_field="accessionNumber",
            find_existing=self._repo.find_existing_accessions,
            map_record=_map_sec_record,
        )
        return await self._sync(adapter, company_id, cik)

    async def list_daily_sec_filings(
        self,
        filing_date: date_type,
        form_types: list[str] | None = None,
    ) -> list[dict]:
        """List SEC filings for one SEC filingDate via the SEC client."""
        return await self._sec.list_daily_filings(
            filing_date,
            form_types=form_types,
        )

    async def list_sec_company_universe(self) -> list[dict]:
        """List SEC company ticker universe entries."""
        return await self._sec.list_universe()

    async def find_sec_company_by_ticker(self, ticker: str) -> dict | None:
        """Find one SEC company universe entry by ticker."""
        query = ticker.upper().strip()
        for entry in await self.list_sec_company_universe():
            if (entry.get("ticker") or "").upper().strip() == query:
                return entry
        return None

    async def find_sec_company_by_cik(self, cik: str) -> dict | None:
        """Find one SEC company universe entry by CIK."""
        try:
            query = str(int(cik)).zfill(10)
        except ValueError:
            return None
        for entry in await self.list_sec_company_universe():
            if entry.get("cik") == query:
                return entry
        return None

    async def update_from_sec_records(
        self,
        company_id: str,
        records: list[dict],
    ) -> int:
        """Register already-fetched SEC filing records for a company."""
        async def _fetch_prefetched(_: str) -> list[dict]:
            return records

        adapter = FilingSourceAdapter(
            source=FilingSource.SEC,
            fetch=_fetch_prefetched,
            key_field="accessionNumber",
            find_existing=self._repo.find_existing_accessions,
            map_record=_map_sec_record,
        )
        return await self._sync(adapter, company_id, company_id)

    async def update_from_edinet(
        self, company_id: str, edinet_code: str,
    ) -> int:
        """EDINET からファイリングを取得・登録。戻り値は登録数。"""
        today = date_type.today()
        start = (today - timedelta(days=365 * 2)).isoformat()
        end = today.isoformat()
        adapter = FilingSourceAdapter(
            source=FilingSource.EDINET,
            fetch=lambda code: self._edinet.search_company_filings(code, start, end),
            key_field="docID",
            find_existing=self._repo.find_existing_doc_ids,
            map_record=_map_edinet_record,
        )
        return await self._sync(adapter, company_id, edinet_code)
