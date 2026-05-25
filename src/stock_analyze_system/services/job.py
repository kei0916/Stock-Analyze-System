"""バッチオーケストレーションサービス"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import httpx

from stock_analyze_system.exceptions import ApiConnectionError
from stock_analyze_system.models.enums import PeriodType
from stock_analyze_system.services.valuation import compute_valuation_from_financials

if TYPE_CHECKING:
    from stock_analyze_system.services.analysis_target import AnalysisTargetService
    from stock_analyze_system.ingestion.fmp import FmpClient
    from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
    from stock_analyze_system.services.company import CompanyService
    from stock_analyze_system.services.financial import FinancialService
    from stock_analyze_system.services.financial_sync import FinancialSyncService
    from stock_analyze_system.services.filing_sync import FilingSyncService
    from stock_analyze_system.services.quotes import QuoteService
    from stock_analyze_system.services.valuation import ValuationService

logger = logging.getLogger(__name__)

_SEC_FILING_TZ = ZoneInfo("America/New_York")
_US_DAILY_FILING_FORMS = ["10-K", "10-Q", "20-F", "40-F", "8-K", "6-K"]
_US_FINANCIAL_TRIGGER_FORMS = frozenset({"10-K", "10-Q", "20-F", "40-F"})
_DAILY_UPDATE_EXCEPTIONS = (
    ValueError,
    TypeError,
    AttributeError,
    OSError,
    ApiConnectionError,
    httpx.HTTPError,
)
_QUOTE_PROVIDERS = frozenset({"yahoo", "google_sheets"})


@dataclass
class SyncResult:
    """単一企業の同期結果"""
    company_id: str
    financials_count: int = 0
    filings_count: int = 0
    valuations_count: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_reasons: list[str] = field(default_factory=list)


@dataclass
class DailyUpdateResult:
    """日次更新サイクルの結果"""
    market: str
    total_companies: int = 0
    results: list[SyncResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


def _default_sec_filing_date() -> date_type:
    """Return today's date in SEC filing-date timezone."""
    return datetime.now(_SEC_FILING_TZ).date()


def _normalize_cik(cik: str | None) -> str | None:
    """Normalize a company/feed CIK to 10 digits."""
    if not cik:
        return None
    try:
        return str(int(cik)).zfill(10)
    except ValueError:
        return None


def _validate_quote_provider(quote_provider: str) -> str:
    """Return a supported quote provider or raise a request-level error."""
    if quote_provider not in _QUOTE_PROVIDERS:
        allowed = ", ".join(sorted(_QUOTE_PROVIDERS))
        raise ValueError(
            f"Unsupported quote provider: {quote_provider}; "
            f"quote_provider must be one of: {allowed}"
        )
    return quote_provider


