"""JobService のテスト"""
from dataclasses import asdict
from datetime import date, datetime
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from stock_analyze_system.exceptions import ApiConnectionError
from stock_analyze_system.models.enums import PeriodType
from stock_analyze_system.services import job as job_module
from stock_analyze_system.services.job import JobService, SyncResult
from stock_analyze_system.services.valuation import compute_valuation_from_financials


class TestSyncResult:
    def test_dataclass_defaults(self):
        result = SyncResult(company_id="US_AAPL")
        assert result.financials_count == 0
        assert result.filings_count == 0
        assert result.valuations_count == 0
        assert result.errors == []

    def test_serializable(self):
        result = SyncResult(company_id="US_AAPL", financials_count=5)
        d = asdict(result)
        assert d["financials_count"] == 5


class TestComputeValuationFromFinancials:
    def test_normal(self):
        fd = MagicMock(
            eps=6.0, equity=100e9, shares_outstanding=15e9,
            total_debt=100e9, cash=50e9, ebitda=130e9,
            revenue=394e9, fcf=111e9, net_income=94e9,
        )
        result = compute_valuation_from_financials(
            stock_price=185.0, fd=fd, currency="USD",
            val_date=date(2024, 1, 1), market_cap=3e12,
        )
        assert result["stock_price"] == 185.0
        assert result["per"] is not None

    def test_stock_price_none_returns_minimal(self):
        """新発見1: stock_price が None の場合、安全に処理されること"""
        fd = MagicMock(eps=6.0, equity=100e9)
        result = compute_valuation_from_financials(
            stock_price=None, fd=fd, currency="USD",
            val_date=date(2024, 1, 1),
        )
        assert result["stock_price"] is None
        assert result["per"] is None

    def test_shares_none_explicit_check(self):
        """新発見2: shares_outstanding が None でも TypeError にならないこと"""
        fd = MagicMock(
            eps=6.0, equity=100e9, shares_outstanding=None,
            total_debt=100e9, cash=50e9, ebitda=130e9,
            revenue=394e9, fcf=111e9, net_income=94e9,
        )
        result = compute_valuation_from_financials(
            stock_price=185.0, fd=fd, currency="USD",
            val_date=date(2024, 1, 1),
        )
        # market_cap is None → effective_mcap is None
        assert result["ev_ebitda"] is None


