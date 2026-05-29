"""Google Sheets GOOGLEFINANCE quote provider."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from stock_analyze_system.config import GoogleSheetsConfig


@dataclass(frozen=True)
class QuoteRequest:
    company_id: str
    provider_symbol: str


@dataclass(frozen=True)
class QuoteResult:
    company_id: str
    provider_symbol: str
    price: float | None
    currency: str | None
    data_delay_minutes: int | None
    status: str
    error_message: str | None
    raw_value: str | None
    fetched_at: datetime


class GoogleSheetsQuoteClient:
    def __init__(self, config: GoogleSheetsConfig, service: Any | None = None):
        self._config = config
        self._service = service

    @classmethod
    def from_config(cls, config: GoogleSheetsConfig) -> "GoogleSheetsQuoteClient":
        if not config.enabled:
            raise ValueError("google_sheets.enabled must be true")
        if not config.spreadsheet_id:
            raise ValueError("google_sheets.spreadsheet_id is required")
        service = _build_sheets_service(config)
        return cls(config=config, service=service)

    async def refresh_quotes(self, requests: list[QuoteRequest]) -> list[QuoteResult]:
        return await asyncio.to_thread(self.refresh_quotes_sync, requests)

    def refresh_quotes_sync(self, requests: list[QuoteRequest]) -> list[QuoteResult]:
        if not requests:
            return []
        service = self._require_service()
        self._write_formula_rows(service, requests)
        rows = self._poll_values(service, expected_rows=len(requests))
        rows_by_company = {str(row[0]): row for row in rows if len(row) >= 1}
        return [
            _row_to_result(request, rows_by_company.get(request.company_id, []))
            for request in requests
        ]

    def _require_service(self):
        if self._service is None:
            self._service = _build_sheets_service(self._config)
        return self._service

    def _write_formula_rows(self, service, requests: list[QuoteRequest]) -> None:
        values = [[
            "company_id",
            "provider_symbol",
            "price",
            "currency",
            "delay",
        ]]
        for idx, request in enumerate(requests, start=2):
            values.append([
                _sheet_literal(request.company_id),
                _sheet_literal(request.provider_symbol),
                f'=GOOGLEFINANCE(B{idx},"price")',
                f'=GOOGLEFINANCE(B{idx},"currency")',
                f'=GOOGLEFINANCE(B{idx},"datadelay")',
            ])
        service.spreadsheets().values().update(
            spreadsheetId=self._config.spreadsheet_id,
            range=f"{self._config.worksheet_name}!A1:E{len(values)}",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _poll_values(self, service, expected_rows: int) -> list[list[Any]]:
        range_name = f"{self._config.worksheet_name}!A2:E{expected_rows + 1}"
        rows: list[list[Any]] = []
        for attempt in range(self._config.max_poll_attempts):
            payload = service.spreadsheets().values().batchGet(
                spreadsheetId=self._config.spreadsheet_id,
                ranges=[range_name],
                valueRenderOption="UNFORMATTED_VALUE",
            ).execute()
            rows = payload.get("valueRanges", [{}])[0].get("values", [])
            if _ready_count(rows) >= expected_rows:
                return rows
            if attempt < self._config.max_poll_attempts - 1:
                time.sleep(self._config.poll_interval_seconds)
        return rows


def _sheet_literal(value: str) -> str:
    return "'" + str(value)

def _build_sheets_service(config: GoogleSheetsConfig):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if config.credentials_json:
        info = json.loads(config.credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=scopes,
        )
    elif config.credentials_json_path:
        credentials = service_account.Credentials.from_service_account_file(
            config.credentials_json_path,
            scopes=scopes,
        )
    else:
        raise ValueError(
            "Google Sheets credentials are required through credentials_json or credentials_json_path"
        )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _ready_count(rows: list[list[Any]]) -> int:
    count = 0
    for row in rows:
        if len(row) >= 5 and all(value not in ("", None) for value in row[2:5]):
            count += 1
    return count


def _first_formula_error(values: list[Any]) -> str | None:
    for value in values:
        if isinstance(value, str) and value.startswith("#"):
            return value
    return None


def _row_to_result(request: QuoteRequest, row: list[Any]) -> QuoteResult:
    fetched_at = datetime.now(timezone.utc)
    raw_price = row[2] if len(row) >= 3 else None
    raw_currency = row[3] if len(row) >= 4 else None
    raw_delay = row[4] if len(row) >= 5 else None
    formula_error = _first_formula_error([raw_price, raw_currency, raw_delay])

    if formula_error is not None:
        return QuoteResult(
            request.company_id,
            request.provider_symbol,
            None,
            None,
            None,
            "formula_error",
            formula_error,
            formula_error,
            fetched_at,
        )

    if any(value in ("", None) for value in (raw_price, raw_currency, raw_delay)):
        return QuoteResult(
            request.company_id,
            request.provider_symbol,
            None,
            None,
            None,
            "missing",
            None,
            None,
            fetched_at,
        )
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return QuoteResult(
            request.company_id,
            request.provider_symbol,
            None,
            None,
            None,
            "formula_error",
            str(raw_price),
            str(raw_price),
            fetched_at,
        )

    delay = None
    if raw_delay not in ("", None):
        try:
            delay = int(float(raw_delay))
        except (TypeError, ValueError):
            delay = None

    return QuoteResult(
        request.company_id,
        request.provider_symbol,
        price,
        str(raw_currency) if raw_currency not in ("", None) else None,
        delay,
        "ok",
        None,
        str(raw_price),
        fetched_at,
    )
