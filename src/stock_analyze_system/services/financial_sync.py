"""財務データ同期サービス（SEC/EDINET → DB）"""
from __future__ import annotations

import logging
from tempfile import TemporaryDirectory
from datetime import date as date_type
from datetime import timedelta
from typing import Any

from stock_analyze_system.ingestion.edinet_xbrl_parser import EdinetXbrlParser
from stock_analyze_system.ingestion.xbrl import SecXbrlParser
from stock_analyze_system.models.enums import AccountingStandard, PeriodType
from stock_analyze_system.models.financial_data import FINANCIAL_NATURAL_KEY
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.shared.financial import derive_fcf

logger = logging.getLogger(__name__)

_EDINET_STD_MAP: dict[str, str] = {
    "jp_gaap": AccountingStandard.JP_GAAP,
    "ifrs": AccountingStandard.IFRS,
    "us_gaap": AccountingStandard.US_GAAP,
}



class FinancialSyncService:
    """SEC/EDINET からの財務データ取得・永続化オーケストレーション"""

    def __init__(
        self,
        financial_repo: FinancialRepository,
        sec_client: Any,
        edinet_client: Any,
        yahoo_client: Any,
        fmp_client: Any,
    ):
        self._repo = financial_repo
        self._sec = sec_client
        self._edinet = edinet_client
        self._yahoo = yahoo_client
        self._fmp = fmp_client

    async def update_from_sec(
        self,
        company_id: str,
        cik: str,
        acct_std: str,
        period_types: tuple[str, ...] = (PeriodType.ANNUAL,),
    ) -> int:
        """SEC EDGAR から財務データを取得・upsert。戻り値はレコード数。"""
        try:
            facts = await self._sec.get_company_facts(cik)
        except (ValueError, OSError, KeyError):
            logger.exception("SEC EDGAR fetch failed for %s", company_id)
            return 0

        total_count = 0
        for period_type in period_types:
            count = await self._parse_and_upsert_sec(
                company_id, facts, acct_std, period_type,
            )
            total_count += count

        logger.info(
            "Financial update for %s: %d records from SEC EDGAR",
            company_id, total_count,
        )
        return total_count

    async def _parse_and_upsert_sec(
        self, company_id: str, facts: dict,
        acct_std: str, period_type: str,
    ) -> int:
        """SEC facts を parse して DB に upsert。戻り値は upsert レコード数。"""
        parser = SecXbrlParser()
        try:
            records = parser.parse_company_facts(facts, period_type=period_type)
        except (ValueError, KeyError):
            logger.warning(
                "SEC EDGAR parse failed for %s period_type=%s",
                company_id, period_type,
            )
            return 0

        count = 0
        for record in records:
            currency = record.pop("currency", "USD")
            derive_fcf(record)
            data = {
                "accounting_standard": acct_std,
                "currency": currency,
                "period_type": period_type,
                "fiscal_year_end": date_type.fromisoformat(record["fiscal_year_end"]),
                **{k: v for k, v in record.items() if k != "fiscal_year_end"},
            }
            await self._upsert_financial(company_id, data)
            count += 1
        return count

    async def update_from_edinet(
        self, company_id: str, edinet_code: str,
    ) -> int:
        """EDINET から財務データを取得・upsert。戻り値はレコード数。"""
        try:
            today = date_type.today()
            docs = await self._edinet.search_company_filings(
                edinet_code,
                (today - timedelta(days=365 * 2)).isoformat(),
                today.isoformat(),
            )
        except (ValueError, OSError, KeyError):
            logger.exception("EDINET search failed for %s", company_id)
            return 0

        if not docs:
            return 0

        total = 0
        for doc in docs:
            count = await self._parse_and_upsert_edinet(company_id, doc)
            total += count

        logger.info(
            "Financial update for %s: %d records from EDINET",
            company_id, total,
        )
        return total

    async def _parse_and_upsert_edinet(
        self, company_id: str, doc: dict,
    ) -> int:
        """EDINET ドキュメントを parse して upsert。戻り値はレコード数。"""
        doc_id = doc.get("docID")
        if not doc_id:
            return 0
        try:
            with TemporaryDirectory(prefix="edinet-xbrl-") as tmpdir:
                xbrl_dir = await self._edinet.download_xbrl_zip(doc_id, tmpdir)
                parser = EdinetXbrlParser()
                std = parser.detect_accounting_standard(xbrl_dir)
                result = parser.parse_xbrl_directory(xbrl_dir, std)
                if not result:
                    return 0

                data = {
                    "accounting_standard": _EDINET_STD_MAP.get(std, std.upper().replace("_", "-")),
                    "currency": "JPY",
                    "period_type": PeriodType.ANNUAL,
                    **result,
                }
                await self._upsert_financial(company_id, data)
                return 1
        except (ValueError, OSError, KeyError):
            logger.exception("EDINET parse failed for doc %s", doc_id)
            return 0

    _UPSERT_FILTER_KEYS = FINANCIAL_NATURAL_KEY

    async def _upsert_financial(self, company_id: str, data: dict) -> None:
        """財務データを共通フィルターキーで upsert する"""
        filters = {"company_id": company_id}
        for k in self._UPSERT_FILTER_KEYS:
            if k in data:
                filters[k] = data[k]
        remainder = {k: v for k, v in data.items() if k not in self._UPSERT_FILTER_KEYS}
        await self._repo.upsert(filters, remainder)
