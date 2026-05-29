"""CLIサービスコンテナ: DI組み立て"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.config import AppConfig

if TYPE_CHECKING:
    from stock_analyze_system.services.company import CompanyService
    from stock_analyze_system.services.financial import FinancialService
    from stock_analyze_system.services.valuation import ValuationService
    from stock_analyze_system.services.filing import FilingService
    from stock_analyze_system.services.watchlist import WatchlistService
    from stock_analyze_system.services.analysis import AnalysisService
    from stock_analyze_system.services.analysis_target import AnalysisTargetService
    from stock_analyze_system.services.job import JobService
    from stock_analyze_system.services.financial_sync import FinancialSyncService
    from stock_analyze_system.services.filing_sync import FilingSyncService
    from stock_analyze_system.services.filing_content import FilingContentService
    from stock_analyze_system.services.rag_service import RagService
    from stock_analyze_system.services.screening import ScreeningService
    from stock_analyze_system.services.screening_metrics import ScreeningMetricsService
    from stock_analyze_system.services.screening_universe import ScreeningUniverseService
    from stock_analyze_system.services.quotes import QuoteService
    from stock_analyze_system.shared.clients import ClientBundle


@dataclass
class ServiceContainer:
    company_service: CompanyService
    financial_service: FinancialService
    valuation_service: ValuationService
    filing_service: FilingService
    watchlist_service: WatchlistService
    target_service: AnalysisTargetService
    job_service: JobService
    financial_sync: FinancialSyncService
    filing_sync: FilingSyncService
    filing_content_service: FilingContentService
    screening_universe_service: ScreeningUniverseService | None = None
    screening_service: ScreeningService | None = None
    screening_metrics_service: ScreeningMetricsService | None = None
    quote_service: QuoteService | None = None
    rag_service: RagService | None = None
    analysis_service: AnalysisService | None = None
    session: AsyncSession | None = None


async def setup_services(
    session: AsyncSession,
    config: AppConfig,
    *,
    clients: "ClientBundle | None" = None,
) -> ServiceContainer:
    from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
    from stock_analyze_system.ingestion.edinet import EdinetClient
    from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
    from stock_analyze_system.ingestion.fmp import FmpClient
    from stock_analyze_system.repositories.company import CompanyRepository
    from stock_analyze_system.repositories.financial import FinancialRepository
    from stock_analyze_system.repositories.valuation import ValuationRepository
    from stock_analyze_system.repositories.filing import FilingRepository
    from stock_analyze_system.repositories.watchlist import WatchlistRepository
    from stock_analyze_system.repositories.target import TargetRepository
    from stock_analyze_system.repositories.analysis import AnalysisRepository
    from stock_analyze_system.repositories.quote_price import QuotePriceRepository
    from stock_analyze_system.services.analysis import AnalysisService
    from stock_analyze_system.services.company import CompanyService
    from stock_analyze_system.services.financial import FinancialService
    from stock_analyze_system.services.valuation import ValuationService
    from stock_analyze_system.services.filing import FilingService
    from stock_analyze_system.services.filing_content import FilingContentService
    from stock_analyze_system.services.watchlist import WatchlistService
    from stock_analyze_system.services.analysis_target import AnalysisTargetService
    from stock_analyze_system.services.financial_sync import FinancialSyncService
    from stock_analyze_system.services.filing_sync import FilingSyncService
    from stock_analyze_system.services.google_sheets_quotes import GoogleSheetsQuoteClient
    from stock_analyze_system.services.job import JobService
    from stock_analyze_system.services.quotes import QuoteService

    if clients is None:
        sec_client = SecEdgarClient(
            email=config.sec_edgar.email,
            rate=config.sec_edgar.rate_limit_rps,
        )
        edinet_client = EdinetClient(api_key=config.edinet.api_key, base_url=config.edinet.base_url)
        yahoo_client = YahooFinanceClient(rate=config.yahoo_finance.rate_limit_rps)
        fmp_client = FmpClient(api_key=config.fmp.api_key, base_url=config.fmp.base_url)
        llm_client_pre = None
        pdf_converter_pre = None
    else:
        sec_client = clients.sec
        edinet_client = clients.edinet
        yahoo_client = clients.yahoo
        fmp_client = clients.fmp
        llm_client_pre = clients.llm
        pdf_converter_pre = clients.pdf_converter

    company_repo = CompanyRepository(session)
    financial_repo = FinancialRepository(session)
    valuation_repo = ValuationRepository(session)
    filing_repo = FilingRepository(session)
    watchlist_repo = WatchlistRepository(session)
    target_repo = TargetRepository(session)
    quote_repo = QuotePriceRepository(session)
    analysis_repo = AnalysisRepository(session)

    company_svc = CompanyService(company_repo)
    financial_svc = FinancialService(financial_repo)
    valuation_svc = ValuationService(valuation_repo)
    filing_svc = FilingService(filing_repo)
    watchlist_svc = WatchlistService(watchlist_repo)
    target_svc = AnalysisTargetService(target_repo)
    google_quote_client = (
        GoogleSheetsQuoteClient.from_config(config.google_sheets)
        if config.google_sheets.enabled
        else None
    )
    quote_svc = QuoteService(
        company_repo=company_repo,
        quote_repo=quote_repo,
        google_sheets_client=google_quote_client,
    )
    analysis_svc = AnalysisService(analysis_repo)

    financial_sync = FinancialSyncService(
        financial_repo, sec_client, edinet_client, yahoo_client, fmp_client,
    )
    filing_sync = FilingSyncService(filing_repo, sec_client, edinet_client)
    filing_content_service = FilingContentService(
        filing_repo=filing_repo,
        sec_client=sec_client,
        edinet_client=edinet_client,
        config=config.filings,
    )
    job_svc = JobService(
        company_svc, financial_sync, filing_sync, valuation_svc,
        financial_svc, yahoo_client, fmp_client,
        target_svc=target_svc,
        quote_service=quote_svc,
    )

    # RAG services (ADR-004 amendment §B: RagService は常に構築する。
    # PageIndexService だけが config.pageindex.enabled 条件下。)
    from stock_analyze_system.repositories.rag_qa_history import RagQaHistoryRepository
    from stock_analyze_system.services.filing_section_extractor import (
        FilingSectionExtractor,
    )
    from stock_analyze_system.services.llm_client import LlmClient
    from stock_analyze_system.services.rag_service import RagService

    qa_history_repo = RagQaHistoryRepository(session)
    llm_client = llm_client_pre or LlmClient(config.llm)

    pageindex_service = None
    if config.pageindex.enabled:
        from stock_analyze_system.repositories.document_index import DocumentIndexRepository
        from stock_analyze_system.services.pdf_converter import PdfConverter
        from stock_analyze_system.services.pageindex import PageIndexService

        doc_index_repo = DocumentIndexRepository(session)
        pdf_converter = pdf_converter_pre or PdfConverter()
        pageindex_service = PageIndexService(
            doc_index_repo=doc_index_repo,
            pdf_converter=pdf_converter,
            llm_client=llm_client,
            config=config.pageindex,
        )

    rag_service = RagService(
        pageindex_service=pageindex_service,
        analysis_repo=analysis_repo,
        llm_client=llm_client,
        qa_history_repo=qa_history_repo,
        filing_content_service=filing_content_service,
        section_extractor=FilingSectionExtractor(),
    )

    from stock_analyze_system.repositories.screening import ScreeningRepository
    from stock_analyze_system.services.screening import ScreeningService
    from stock_analyze_system.services.screening_universe import ScreeningUniverseService

    screening_repo = ScreeningRepository(session)
    screening_universe_svc = ScreeningUniverseService(
        screening_repo=screening_repo,
        company_repo=company_repo,
        sec_client=sec_client,
        yahoo_client=yahoo_client,
    )
    screening_svc = ScreeningService(
        screening_repo=screening_repo,
        company_repo=company_repo,
        target_service=target_svc,
    )

    from stock_analyze_system.services.screening_metrics import ScreeningMetricsService

    screening_metrics_svc = ScreeningMetricsService(
        company_repo=company_repo,
        financial_repo=financial_repo,
        quote_repo=quote_repo,
        screening_repo=screening_repo,
        universe_refresher=screening_universe_svc.refresh_universe,
    )

    return ServiceContainer(
        company_service=company_svc,
        financial_service=financial_svc,
        valuation_service=valuation_svc,
        filing_service=filing_svc,
        watchlist_service=watchlist_svc,
        target_service=target_svc,
        job_service=job_svc,
        financial_sync=financial_sync,
        filing_sync=filing_sync,
        filing_content_service=filing_content_service,
        screening_universe_service=screening_universe_svc,
        screening_service=screening_svc,
        screening_metrics_service=screening_metrics_svc,
        quote_service=quote_svc,
        rag_service=rag_service,
        analysis_service=analysis_svc,
        session=session,
    )