class JobService:
    """バッチ同期オーケストレーション"""

    def __init__(
        self,
        company_svc: CompanyService,
        financial_sync: FinancialSyncService,
        filing_sync: FilingSyncService,
        valuation_svc: ValuationService,
        financial_svc: FinancialService,
        yahoo_client: YahooFinanceClient,
        fmp_client: FmpClient,
        target_svc: AnalysisTargetService | None = None,
        quote_service: QuoteService | None = None,
    ):
        self._company_svc = company_svc
        self._financial_sync = financial_sync
        self._filing_sync = filing_sync
        self._valuation_svc = valuation_svc
        self._financial_svc = financial_svc
        self._yahoo = yahoo_client
        self._fmp = fmp_client
        self._target_svc = target_svc
        self._quote_service = quote_service

    async def _get_price_data_for_company(
        self,
        company,
        result: SyncResult,
        quote_provider: str,
    ) -> dict | None:
        """Fetch price data for valuation from the requested provider."""
        quote_provider = _validate_quote_provider(quote_provider)
        if quote_provider == "google_sheets":
            if self._quote_service is None:
                result.errors.append("quote_service unavailable")
                return None
            quote = await self._quote_service.get_latest_price(
                company.id,
                provider="google_sheets",
            )
            if quote is None or quote.status != "ok" or quote.price is None:
                result.skipped_reasons.append(
                    f"No usable quote for {company.id} from google_sheets"
                )
                return None
            return {
                "price": quote.price,
                "market_cap": None,
                "currency": quote.currency or "USD",
            }

        yf_ticker = self._company_svc.resolve_yf_ticker(company)
        if not yf_ticker:
            return None
        return await self._yahoo.get_stock_price(yf_ticker)

    async def _update_valuation_for_company(
        self,
        company,
        result: SyncResult,
        quote_provider: str = "yahoo",
    ) -> None:
        """Update valuation for a single company."""
        try:
            quote_provider = _validate_quote_provider(quote_provider)
        except ValueError as exc:
            result.errors.append(str(exc))
            return

        try:
            price_data = await self._get_price_data_for_company(
                company,
                result,
                quote_provider,
            )
            if not price_data:
                return
            currency = price_data.get("currency", "USD")
            stock_price = price_data.get("price")
            market_cap_val = price_data.get("market_cap")

            latest_fd = await self._financial_svc.get_latest(
                result.company_id,
                PeriodType.ANNUAL,
            )
            if latest_fd:
                val_data = compute_valuation_from_financials(
                    stock_price,
                    latest_fd,
                    currency,
                    date_type.today(),
                    market_cap=market_cap_val,
                )
            else:
                val_data = {
                    "currency": currency,
                    "date": date_type.today(),
                    "stock_price": stock_price,
                    "market_cap": market_cap_val,
                }
            val_data["last_updated"] = datetime.now()

            await self._valuation_svc.upsert_valuation(
                result.company_id,
                val_data,
            )
            result.valuations_count += 1
        except (ValueError, TypeError, AttributeError) as exc:
            result.errors.append(f"Valuation error: {exc}")
            logger.warning("Valuation failed for %s: %s", result.company_id, exc)

    async def update_valuation_for_company(
        self,
        company_id: str,
        quote_provider: str = "yahoo",
    ) -> SyncResult:
        """Update valuation for a single company ID."""
        result = SyncResult(company_id=company_id)
        try:
            company = await self._company_svc.get_company(company_id)
            if company is None:
                raise ValueError(f"Company '{company_id}' not found")
            await self._update_valuation_for_company(
                company,
                result,
                quote_provider=quote_provider,
            )
        except _DAILY_UPDATE_EXCEPTIONS as exc:
            logger.exception("Valuation update failed for %s", company_id)
            result.errors.append(str(exc))
        return result

    async def sync_company(self, company_id: str) -> SyncResult:
        """単一企業の全データを外部ソースから取り込み、DB に反映する。

        financial / filing / valuation の各カテゴリを並行ではなく順次処理する
        (LLM + SEC の同時実行でのデッドロックを回避するため)。

        Args:
            company_id: 対象企業 ID。

        Returns:
            各カテゴリの取り込み件数とエラー内訳を含む `SyncResult`。

        Raises:
            ValueError: `company_id` に該当する企業が存在しない場合。
        """
        company = await self._company_svc.get_company(company_id)
        if company is None:
            raise ValueError(f"Company '{company_id}' not found")

        result = SyncResult(company_id=company_id)

        # 1. Financial data
        cik = company.cik
        edinet_code = company.edinet_code
        acct_std = company.accounting_standard

        if cik:
            count = await self._financial_sync.update_from_sec(
                company_id, cik, acct_std,
                period_types=(PeriodType.ANNUAL, PeriodType.QUARTERLY),
            )
            result.financials_count = count
        elif (not self._company_svc.is_us_market(company_id)
              and edinet_code):
            count = await self._financial_sync.update_from_edinet(
                company_id, edinet_code,
            )
            result.financials_count = count

        # 2. Filing data
        if cik:
            result.filings_count = await self._filing_sync.update_from_sec(
                company_id, cik,
            )
        elif (not self._company_svc.is_us_market(company_id)
              and edinet_code):
            result.filings_count = await self._filing_sync.update_from_edinet(
                company_id, edinet_code,
            )

        # 3. Valuation from Yahoo Finance
        await self._update_valuation_for_company(company, result)

        return result

    async def _run_us_daily_filing_update(
        self,
        target_date: date_type,
    ) -> DailyUpdateResult:
        """Run US daily update from SEC filings for one filingDate."""
        result = DailyUpdateResult(market="us")
        companies = await self._company_svc.list_companies()
        companies = [c for c in companies if c.id.startswith("US_")]
        result.total_companies = len(companies)

        companies_by_cik: dict[str, list[object]] = defaultdict(list)
        for company in companies:
            normalized_cik = _normalize_cik(company.cik)
            if normalized_cik is not None:
                companies_by_cik[normalized_cik].append(company)

        try:
            daily_filings = await self._filing_sync.list_daily_sec_filings(
                target_date,
                form_types=_US_DAILY_FILING_FORMS,
            )
        except _DAILY_UPDATE_EXCEPTIONS as exc:
            logger.exception("SEC daily filing fetch failed for %s", target_date)
            sr = SyncResult(company_id="SEC_EDGAR")
            sr.errors.append(str(exc))
            result.results.append(sr)
            result.finished_at = datetime.now(timezone.utc)
            return result

        filings_by_company_id: dict[str, list[dict]] = defaultdict(list)
        company_by_id: dict[str, object] = {}
        unknown_cik_count = 0
        for filing in daily_filings:
            normalized_cik = _normalize_cik(filing.get("cik"))
            if normalized_cik is None or normalized_cik not in companies_by_cik:
                unknown_cik_count += 1
                continue
            for company in companies_by_cik[normalized_cik]:
                filings_by_company_id[company.id].append(filing)
                company_by_id[company.id] = company

        logger.info(
            "SEC daily filings target_date=%s feed_rows=%d matched_companies=%d unknown_ciks=%d",
            target_date,
            len(daily_filings),
            len(filings_by_company_id),
            unknown_cik_count,
        )

        for company_id in sorted(filings_by_company_id):
            company = company_by_id[company_id]
            filings = filings_by_company_id[company_id]
            sr = SyncResult(company_id=company_id)
            try:
                sr.filings_count = await self._filing_sync.update_from_sec_records(
                    company_id,
                    filings,
                )
            except _DAILY_UPDATE_EXCEPTIONS as exc:
                logger.exception("SEC daily filing registration failed for %s", company_id)
                sr.errors.append(f"Filing error: {exc}")

            if any(f.get("form") in _US_FINANCIAL_TRIGGER_FORMS for f in filings):
                try:
                    sr.financials_count = await self._financial_sync.update_from_sec(
                        company_id,
                        company.cik,
                        company.accounting_standard,
                        period_types=(PeriodType.ANNUAL, PeriodType.QUARTERLY),
                    )
                except _DAILY_UPDATE_EXCEPTIONS as exc:
                    logger.exception("SEC daily financial refresh failed for %s", company_id)
                    sr.errors.append(f"Financial error: {exc}")

            await self._update_valuation_for_company(company, sr)
            result.results.append(sr)

        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Daily SEC filing update complete: target_date=%s companies=%d",
            target_date,
            len(result.results),
        )
        return result

    async def run_target_valuation_update(
        self,
        market: str = "all",
        quote_provider: str = "yahoo",
    ) -> DailyUpdateResult:
        """Update valuations for analysis targets.

        Args:
            market: `"us"`, `"jp"`, or `"all"`. US/JP filter by company ID
                prefix so separate cron entries can run after each market close.

        Returns:
            Per-target valuation update results.
        """
        normalized_market = market.lower()
        if normalized_market not in {"all", "us", "jp"}:
            raise ValueError("market must be one of: all, us, jp")
        quote_provider = _validate_quote_provider(quote_provider)

        result = DailyUpdateResult(market=normalized_market)
        if self._target_svc is None:
            sr = SyncResult(company_id="ANALYSIS_TARGETS")
            sr.errors.append("target_service unavailable")
            result.results.append(sr)
            result.finished_at = datetime.now(timezone.utc)
            return result

        targets = await self._target_svc.list_targets()
        if normalized_market != "all":
            prefix = f"{normalized_market.upper()}_"
            targets = [t for t in targets if t.company_id.startswith(prefix)]
        result.total_companies = len(targets)

        for target in targets:
            company_id = target.company_id
            result.results.append(
                await self.update_valuation_for_company(
                    company_id,
                    quote_provider=quote_provider,
                ),
            )

        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Target valuation update complete: market=%s targets=%d",
            normalized_market,
            result.total_companies,
        )
        return result

    async def run_daily_update(
        self,
        market: str = "us",
        target_date: date_type | None = None,
    ) -> DailyUpdateResult:
        """Run the daily update workflow for one market.

        US updates are driven by SEC EDGAR daily filings for `target_date`.
        Matching companies register those filings, and only financial-reporting
        forms refresh SEC financial data. Non-US markets keep the existing
        per-company `sync_company` loop.

        Args:
            market: `"us"` または `"jp"`。デフォルトは `"us"`。
            target_date: SEC filing date for US daily updates. Defaults to
                today in the SEC filing-date timezone.

        Returns:
            各企業の `SyncResult` を束ねた `DailyUpdateResult`。
        """
        if market.lower() == "us":
            return await self._run_us_daily_filing_update(
                target_date or _default_sec_filing_date(),
            )

        result = DailyUpdateResult(market=market)

        market_prefix = market.upper()
        companies = await self._company_svc.list_companies()
        companies = [c for c in companies if c.id.startswith(f"{market_prefix}_")]
        result.total_companies = len(companies)

        for company in companies:
            try:
                sync_result = await self.sync_company(company.id)
                result.results.append(sync_result)
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                logger.exception("Sync failed for %s", company.id)
                sr = SyncResult(company_id=company.id)
                sr.errors.append(str(exc))
                result.results.append(sr)

        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Daily update complete for market=%s: %d companies",
            market, result.total_companies,
        )
        return result
