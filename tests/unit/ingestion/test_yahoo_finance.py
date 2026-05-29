"""Yahoo Finance クライアントのテスト"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stock_analyze_system.ingestion.yahoo_finance import (
    YahooFinanceClient,
    _epoch_to_date,
)


class TestEpochToDate:
    def test_basic_conversion(self):
        assert _epoch_to_date(1759190400) == "2025-09-30"

    def test_float_input(self):
        assert _epoch_to_date(1759190400.0) == "2025-09-30"

    def test_epoch_zero(self):
        assert _epoch_to_date(0) == "1970-01-01"


class TestGetStockPrice:
    async def test_returns_price_data(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 185.0,
            "marketCap": 2800000000000,
            "fiftyTwoWeekHigh": 199.62,
            "fiftyTwoWeekLow": 124.17,
            "currency": "USD",
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_stock_price("AAPL")
            assert result is not None
            assert result["price"] == 185.0
            assert result["market_cap"] == 2800000000000
            assert result["currency"] == "USD"

    async def test_returns_none_on_no_price(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_stock_price("INVALID")
            assert result is None


class TestGetScreeningInfo:
    async def test_returns_screening_data(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 185.0,
            "marketCap": 2800000000000,
            "trailingPE": 28.5,
            "trailingEps": 6.16,
            "returnOnEquity": 0.175,
            "operatingMargins": 0.30,
            "profitMargins": 0.26,
            "revenueGrowth": 0.05,
            "earningsGrowth": 0.10,
            "priceToBook": 45.0,
            "priceToSalesTrailing12Months": 7.5,
            "enterpriseToEbitda": 20.0,
            "forwardPE": 25.0,
            "dividendYield": 0.006,
            "debtToEquity": 150.0,
            "pegRatio": 2.5,
            "freeCashflow": 110000000000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NMS",
            "beta": 1.2,
            "averageVolume": 50000000,
            "mostRecentQuarter": 1727481600,
            "lastFiscalYearEnd": 1727481600,
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_screening_info("AAPL")
            assert result is not None
            assert result["roe"] == 0.175
            assert result["de_ratio"] == 1.5  # 150/100
            assert result["sector"] == "Technology"

    async def test_fcf_yield_calculation(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 100.0,
            "marketCap": 1000,
            "freeCashflow": 100,
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_screening_info("TEST")
            assert result is not None
            assert result["fcf_yield"] == pytest.approx(0.1)

    async def test_fcf_yield_zero_mcap(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 100.0,
            "marketCap": 0,
            "freeCashflow": 100,
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_screening_info("TEST")
            assert result is not None
            assert result["fcf_yield"] is None


class TestGetStockPriceExceptionHandling:
    async def test_returns_none_on_exception(self):
        """例外発生時にNoneを返すこと"""
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.side_effect = RuntimeError("network error")
            client = YahooFinanceClient()
            result = await client.get_stock_price("AAPL")
            assert result is None


class TestGetScreeningInfoExceptionHandling:
    async def test_returns_none_on_exception(self):
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.side_effect = RuntimeError("network error")
            client = YahooFinanceClient()
            result = await client.get_screening_info("AAPL")
            assert result is None

    async def test_returns_none_when_price_is_none(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": None, "currentPrice": None}
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_screening_info("TEST")
            assert result is None


class TestGetQuarterlyFinancials:
    async def test_returns_empty_on_exception(self):
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.side_effect = RuntimeError("error")
            client = YahooFinanceClient()
            result = await client.get_quarterly_financials("AAPL")
            assert result == []


class TestGetPriceHistory:
    async def test_returns_empty_on_exception(self):
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.side_effect = RuntimeError("error")
            client = YahooFinanceClient()
            result = await client.get_price_history("AAPL")
            assert result == []


class TestFetchQuarterly:
    def test_parses_quarterly_data(self):
        """四半期データが正しくパースされること"""
        col = pd.Timestamp("2024-09-28")
        income = pd.DataFrame(
            {
                col: [100e9, 30e9, 25e9, 35e9, 6.5, 40e9, 5e9, 28e9],
            },
            index=[
                "Total Revenue", "Operating Income", "Net Income",
                "EBITDA", "Diluted EPS", "Cost Of Revenue",
                "Tax Provision", "Pretax Income",
            ],
        )
        balance = pd.DataFrame(
            {
                col: [350e9, 70e9, 150e9, 120e9, 100e9, 30e9, 5e9, 15e9],
            },
            index=[
                "Total Assets", "Stockholders Equity", "Current Assets",
                "Current Liabilities", "Total Debt", "Cash And Cash Equivalents",
                "Inventory", "Share Issued",
            ],
        )
        cashflow = pd.DataFrame(
            {
                col: [28e9, -10e9, 18e9, -3e9, -5e9],
            },
            index=[
                "Operating Cash Flow", "Capital Expenditure",
                "Free Cash Flow", "Common Stock Dividend Paid",
                "Repurchase Of Capital Stock",
            ],
        )

        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = income
        mock_ticker.quarterly_balance_sheet = balance
        mock_ticker.quarterly_cashflow = cashflow

        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_quarterly("AAPL")

        assert len(records) == 1
        r = records[0]
        assert r["fiscal_year_end"] == "2024-09-28"
        assert r["revenue"] == 100e9
        assert r["operating_income"] == 30e9
        assert r["net_income"] == 25e9
        assert r["eps"] == 6.5
        assert r["total_assets"] == 350e9
        assert r["operating_cf"] == 28e9
        assert r["fcf"] == 18e9

    def test_empty_income_returns_empty(self):
        """income_stmt が空の場合は空リストを返す"""
        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = pd.DataFrame()
        mock_ticker.quarterly_balance_sheet = pd.DataFrame()
        mock_ticker.quarterly_cashflow = pd.DataFrame()

        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_quarterly("AAPL")
        assert records == []

    def test_none_income_returns_empty(self):
        """income_stmt が None の場合は空リストを返す"""
        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = None
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_quarterly("AAPL")
        assert records == []

    def test_nan_values_become_none(self):
        """NaN値がNoneに変換されること"""
        col = pd.Timestamp("2024-09-28")
        income = pd.DataFrame(
            {col: [float("nan")]},
            index=["Total Revenue"],
        )
        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = income
        mock_ticker.quarterly_balance_sheet = pd.DataFrame()
        mock_ticker.quarterly_cashflow = pd.DataFrame()

        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_quarterly("AAPL")
        assert len(records) == 1
        assert records[0]["revenue"] is None

    def test_fcf_derived_when_missing(self):
        """FCFがない場合にoperating_cf - abs(capex)で導出"""
        col = pd.Timestamp("2024-09-28")
        income = pd.DataFrame({col: [100e9]}, index=["Total Revenue"])
        cashflow = pd.DataFrame(
            {col: [50e9, -10e9]},
            index=["Operating Cash Flow", "Capital Expenditure"],
        )
        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = income
        mock_ticker.quarterly_balance_sheet = pd.DataFrame()
        mock_ticker.quarterly_cashflow = cashflow

        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_quarterly("AAPL")
        assert records[0]["fcf"] == 40e9


class TestGetScreeningInfoBatch:
    async def test_success_maps_all_fields(self):
        """1000銘柄のバッチリクエストが成功し、正しい辞書を返す"""
        mock_response = {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "AAPL",
                        "regularMarketPrice": 150.0,
                        "marketCap": 2000000000000,
                        "trailingPE": 25.0,
                        "forwardPE": 22.0,
                        "priceToBook": 30.0,
                        "dividendYield": 0.005,
                        "exchange": "NMS",
                        "fiftyTwoWeekHigh": 180.0,
                        "fiftyTwoWeekLow": 120.0,
                        "averageVolume": 50000000,
                        "trailingEps": 6.0,
                    },
                    {
                        "symbol": "MSFT",
                        "regularMarketPrice": 300.0,
                        "marketCap": 2500000000000,
                        "trailingPE": 30.0,
                    },
                ],
                "error": None,
            }
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.YfData") as MockYfData:
            mock_data = MagicMock()
            mock_data.get_raw_json.return_value = mock_response
            MockYfData.return_value = mock_data

            client = YahooFinanceClient(rate=1000.0)
            result = await client.get_screening_info_batch(["AAPL", "MSFT"])

            assert len(result) == 2
            assert result["AAPL"]["stock_price"] == 150.0
            assert result["AAPL"]["market_cap"] == 2000000000000
            assert result["AAPL"]["trailing_per"] == 25.0
            assert result["AAPL"]["forward_per"] == 22.0
            assert result["AAPL"]["pbr"] == 30.0
            assert result["AAPL"]["dividend_yield"] == 0.005
            assert result["AAPL"]["exchange"] == "NMS"
            assert result["AAPL"]["fifty_two_week_high"] == 180.0
            assert result["AAPL"]["fifty_two_week_low"] == 120.0
            assert result["AAPL"]["volume"] == 50000000
            assert result["AAPL"]["eps"] == 6.0
            assert result["MSFT"]["stock_price"] == 300.0

            mock_data.get_raw_json.assert_called_once()
            call_args = mock_data.get_raw_json.call_args
            assert call_args.kwargs["params"]["symbols"] == "AAPL,MSFT"

    async def test_partial_failure_skips_missing(self):
        """一部銘柄が失敗しても成功銘柄は返す"""
        mock_response = {
            "quoteResponse": {
                "result": [{"symbol": "AAPL", "regularMarketPrice": 150.0}],
                "error": [{"code": "Not Found", "symbol": "INVALID"}],
            }
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.YfData") as MockYfData:
            mock_data = MagicMock()
            mock_data.get_raw_json.return_value = mock_response
            MockYfData.return_value = mock_data

            client = YahooFinanceClient(rate=1000.0)
            result = await client.get_screening_info_batch(["AAPL", "INVALID"])
            assert "AAPL" in result
            assert "INVALID" not in result

    async def test_empty_input(self):
        """空リストの場合は空辞書を返す"""
        client = YahooFinanceClient(rate=1000.0)
        result = await client.get_screening_info_batch([])
        assert result == {}

    async def test_api_error_returns_empty(self):
        """Yahoo API が全体エラーを返した場合は空辞書を返す"""
        with patch("stock_analyze_system.ingestion.yahoo_finance.YfData") as MockYfData:
            mock_data = MagicMock()
            mock_data.get_raw_json.side_effect = Exception("Connection timeout")
            MockYfData.return_value = mock_data

            client = YahooFinanceClient(rate=1000.0)
            result = await client.get_screening_info_batch(["AAPL"])
            assert result == {}


class TestFetchHistory:
    def test_parses_history(self):
        """履歴データが正しくパースされること"""
        idx = pd.DatetimeIndex([pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")])
        hist = pd.DataFrame(
            {"Close": [185.0, 186.5], "Volume": [50000000, 45000000]},
            index=idx,
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist

        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_history("AAPL", "10y")
        assert len(records) == 2
        assert records[0]["date"] == "2024-01-02"
        assert records[0]["close"] == 185.0
        assert records[0]["volume"] == 50000000

    def test_empty_history(self):
        """空の履歴でも空リストを返す"""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_history("AAPL", "10y")
        assert records == []

    def test_none_history(self):
        """None履歴でも空リストを返す"""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = None

        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            records = YahooFinanceClient._fetch_history("AAPL", "10y")
        assert records == []
