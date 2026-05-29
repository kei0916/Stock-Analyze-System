from datetime import date

from stock_analyze_system.models.price_history import PriceHistory

def test_price_history_fields():
    ph = PriceHistory(
        company_id="US_AAPL",
        ticker="AAPL",
        date=date(2021, 5, 8),
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000000,
    )
    assert ph.company_id == "US_AAPL"
    assert ph.ticker == "AAPL"
    assert ph.date == date(2021, 5, 8)
