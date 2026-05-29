from stock_analyze_system.config import GoogleSheetsConfig
from stock_analyze_system.services.google_sheets_quotes import (
    GoogleSheetsQuoteClient,
    QuoteRequest,
)


class FakeValues:
    def __init__(self, read_values):
        self.updated_body = None
        self.read_values = _as_response_sequence(read_values)
        self.batch_get_calls = 0

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.updated_body = body
        return FakeExecute({"updatedRows": len(body["values"])})

    def batchGet(self, spreadsheetId, ranges, valueRenderOption):
        idx = min(self.batch_get_calls, len(self.read_values) - 1)
        self.batch_get_calls += 1
        return FakeExecute({"valueRanges": [{"values": self.read_values[idx]}]})


class FakeSpreadsheets:
    def __init__(self, values):
        self._values = values

    def values(self):
        return self._values


class FakeService:
    def __init__(self, read_values):
        self.values_api = FakeValues(read_values)

    def spreadsheets(self):
        return FakeSpreadsheets(self.values_api)


class FakeExecute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


def _as_response_sequence(read_values):
    if read_values and isinstance(read_values[0], list) and read_values[0]:
        if isinstance(read_values[0][0], list):
            return read_values
    return [read_values]


def test_refresh_quotes_parses_successful_values():
    service = FakeService([
        ["US_AAPL", "NASDAQ:AAPL", 185.25, "USD", 20],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="test",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_AAPL", provider_symbol="NASDAQ:AAPL"),
    ])

    assert results[0].company_id == "US_AAPL"
    assert results[0].price == 185.25
    assert results[0].currency == "USD"
    assert results[0].data_delay_minutes == 20
    assert results[0].status == "ok"
    assert service.values_api.updated_body["values"][1][2] == '=GOOGLEFINANCE(B2,"price")'


def test_refresh_quotes_polls_until_metadata_values_are_ready():
    service = FakeService([
        [["US_AAPL", "NASDAQ:AAPL", 185.25, "", ""]],
        [["US_AAPL", "NASDAQ:AAPL", 185.25, "USD", 20]],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="test",
            poll_interval_seconds=0,
            max_poll_attempts=2,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_AAPL", provider_symbol="NASDAQ:AAPL"),
    ])

    assert service.values_api.batch_get_calls == 2
    assert results[0].status == "ok"
    assert results[0].currency == "USD"
    assert results[0].data_delay_minutes == 20


def test_refresh_quotes_marks_formula_error():
    service = FakeService([
        ["US_BAD", "NASDAQ:BAD", "#N/A", "", ""],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="test",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_BAD", provider_symbol="NASDAQ:BAD"),
    ])

    assert results[0].price is None
    assert results[0].status == "formula_error"
    assert results[0].error_message == "#N/A"


def test_refresh_quotes_marks_currency_formula_error():
    service = FakeService([
        ["US_AAPL", "NASDAQ:AAPL", 185.25, "#N/A", 20],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="test",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_AAPL", provider_symbol="NASDAQ:AAPL"),
    ])

    assert results[0].price is None
    assert results[0].currency is None
    assert results[0].status == "formula_error"
    assert results[0].error_message == "#N/A"


def test_refresh_quotes_marks_delay_formula_error():
    service = FakeService([
        ["US_AAPL", "NASDAQ:AAPL", 185.25, "USD", "#VALUE!"],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="test",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_AAPL", provider_symbol="NASDAQ:AAPL"),
    ])

    assert results[0].price is None
    assert results[0].data_delay_minutes is None
    assert results[0].status == "formula_error"
    assert results[0].error_message == "#VALUE!"


def test_refresh_quotes_marks_missing_after_poll():
    service = FakeService([
        ["US_EMPTY", "NASDAQ:EMPTY", "", "", ""],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="test",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    results = client.refresh_quotes_sync([
        QuoteRequest(company_id="US_EMPTY", provider_symbol="NASDAQ:EMPTY"),
    ])

    assert results[0].status == "missing"

def test_refresh_quotes_writes_identifiers_as_sheet_literals():
    service = FakeService([
        ["US_EVIL", "=1+1", "", "", ""],
    ])
    client = GoogleSheetsQuoteClient(
        config=GoogleSheetsConfig(
            enabled=True,
            spreadsheet_id="sheet-123",
            worksheet_name="test",
            poll_interval_seconds=0,
            max_poll_attempts=1,
        ),
        service=service,
    )

    client.refresh_quotes_sync([
        QuoteRequest(company_id="=cmd", provider_symbol="=1+1"),
    ])

    written = service.values_api.updated_body["values"][1]
    assert written[0] == "'=cmd"
    assert written[1] == "'=1+1"
