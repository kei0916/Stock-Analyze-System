"""FMP クライアントのテスト"""
import pytest

from stock_analyze_system.exceptions import ApiConnectionError
from stock_analyze_system.ingestion.fmp import FmpClient


class TestQuote:
    async def test_quote_success(self, httpx_mock):
        httpx_mock.add_response(json=[{
            "symbol": "AAPL", "price": 185.0, "changesPercentage": 1.5,
        }])
        async with FmpClient(api_key="test_key") as client:
            result = await client.quote("AAPL")
            assert result is not None
            assert result["price"] == 185.0

    async def test_quote_empty(self, httpx_mock):
        httpx_mock.add_response(json=[])
        async with FmpClient(api_key="test_key") as client:
            result = await client.quote("NONEXIST")
            assert result is None


class TestProfile:
    async def test_profile_success(self, httpx_mock):
        httpx_mock.add_response(json=[{
            "symbol": "AAPL", "companyName": "Apple Inc.",
            "sector": "Technology",
        }])
        async with FmpClient(api_key="test_key") as client:
            result = await client.profile("AAPL")
            assert result is not None
            assert result["companyName"] == "Apple Inc."

    async def test_profile_empty(self, httpx_mock):
        httpx_mock.add_response(json=[])
        async with FmpClient(api_key="test_key") as client:
            result = await client.profile("INVALID")
            assert result is None


class TestSearchName:
    async def test_search_name(self, httpx_mock):
        httpx_mock.add_response(json=[
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "AAPD", "name": "Apple Short"},
        ])
        async with FmpClient(api_key="test_key") as client:
            results = await client.search_name("Apple")
            assert len(results) == 2


class TestGetFinancialStatements:
    """M8修正: get_financial_statementsのテスト追加"""
    async def test_get_financial_statements_success(self, httpx_mock):
        httpx_mock.add_response(json=[{
            "date": "2024-09-28", "symbol": "AAPL",
            "revenue": 391035000000, "netIncome": 93736000000,
        }])
        async with FmpClient(api_key="test_key") as client:
            result = await client.get_financial_statements("AAPL")
            assert result is not None
            assert result["revenue"] == 391035000000

    async def test_get_financial_statements_empty(self, httpx_mock):
        httpx_mock.add_response(json=[])
        async with FmpClient(api_key="test_key") as client:
            result = await client.get_financial_statements("INVALID")
            assert result is None


class TestIsAvailable:
    async def test_is_available_true(self, httpx_mock):
        httpx_mock.add_response(json=[{"symbol": "AAPL", "price": 185.0}])
        async with FmpClient(api_key="test_key") as client:
            assert await client.is_available() is True

    async def test_is_available_no_key(self):
        async with FmpClient(api_key="") as client:
            assert await client.is_available() is False

    async def test_is_available_error(self, httpx_mock):
        httpx_mock.add_response(json={"Error Message": "Invalid API Key"})
        async with FmpClient(api_key="bad_key") as client:
            assert await client.is_available() is False

    async def test_is_available_connection_error(self, monkeypatch):
        async def raise_connection_error(_ticker: str):
            raise ApiConnectionError("connection failed")

        async with FmpClient(api_key="test_key") as client:
            monkeypatch.setattr(client, "quote", raise_connection_error)
            assert await client.is_available() is False


class TestGetStockNews:
    async def test_get_stock_news(self, httpx_mock):
        httpx_mock.add_response(json=[
            {"title": "Apple Q4 Results", "url": "https://example.com/news1"},
        ])
        async with FmpClient(api_key="test_key") as client:
            news = await client.get_stock_news("AAPL", limit=5)
            assert len(news) == 1
            assert news[0]["title"] == "Apple Q4 Results"


class TestErrorHandling:
    async def test_fmp_error_message(self, httpx_mock):
        httpx_mock.add_response(json={"Error Message": "Limit Reached"})
        from stock_analyze_system.exceptions import ApiResponseError
        async with FmpClient(api_key="test_key") as client:
            with pytest.raises(ApiResponseError, match="Limit Reached"):
                await client.quote("AAPL")
