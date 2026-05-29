# tests/unit/ingestion/test_stooq.py
from datetime import date, timedelta

import pytest

from stock_analyze_system.ingestion.stooq import (
    StooqAuthError,
    StooqNotFoundError,
    StooqParseError,
    StooqRateLimitError,
    StooqPriceClient,
)

@pytest.mark.asyncio
async def test_fetch_history_parses_csv(httpx_mock):
    # CSV from stooq: newest first (descending date)
    csv_body = "Date,Open,High,Low,Close,Volume\n2021-05-08,100,105,99,104,1000000\n2021-05-07,99,101,98,100,900000"
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=testkey", text=csv_body)
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    rows = await client.fetch_history("AAPL")
    
    assert len(rows) == 2
    # After reverse(), oldest first: rows[0] = 2021-05-07
    assert rows[0]["date"] == date(2021, 5, 7)
    assert rows[0]["close"] == 100.0
    assert rows[1]["date"] == date(2021, 5, 8)
    assert rows[1]["close"] == 104.0

@pytest.mark.asyncio
async def test_fetch_history_filters_by_years(httpx_mock):
    cutoff = date.today() - timedelta(days=10*365)
    old_date = (cutoff - timedelta(days=1)).strftime("%Y-%m-%d")
    new_date = date.today().strftime("%Y-%m-%d")
    csv_body = f"Date,Open,High,Low,Close,Volume\n{new_date},100,105,99,104,1000000\n{old_date},50,55,49,54,500000"
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=msft.us&i=d&apikey=testkey", text=csv_body)
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    rows = await client.fetch_history("MSFT", years=10)
    
    assert len(rows) == 1
    assert rows[0]["date"] == date.fromisoformat(new_date)

@pytest.mark.asyncio
async def test_fetch_history_rejects_auth_error(httpx_mock):
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=invalid", text="Get your apikey:")
    
    client = StooqPriceClient(api_key="invalid", rate=1000)
    with pytest.raises(StooqAuthError):
        await client.fetch_history("AAPL")

@pytest.mark.asyncio
async def test_fetch_history_rejects_empty(httpx_mock):
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=testkey", text="")
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    with pytest.raises(StooqParseError):
        await client.fetch_history("AAPL")

@pytest.mark.asyncio
async def test_fetch_history_not_found(httpx_mock):
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=unknown.us&i=d&apikey=testkey", status_code=404)
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    with pytest.raises(StooqNotFoundError):
        await client.fetch_history("UNKNOWN")

@pytest.mark.asyncio
async def test_fetch_history_rejects_html_captcha(httpx_mock):
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=testkey", text="<html>captcha</html>")
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    with pytest.raises(StooqParseError):
        await client.fetch_history("AAPL")

@pytest.mark.asyncio
async def test_fetch_history_rejects_no_data(httpx_mock):
    httpx_mock.add_response(url="https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=testkey", text="No data for AAPL.US")
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    with pytest.raises(StooqParseError):
        await client.fetch_history("AAPL")

@pytest.mark.asyncio
async def test_fetch_history_rejects_rate_limit(httpx_mock):
    """日次上限応答を StooqRateLimitError として検出"""
    httpx_mock.add_response(
        url="https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=testkey",
        text="Exceeded the daily hits limit",
    )
    
    client = StooqPriceClient(api_key="testkey", rate=1000)
    with pytest.raises(StooqRateLimitError):
        await client.fetch_history("AAPL")