class TestJobService:
    async def test_sync_company_counts(self):
        """Bug #4: sync_company が正しいカウントを返すこと"""
        company = MagicMock(
            id="US_AAPL", cik="0000320193", edinet_code=None,
            accounting_standard="US-GAAP",
        )
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")
        company_svc.is_us_market = MagicMock(return_value=True)

        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 5

        filing_sync = AsyncMock()
        filing_sync.update_from_sec.return_value = 2

        valuation_svc = AsyncMock()
        yahoo_client = AsyncMock()
        yahoo_client.get_stock_price.return_value = {
            "price": 185.0, "market_cap": 3e12, "currency": "USD",
        }

        financial_svc = AsyncMock()
        fd_mock = MagicMock(
            eps=6.0, equity=100e9, shares_outstanding=15e9,
            total_debt=100e9, cash=50e9, ebitda=130e9,
            revenue=394e9, fcf=111e9, net_income=94e9,
        )
        financial_svc.get_latest.return_value = fd_mock

        svc = JobService(
            company_svc=company_svc,
            financial_sync=financial_sync,
            filing_sync=filing_sync,
            valuation_svc=valuation_svc,
            financial_svc=financial_svc,
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
        )
        result = await svc.sync_company("US_AAPL")
        assert result.financials_count == 5
        assert result.filings_count == 2
        assert result.valuations_count >= 1
        saved = valuation_svc.upsert_valuation.await_args.args[1]
        assert isinstance(saved["last_updated"], datetime)

    async def test_sync_company_edinet_path(self):
        """非USマーケット企業でEDINETパスが使われること"""
        company = MagicMock(
            id="JP_7203", cik=None, edinet_code="E02144",
            accounting_standard="JP-GAAP",
        )
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="7203.T")
        company_svc.is_us_market = MagicMock(return_value=False)

        financial_sync = AsyncMock()
        financial_sync.update_from_edinet.return_value = 3

        filing_sync = AsyncMock()
        filing_sync.update_from_edinet.return_value = 1

        yahoo_client = AsyncMock()
        yahoo_client.get_stock_price.return_value = None

        svc = JobService(
            company_svc=company_svc,
            financial_sync=financial_sync,
            filing_sync=filing_sync,
            valuation_svc=AsyncMock(),
            financial_svc=AsyncMock(),
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
        )
        result = await svc.sync_company("JP_7203")
        assert result.financials_count == 3
        assert result.filings_count == 1
        financial_sync.update_from_edinet.assert_called_once()
        filing_sync.update_from_edinet.assert_called_once()

    async def test_sync_company_valuation_error_captured(self):
        """バリュエーション計算エラーがerrorsに記録されること"""
        company = MagicMock(
            id="US_AAPL", cik="0000320193", edinet_code=None,
            accounting_standard="US-GAAP",
        )
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")
        company_svc.is_us_market = MagicMock(return_value=True)

        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 0
        filing_sync = AsyncMock()
        filing_sync.update_from_sec.return_value = 0

        yahoo_client = AsyncMock()
        yahoo_client.get_stock_price.side_effect = ValueError("API down")

        svc = JobService(
            company_svc=company_svc,
            financial_sync=financial_sync,
            filing_sync=filing_sync,
            valuation_svc=AsyncMock(),
            financial_svc=AsyncMock(),
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
        )
        result = await svc.sync_company("US_AAPL")
        assert len(result.errors) == 1
        assert "Valuation error" in result.errors[0]

    async def test_sync_company_no_ticker(self):
        """yf_ticker がない場合はバリュエーションスキップ"""
        company = MagicMock(
            id="US_AAPL", cik="0000320193", edinet_code=None,
            accounting_standard="US-GAAP",
        )
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 0
        filing_sync = AsyncMock()
        filing_sync.update_from_sec.return_value = 0

        svc = JobService(
            company_svc=company_svc,
            financial_sync=financial_sync,
            filing_sync=filing_sync,
            valuation_svc=AsyncMock(),
            financial_svc=AsyncMock(),
            yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )
        result = await svc.sync_company("US_AAPL")
        assert result.valuations_count == 0
        assert result.errors == []

    async def test_sync_company_not_found(self):
        """存在しない企業で ValueError"""
        company_svc = AsyncMock()
        company_svc.get_company.return_value = None

        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=AsyncMock(),
            financial_svc=AsyncMock(),
            yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )
        with pytest.raises(ValueError, match="not found"):
            await svc.sync_company("US_NONEXIST")

    async def test_update_valuation_for_company_updates_single_company(self):
        company = MagicMock(id="US_AAPL", ticker="AAPL")

        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")

        yahoo_client = AsyncMock()
        yahoo_client.get_stock_price.return_value = {
            "price": 185.0,
            "market_cap": 3e12,
            "currency": "USD",
        }

        valuation_svc = AsyncMock()
        financial_svc = AsyncMock()
        financial_svc.get_latest.return_value = None

        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=valuation_svc,
            financial_svc=financial_svc,
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
        )

        result = await svc.update_valuation_for_company("US_AAPL")

        assert result.company_id == "US_AAPL"
        assert result.valuations_count == 1
        assert result.errors == []
        company_svc.get_company.assert_awaited_once_with("US_AAPL")
        yahoo_client.get_stock_price.assert_awaited_once_with("AAPL")
        valuation_svc.upsert_valuation.assert_awaited_once()

    async def test_update_valuation_uses_google_sheets_cached_quote(self):
        company = MagicMock(id="US_AAPL", ticker="AAPL")

        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")

        quote = MagicMock(
            status="ok",
            price=185.0,
            currency="USD",
        )
        quote_service = AsyncMock()
        quote_service.get_latest_price.return_value = quote

        yahoo_client = AsyncMock()
        valuation_svc = AsyncMock()
        financial_svc = AsyncMock()
        financial_svc.get_latest.return_value = MagicMock(
            eps=6.0,
            equity=100e9,
            shares_outstanding=15e9,
            total_debt=100e9,
            cash=50e9,
            ebitda=130e9,
            revenue=394e9,
            fcf=111e9,
            net_income=94e9,
        )

        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=valuation_svc,
            financial_svc=financial_svc,
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
            quote_service=quote_service,
        )

        result = await svc.update_valuation_for_company(
            "US_AAPL",
            quote_provider="google_sheets",
        )

        assert result.valuations_count == 1
        yahoo_client.get_stock_price.assert_not_awaited()
        saved = valuation_svc.upsert_valuation.await_args.args[1]
        assert saved["stock_price"] == 185.0
        assert saved["market_cap"] == 185.0 * 15e9

    async def test_google_sheets_quote_provider_missing_quote_skips_valuation(self):
        company = MagicMock(id="US_AAPL", ticker="AAPL")
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")

        quote_service = AsyncMock()
        quote_service.get_latest_price.return_value = MagicMock(
            status="formula_error",
            price=None,
            currency=None,
        )
        valuation_svc = AsyncMock()

        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=valuation_svc,
            financial_svc=AsyncMock(),
            yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
            quote_service=quote_service,
        )

        result = await svc.update_valuation_for_company(
            "US_AAPL",
            quote_provider="google_sheets",
        )

        assert result.valuations_count == 0
        assert "No usable quote" in result.skipped_reasons[0]
        valuation_svc.upsert_valuation.assert_not_awaited()

    async def test_update_valuation_rejects_unknown_quote_provider(self):
        company = MagicMock(id="US_AAPL", ticker="AAPL")
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")
        yahoo_client = AsyncMock()
        valuation_svc = AsyncMock()
        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=valuation_svc,
            financial_svc=AsyncMock(),
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
        )

        result = await svc.update_valuation_for_company(
            "US_AAPL",
            quote_provider="google-sheet",
        )

        assert result.valuations_count == 0
        assert result.errors == [
            "Unsupported quote provider: google-sheet; "
            "quote_provider must be one of: google_sheets, yahoo"
        ]
        yahoo_client.get_stock_price.assert_not_awaited()
        valuation_svc.upsert_valuation.assert_not_awaited()


