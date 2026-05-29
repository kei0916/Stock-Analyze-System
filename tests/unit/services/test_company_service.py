"""CompanyService のテスト"""
import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.services.company import CompanyService


class TestBuildCompanyId:
    """build_company_id 静的メソッド（Bug #7 修正確認含む）"""

    def test_us_market(self):
        assert CompanyService.build_company_id(
            ticker="AAPL", security_code=None, market="NASDAQ",
        ) == "US_AAPL"

    def test_jp_market(self):
        assert CompanyService.build_company_id(
            ticker=None, security_code="7203", market="TSE_PRIME",
        ) == "JP_7203"

    def test_unknown_market_raises(self):
        """Bug #7: 未知の市場で ValueError が発生すること"""
        with pytest.raises(ValueError, match="Unknown market"):
            CompanyService.build_company_id(
                ticker="TEST", security_code=None, market="INVALID_MARKET",
            )

    def test_us_market_no_ticker_raises(self):
        with pytest.raises(ValueError, match="ticker is required"):
            CompanyService.build_company_id(
                ticker=None, security_code=None, market="NYSE",
            )

    def test_jp_market_no_security_code_raises(self):
        with pytest.raises(ValueError, match="security_code is required"):
            CompanyService.build_company_id(
                ticker=None, security_code=None, market="TSE_PRIME",
            )

    def test_all_us_markets(self):
        for market in ("NYSE", "NASDAQ", "AMEX", "OTC"):
            result = CompanyService.build_company_id(
                ticker="TEST", security_code=None, market=market,
            )
            assert result == "US_TEST"

    def test_all_jp_markets(self):
        for market in ("TSE_PRIME", "TSE_STANDARD", "TSE_GROWTH", "TSE"):
            result = CompanyService.build_company_id(
                ticker=None, security_code="1234", market=market,
            )
            assert result == "JP_1234"


class TestResolveYfTicker:
    """Yahoo Finance ticker 解決"""

    def test_us_company(self):
        company = Company(
            id="US_AAPL", ticker="AAPL", name="Apple",
            market="NASDAQ", accounting_standard="US-GAAP",
        )
        assert CompanyService.resolve_yf_ticker(company) == "AAPL"

    def test_jp_company(self):
        company = Company(
            id="JP_7203", security_code="7203", name="Toyota",
            market="TSE_PRIME", accounting_standard="IFRS",
        )
        assert CompanyService.resolve_yf_ticker(company) == "7203.T"

    def test_jp_no_security_code(self):
        company = Company(
            id="JP_UNKNOWN", name="Unknown",
            market="TSE_PRIME", accounting_standard="IFRS",
        )
        assert CompanyService.resolve_yf_ticker(company) is None


class TestCompanyServiceAsync:
    """非同期サービスメソッド"""

    async def test_register_company_new(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        company = await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc.",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        assert company.id == "US_AAPL"
        assert company.ticker == "AAPL"

    async def test_register_company_update(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc.",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        updated = await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc. (Updated)",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        assert updated.name == "Apple Inc. (Updated)"

    async def test_get_company(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        result = await svc.get_company("US_AAPL")
        assert result is not None

    async def test_search_companies(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc.",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        results = await svc.search_companies("Apple")
        assert len(results) == 1

    async def test_find_by_identifier(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        result = await svc.find_by_identifier("AAPL")
        assert result is not None
        assert result.id == "US_AAPL"

    async def test_register_sec_filer_with_ticker_uses_us_id(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)

        company = await svc.register_sec_filer(
            cik="1504776",
            name="Warby Parker Inc.",
            ticker="wrby",
            exchange="NYSE",
        )

        assert company.id == "US_WRBY"
        assert company.ticker == "WRBY"
        assert company.cik == "0001504776"
        assert company.market == "NYSE"

    async def test_register_sec_filer_without_ticker_uses_sec_cik_id(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)

        company = await svc.register_sec_filer(
            cik="1234567",
            name="Private ABS Trust",
        )

        assert company.id == "SEC_0001234567"
        assert company.ticker is None
        assert company.cik == "0001234567"
        assert company.market == "SEC"
