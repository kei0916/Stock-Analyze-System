"""Screening cache metrics computation from SEC financials + cached quotes."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.repositories.quote_price import QuotePriceRepository
from stock_analyze_system.repositories.screening import ScreeningRepository

logger = logging.getLogger(__name__)


@dataclass
class RefreshMetricsResult:
    eligible: int
    processed: int
    succeeded: int
    skipped_no_financials: int
    skipped_no_quote: int
    failed: int


class ScreeningMetricsService:
    """Compute screening_cache rows from financial_data + quote_prices."""

    def __init__(
        self,
        company_repo: CompanyRepository,
        financial_repo: FinancialRepository,
        quote_repo: QuotePriceRepository,
        screening_repo: ScreeningRepository,
        universe_refresher: Callable[[], Awaitable[object]] | None = None,
    ):
        self._company_repo = company_repo
        self._financial_repo = financial_repo
        self._quote_repo = quote_repo
        self._screening_repo = screening_repo
        self._universe_refresher = universe_refresher

    async def refresh_from_sec_google(
        self,
        limit: int | None = None,
        *,
        refresh_universe: bool = True,
    ) -> RefreshMetricsResult:
        """Refresh screening_cache using latest SEC financials and Google Sheets quotes."""
        if refresh_universe and self._universe_refresher is not None:
            await self._universe_refresher()

        companies = await self._company_repo.list_all()
        companies = [c for c in companies if c.id.startswith("US_")]
        if limit is not None:
            companies = companies[:limit]

        eligible = len(companies)
        succeeded = skipped_no_financials = skipped_no_quote = failed = 0

        company_ids = [c.id for c in companies]
        quotes = await self._quote_repo.get_latest_many(
            company_ids, provider="google_sheets",
        )

        for company in companies:
            fin = await self._financial_repo.get_latest(company.id, "annual")
            if fin is None:
                fin = await self._financial_repo.get_latest(company.id, "quarterly")
            if fin is None:
                skipped_no_financials += 1
                continue

            quote = quotes.get(company.id)
            if quote is None or quote.status != "ok" or quote.price is None:
                skipped_no_quote += 1
                continue

            try:
                payload = self._compute_metrics(company, fin, quote)
                await self._screening_repo.upsert_cache(company.id, payload)
                await self._screening_repo._session.commit()
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                await self._screening_repo._session.rollback()
                logger.warning(
                    "screening metrics upsert failed for %s: %s",
                    company.id, exc, exc_info=exc,
                )
                failed += 1

        return RefreshMetricsResult(
            eligible=eligible,
            processed=eligible,
            succeeded=succeeded,
            skipped_no_financials=skipped_no_financials,
            skipped_no_quote=skipped_no_quote,
            failed=failed,
        )

    @staticmethod
    def _compute_metrics(company, fin, quote) -> dict:
        price = quote.price
        shares = fin.shares_outstanding
        revenue = fin.revenue
        equity = fin.equity
        total_debt = fin.total_debt
        cash = fin.cash
        ebitda = fin.ebitda
        eps = fin.eps
        net_income = fin.net_income
        operating_income = fin.operating_income
        fcf = fin.fcf
        dps = fin.dps

        market_cap = price * shares if price is not None and shares else None
        trailing_per = price / eps if price is not None and eps else None
        book_value_per_share = equity / shares if equity is not None and shares else None
        pbr = price / book_value_per_share if price is not None and book_value_per_share else None
        psr = price / (revenue / shares) if price is not None and revenue and shares else None
        ev = (market_cap + total_debt - cash) if market_cap is not None and total_debt is not None and cash is not None else None
        ev_ebitda = ev / ebitda if ev is not None and ebitda else None
        de_ratio = total_debt / equity if total_debt is not None and equity else None
        roe = net_income / equity if net_income is not None and equity else None
        operating_margin = operating_income / revenue if operating_income is not None and revenue else None
        net_margin = net_income / revenue if net_income is not None and revenue else None
        fcf_yield = fcf / market_cap if fcf is not None and market_cap else None
        dividend_yield = dps / price if dps is not None and price else None

        return {
            "stock_price": price,
            "market_cap": market_cap,
            "trailing_per": trailing_per,
            "eps": eps,
            "pbr": pbr,
            "psr": psr,
            "ev_ebitda": ev_ebitda,
            "de_ratio": de_ratio,
            "roe": roe,
            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "fcf_yield": fcf_yield,
            "dividend_yield": dividend_yield,
            "sector": company.sector,
        }
