"""setup_services() が組み立てる ServiceContainer の契約を固定するテスト。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from stock_analyze_system.cli.container import ServiceContainer, setup_services
from tests.integration.conftest import build_test_config


@pytest.mark.characterization
class TestSetupServicesAssembly:
    async def test_returns_service_container_instance(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert isinstance(services, ServiceContainer)

    async def test_all_required_services_are_non_none(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.company_service is not None
        assert services.financial_service is not None
        assert services.valuation_service is not None
        assert services.filing_service is not None
        assert services.watchlist_service is not None
        assert services.target_service is not None
        assert services.job_service is not None
        assert services.financial_sync is not None
        assert services.filing_sync is not None
        assert services.filing_content_service is not None

    async def test_rag_service_constructed_when_pageindex_disabled(self, session):
        """ADR-004 amendment §B: pageindex.enabled=false でも RagService は
        常に構築される. 旧契約 (`rag_service is None`) は廃止."""
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.rag_service is not None
        assert type(services.rag_service).__name__ == "RagService"
        # PageIndex 経路だけが disabled になっている
        assert services.rag_service.pageindex_available is False

    async def test_rag_service_created_when_pageindex_enabled(self, session):
        config = build_test_config(pageindex_enabled=True)
        services = await setup_services(session, config)
        assert services.rag_service is not None
        assert type(services.rag_service).__name__ == "RagService"
        assert (
            services.rag_service._filing_content_service
            is services.filing_content_service
        )

    async def test_setup_services_passes_sec_rate_limit(self, session):
        config = build_test_config(pageindex_enabled=False)
        config.sec_edgar.email = "sec@example.com"
        config.sec_edgar.rate_limit_rps = 10

        with patch("stock_analyze_system.ingestion.sec_edgar.SecEdgarClient") as sec_cls:
            await setup_services(session, config)

        sec_cls.assert_called_once_with(email="sec@example.com", rate=10)

    async def test_service_class_names_match_expected(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert type(services.company_service).__name__ == "CompanyService"
        assert type(services.financial_service).__name__ == "FinancialService"
        assert type(services.valuation_service).__name__ == "ValuationService"
        assert type(services.filing_service).__name__ == "FilingService"
        assert type(services.watchlist_service).__name__ == "WatchlistService"
        assert type(services.target_service).__name__ == "AnalysisTargetService"
        assert type(services.job_service).__name__ == "JobService"
        assert type(services.financial_sync).__name__ == "FinancialSyncService"
        assert type(services.filing_sync).__name__ == "FilingSyncService"
        assert type(services.filing_content_service).__name__ == "FilingContentService"

    async def test_screening_services_wired(self, session):
        """Phase 5 (Task 9) 以降は screening_service / screening_universe_service
        が常に組み立てられる (pageindex 設定とは独立)"""
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.screening_service is not None
        assert type(services.screening_service).__name__ == "ScreeningService"
        assert services.screening_universe_service is not None
        assert (
            type(services.screening_universe_service).__name__
            == "ScreeningUniverseService"
        )

    async def test_quote_service_wired_when_google_sheets_disabled(self, session):
        config = build_test_config(pageindex_enabled=False)
        config.google_sheets.enabled = False

        services = await setup_services(session, config)

        assert services.quote_service is not None
        assert type(services.quote_service).__name__ == "QuoteService"
