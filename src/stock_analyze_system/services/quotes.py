"""Quote refresh orchestration service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.quote_price import QuotePrice
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.services.google_sheets_quotes import (
    GoogleSheetsQuoteClient,
    QuoteRequest,
    QuoteResult,
)
from stock_analyze_system.services.quote_symbols import build_google_finance_symbol


@dataclass(frozen=True)
class QuoteRefreshResult:
    requested: int
    submitted: int
    succeeded: int
    failed: int
    skipped: int
    statuses: dict[str, int]


class QuoteService:
    def __init__(
        self,
        company_repo: CompanyRepository,
        quote_repo: QuotePriceRepository,
        google_sheets_client: GoogleSheetsQuoteClient | None = None,
    ):
        self._company_repo = company_repo
        self._quote_repo = quote_repo
        self._google = google_sheets_client

    async def get_latest_price(
        self,
        company_id: str,
        provider: str = "google_sheets",
    ) -> QuotePrice | None:
        return await self._quote_repo.get_latest(company_id, provider=provider)

    async def status_counts(self, provider: str = "google_sheets") -> dict[str, int]:
        return await self._quote_repo.count_by_status(provider=provider)

    async def get_latest_many(
        self,
        company_ids: list[str],
        provider: str = "google_sheets",
    ) -> dict[str, QuotePrice]:
        return await self._quote_repo.get_latest_many(company_ids, provider=provider)

    async def list_recent(
        self,
        limit: int = 5,
        provider: str = "google_sheets",
    ) -> list[QuotePrice]:
        return await self._quote_repo.list_recent(limit=limit, provider=provider)

    async def latest_fetched_at(
        self,
        provider: str = "google_sheets",
    ) -> datetime | None:
        return await self._quote_repo.latest_fetched_at(provider=provider)

    async def refresh_google_sheets_quotes(
        self,
        company_ids: list[str] | None = None,
        market_prefix: str | None = "US_",
        limit: int | None = None,
    ) -> QuoteRefreshResult:
        companies, missing_count = await self._select_companies(
            company_ids,
            market_prefix,
            limit,
        )
        requests: list[QuoteRequest] = []
        unsupported_companies: list[Company] = []
        statuses: dict[str, int] = {}
        if missing_count:
            statuses["missing_company"] = missing_count

        for company in companies:
            symbol = build_google_finance_symbol(company.market, company.ticker)
            if symbol is None:
                unsupported_companies.append(company)
                continue
            requests.append(QuoteRequest(company_id=company.id, provider_symbol=symbol))

        if requests:
            if self._google is None:
                raise ValueError("Google Sheets quote client is not configured")
            results = await self._google.refresh_quotes(requests)
            for result in results:
                await self._persist_result(result)
                statuses[result.status] = statuses.get(result.status, 0) + 1

        for company in unsupported_companies:
            await self._persist_unsupported_symbol(company)
            statuses["unsupported_symbol"] = statuses.get("unsupported_symbol", 0) + 1

        await self._quote_repo._session.commit()
        requested = len(companies) + missing_count
        succeeded = statuses.get("ok", 0)
        failed = requested - succeeded
        return QuoteRefreshResult(
            requested=requested,
            submitted=len(requests),
            succeeded=succeeded,
            failed=failed,
            skipped=len(unsupported_companies) + missing_count,
            statuses=dict(sorted(statuses.items())),
        )

    async def _select_companies(
        self,
        company_ids: list[str] | None,
        market_prefix: str | None,
        limit: int | None,
    ) -> tuple[list[Company], int]:
        if company_ids is not None:
            if not company_ids:
                return [], 0
            existing = await self._company_repo.find_existing_ids(company_ids)
            companies = []
            missing_count = 0
            for company_id in company_ids:
                if company_id in existing:
                    company = await self._company_repo.get_by_id(company_id)
                    if company is not None:
                        companies.append(company)
                else:
                    missing_count += 1
            companies = companies[:limit] if limit is not None else companies
            return companies, missing_count

        companies = await self._company_repo.list_all()
        if market_prefix:
            companies = [c for c in companies if c.id.startswith(market_prefix)]
        companies = sorted(companies, key=lambda c: c.id)
        companies = companies[:limit] if limit is not None else companies
        return companies, 0

    async def _persist_unsupported_symbol(self, company: Company) -> None:
        await self._quote_repo.upsert_latest(
            {
                "company_id": company.id,
                "provider": "google_sheets",
                "provider_symbol": None,
                "price": None,
                "currency": None,
                "data_delay_minutes": None,
                "as_of": None,
                "status": "unsupported_symbol",
                "error_message": (
                    f"unsupported exchange/ticker: {company.market}/{company.ticker}"
                ),
                "raw_value": None,
                "fetched_at": datetime.now(timezone.utc),
            }
        )

    async def _persist_result(self, result: QuoteResult) -> None:
        await self._quote_repo.upsert_latest(
            {
                "company_id": result.company_id,
                "provider": "google_sheets",
                "provider_symbol": result.provider_symbol,
                "price": result.price,
                "currency": result.currency,
                "data_delay_minutes": result.data_delay_minutes,
                "as_of": result.fetched_at,
                "fetched_at": result.fetched_at,
                "status": result.status,
                "error_message": result.error_message,
                "raw_value": result.raw_value,
            }
        )