class TestRunDailyUpdate:
    def _make_job_svc(self, companies=None, **overrides):
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = companies or []
        company_svc.get_company = AsyncMock(return_value=None)
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)
        company_svc.is_us_market = MagicMock(return_value=True)

        defaults = {
            "company_svc": company_svc,
            "financial_sync": AsyncMock(),
            "filing_sync": AsyncMock(),
            "valuation_svc": AsyncMock(),
            "financial_svc": AsyncMock(),
            "yahoo_client": AsyncMock(),
            "fmp_client": AsyncMock(),
        }
        defaults.update(overrides)
        return JobService(**defaults)

    def test_default_sec_filing_date_uses_new_york(self, monkeypatch):
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                utc_now = datetime(2026, 4, 28, 1, 30, tzinfo=ZoneInfo("UTC"))
                if tz is None:
                    return utc_now.replace(tzinfo=None)
                return utc_now.astimezone(tz)

        monkeypatch.setattr(job_module, "datetime", FrozenDateTime)

        assert job_module._default_sec_filing_date() == date(2026, 4, 27)

    async def test_us_daily_update_uses_sec_daily_filings_not_sync_company(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        expected_filings = [
            {
                "cik": "0000320193",
                "form": "10-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000320193-26-000001",
                "reportDate": "",
            },
        ]
        filing_sync.list_daily_sec_filings.return_value = expected_filings
        filing_sync.update_from_sec_records.return_value = 1

        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 4

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )
        svc.sync_company = AsyncMock(side_effect=AssertionError("sync_company must not be called"))

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.total_companies == 1
        assert len(result.results) == 1
        assert result.results[0].company_id == "US_AAPL"
        assert result.results[0].filings_count == 1
        assert result.results[0].financials_count == 4
        filing_sync.list_daily_sec_filings.assert_awaited_once_with(
            date(2026, 4, 28),
            form_types=["10-K", "10-Q", "20-F", "40-F", "8-K", "6-K"],
        )
        filing_sync.update_from_sec_records.assert_awaited_once_with(
            "US_AAPL",
            expected_filings,
        )
        financial_sync.update_from_sec.assert_awaited_once_with(
            "US_AAPL",
            "320193",
            "US-GAAP",
            period_types=(PeriodType.ANNUAL, PeriodType.QUARTERLY),
        )
        svc.sync_company.assert_not_awaited()

    async def test_target_valuation_update_filters_analysis_targets_by_market(self):
        aapl = MagicMock(id="US_AAPL", ticker="AAPL")
        toyota = MagicMock(id="JP_7203", ticker=None, security_code="7203")
        targets = [
            MagicMock(company_id="US_AAPL"),
            MagicMock(company_id="JP_7203"),
        ]

        target_svc = AsyncMock()
        target_svc.list_targets.return_value = targets

        company_svc = AsyncMock()
        company_svc.get_company.side_effect = {
            "US_AAPL": aapl,
            "JP_7203": toyota,
        }.__getitem__
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")

        yahoo_client = AsyncMock()
        yahoo_client.get_stock_price.return_value = {
            "price": 185.0,
            "market_cap": 3e12,
            "currency": "USD",
        }

        valuation_svc = AsyncMock()
        financial_svc = AsyncMock()
        financial_svc.get_latest.return_value = None

        svc = self._make_job_svc(
            company_svc=company_svc,
            target_svc=target_svc,
            valuation_svc=valuation_svc,
            financial_svc=financial_svc,
            yahoo_client=yahoo_client,
        )

        result = await svc.run_target_valuation_update(market="us")

        assert result.market == "us"
        assert result.total_companies == 1
        assert [r.company_id for r in result.results] == ["US_AAPL"]
        assert result.results[0].valuations_count == 1
        company_svc.get_company.assert_awaited_once_with("US_AAPL")
        yahoo_client.get_stock_price.assert_awaited_once_with("AAPL")
        valuation_svc.upsert_valuation.assert_awaited_once()

    async def test_target_valuation_update_records_missing_target_company(self):
        target_svc = AsyncMock()
        target_svc.list_targets.return_value = [MagicMock(company_id="US_MISSING")]

        company_svc = AsyncMock()
        company_svc.get_company.return_value = None
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        svc = self._make_job_svc(
            company_svc=company_svc,
            target_svc=target_svc,
        )

        result = await svc.run_target_valuation_update(market="all")

        assert result.total_companies == 1
        assert result.results[0].company_id == "US_MISSING"
        assert result.results[0].errors == ["Company 'US_MISSING' not found"]

    async def test_target_valuation_update_rejects_unknown_quote_provider(self):
        target_svc = AsyncMock()

        svc = self._make_job_svc(target_svc=target_svc)

        with pytest.raises(ValueError, match="quote_provider must be one of"):
            await svc.run_target_valuation_update(
                market="all",
                quote_provider="google-sheet",
            )

        target_svc.list_targets.assert_not_awaited()

    async def test_us_daily_update_captures_sec_daily_feed_api_connection_error(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="0000320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.side_effect = ApiConnectionError("SEC down")
        financial_sync = AsyncMock()

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )
        svc.sync_company = AsyncMock(side_effect=AssertionError("no fallback polling"))

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.total_companies == 1
        assert len(result.results) == 1
        assert result.results[0].company_id == "SEC_EDGAR"
        assert result.results[0].errors == ["SEC down"]
        assert result.finished_at is not None
        filing_sync.update_from_sec_records.assert_not_called()
        financial_sync.update_from_sec.assert_not_called()
        svc.sync_company.assert_not_awaited()

    async def test_us_daily_update_captures_sec_financial_http_error(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="0000320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0000320193",
                "form": "10-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000320193-26-000001",
            },
        ]
        filing_sync.update_from_sec_records.return_value = 1

        request = httpx.Request("GET", "https://www.sec.gov/")
        response = httpx.Response(503, request=request)
        financial_sync = AsyncMock()
        financial_sync.update_from_sec.side_effect = httpx.HTTPStatusError(
            "SEC unavailable",
            request=request,
            response=response,
        )

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert len(result.results) == 1
        assert result.results[0].company_id == "US_AAPL"
        assert result.results[0].filings_count == 1
        assert result.results[0].financials_count == 0
        assert result.results[0].errors == ["Financial error: SEC unavailable"]
        assert result.finished_at is not None

    async def test_us_daily_update_skips_unknown_cik(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="0000320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0009999999",
                "form": "10-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0009999999-26-000001",
            },
        ]

        svc = self._make_job_svc(company_svc=company_svc, filing_sync=filing_sync)
        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.total_companies == 1
        assert result.results == []
        filing_sync.update_from_sec_records.assert_not_called()

    async def test_us_daily_update_8k_registers_without_financial_refresh(self):
        msft = MagicMock(
            id="US_MSFT",
            cik="789019",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="MSFT",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [msft]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0000789019",
                "form": "8-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000789019-26-000002",
            },
        ]
        filing_sync.update_from_sec_records.return_value = 1
        financial_sync = AsyncMock()

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.results[0].filings_count == 1
        assert result.results[0].financials_count == 0
        financial_sync.update_from_sec.assert_not_called()

    async def test_us_daily_update_refreshes_financials_once_per_company(self):
        aapl = MagicMock(
            id="US_AAPL",
            cik="0000320193",
            edinet_code=None,
            accounting_standard="US-GAAP",
            ticker="AAPL",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [aapl]
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        filing_sync = AsyncMock()
        filing_sync.list_daily_sec_filings.return_value = [
            {
                "cik": "0000320193",
                "form": "10-K",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000320193-26-000001",
            },
            {
                "cik": "0000320193",
                "form": "10-Q",
                "filingDate": "2026-04-28",
                "accessionNumber": "0000320193-26-000002",
            },
        ]
        filing_sync.update_from_sec_records.return_value = 2
        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 8

        svc = self._make_job_svc(
            company_svc=company_svc,
            filing_sync=filing_sync,
            financial_sync=financial_sync,
        )

        result = await svc.run_daily_update(market="us", target_date=date(2026, 4, 28))

        assert result.results[0].filings_count == 2
        assert result.results[0].financials_count == 8
        financial_sync.update_from_sec.assert_awaited_once()

    async def test_jp_daily_update_keeps_existing_sync_company_path(self):
        jp_co = MagicMock(
            id="JP_7203",
            cik=None,
            edinet_code="E02144",
            accounting_standard="JP-GAAP",
        )
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [jp_co]
        svc = self._make_job_svc(company_svc=company_svc)
        svc.sync_company = AsyncMock(return_value=SyncResult(company_id="JP_7203", filings_count=1))

        result = await svc.run_daily_update(market="jp", target_date=date(2026, 4, 28))

        assert result.total_companies == 1
        assert result.results[0].company_id == "JP_7203"
        svc.sync_company.assert_awaited_once_with("JP_7203")

    async def test_daily_update_filters_by_market(self):
        """market パラメータで企業がフィルタされること"""
        us_co = MagicMock(id="US_AAPL", cik="123", edinet_code=None, accounting_standard="US-GAAP")
        jp_co = MagicMock(id="JP_7203", cik=None, edinet_code="E02144", accounting_standard="JP-GAAP")

        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [us_co, jp_co]
        company_svc.get_company = AsyncMock(side_effect=lambda cid: us_co if cid == "US_AAPL" else jp_co)
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)
        company_svc.is_us_market = MagicMock(return_value=True)

        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 0
        filing_sync = AsyncMock()
        filing_sync.update_from_sec.return_value = 0

        svc = self._make_job_svc(
            company_svc=company_svc,
            financial_sync=financial_sync,
            filing_sync=filing_sync,
        )
        result = await svc.run_daily_update(market="us")
        assert result.total_companies == 1
        assert result.market == "us"
        assert result.finished_at is not None

    async def test_daily_update_captures_sync_failure(self):
        """sync_company の例外がエラーとして集約されること"""
        co = MagicMock(id="JP_FAIL", cik=None, edinet_code="E99999", accounting_standard="JP-GAAP")
        company_svc = AsyncMock()
        company_svc.list_companies.return_value = [co]
        company_svc.get_company = AsyncMock(side_effect=ValueError("DB error"))
        company_svc.resolve_yf_ticker = MagicMock(return_value=None)

        svc = self._make_job_svc(company_svc=company_svc)
        result = await svc.run_daily_update(market="jp")
        assert result.total_companies == 1
        assert len(result.results) == 1
        assert len(result.results[0].errors) == 1

    async def test_daily_update_empty_market(self):
        """企業がない場合でも正常終了すること"""
        svc = self._make_job_svc(companies=[])
        result = await svc.run_daily_update(market="us")
        assert result.total_companies == 0
        assert result.results == []
        assert result.finished_at is not None
