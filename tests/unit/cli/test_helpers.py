# tests/unit/cli/test_helpers.py
"""CLI helpers のテスト"""
import argparse
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli.container import ServiceContainer, setup_services
from stock_analyze_system.cli.helpers import (
    add_filing_type_argument,
    require_company,
    require_company_and_filing,
    require_latest_filing,
)
from stock_analyze_system.models.enums import FilingType


class TestRequireCompany:
    async def test_found(self):
        svc = AsyncMock()
        company = MagicMock()
        company.id = "US_AAPL"
        svc.get_company.return_value = company
        result = await require_company(svc, "US_AAPL")
        assert result.id == "US_AAPL"

    async def test_not_found_exits(self):
        svc = AsyncMock()
        svc.get_company.return_value = None
        with pytest.raises(SystemExit) as exc_info:
            await require_company(svc, "US_AAPL")
        assert exc_info.value.code == 1


class TestRequireLatestFiling:
    async def test_found(self):
        svc = AsyncMock()
        filing = MagicMock()
        filing.id = 1
        svc.get_latest_filing.return_value = filing
        result = await require_latest_filing(svc, "US_AAPL", "10-K")
        assert result.id == 1

    async def test_not_found_exits(self):
        svc = AsyncMock()
        svc.get_latest_filing.return_value = None
        with pytest.raises(SystemExit) as exc_info:
            await require_latest_filing(svc, "US_AAPL", "10-K")
        assert exc_info.value.code == 1


class TestAddFilingTypeArgument:
    def test_adds_argument_with_default(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        args = parser.parse_args([])
        assert args.filing_type == FilingType.TEN_K

    def test_accepts_valid_type(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        args = parser.parse_args(["--filing-type", "20-F"])
        assert args.filing_type == FilingType.TWENTY_F

    def test_accepts_edinet_annual_report_type(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        args = parser.parse_args(["--filing-type", "annual_report"])
        assert args.filing_type == FilingType.ANNUAL_REPORT

    def test_rejects_invalid_type(self):
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--filing-type", "INVALID"])


class TestRequireCompanyAndFiling:
    async def test_returns_both(self):
        from tests.unit.cli.conftest import make_services
        company = MagicMock(id="US_AAPL")
        filing = MagicMock(id=1)
        services = make_services()
        services.company_service.get_company.return_value = company
        services.filing_service.get_latest_filing.return_value = filing
        c, f = await require_company_and_filing(services, "US_AAPL", FilingType.TEN_K)
        assert c.id == "US_AAPL"
        assert f.id == 1


class TestServiceContainer:
    def test_all_fields_accessible(self):
        container = ServiceContainer(
            company_service=MagicMock(),
            financial_service=MagicMock(),
            valuation_service=MagicMock(),
            filing_service=MagicMock(),
            watchlist_service=MagicMock(),
            target_service=MagicMock(),
            job_service=MagicMock(),
            financial_sync=MagicMock(),
            filing_sync=MagicMock(),
            filing_content_service=MagicMock(),
            screening_service=None,
            rag_service=None,
        )
        assert container.company_service is not None
        assert container.screening_service is None


class TestSetupServices:
    async def test_returns_container(self):
        from stock_analyze_system.config import AppConfig
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            config = AppConfig()
            container = await setup_services(session, config)
            assert isinstance(container, ServiceContainer)
            assert container.company_service is not None
            assert container.job_service is not None
        await engine.dispose()

    async def test_constructs_rag_service_when_pageindex_disabled(self):
        """ADR-004 amendment §B: pageindex.enabled=false でも RagService は
        常に構築される (定型分析が PageIndex 非依存になったため)."""
        from stock_analyze_system.config import AppConfig
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        config = AppConfig()
        config.pageindex.enabled = False  # 明示的に無効
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            container = await setup_services(session, config)
            assert container.rag_service is not None
            # PageIndex 経路だけが disabled になっている
            from stock_analyze_system.services.rag_service import PageIndexDisabledError
            with pytest.raises(PageIndexDisabledError):
                await container.rag_service.get_index_status("US_AAPL")
        await engine.dispose()
