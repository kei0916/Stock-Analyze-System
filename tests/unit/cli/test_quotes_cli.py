import argparse
from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli import quotes
from stock_analyze_system.cli.app import build_parser


def _parse(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    quotes.register_parser(sub)
    return parser.parse_args(["quotes", *argv])


def test_register_parser_accepts_quotes_refresh():
    args = _parse([
        "sheets",
        "refresh",
        "--market",
        "us",
        "--limit",
        "100",
    ])

    assert args.command == "quotes"
    assert args.action == "sheets"
    assert args.sheets_action == "refresh"
    assert args.market == "us"
    assert args.limit == 100


def test_app_parser_registers_quotes_command():
    args = build_parser().parse_args(["quotes", "sheets", "status"])

    assert args.command == "quotes"
    assert args.action == "sheets"
    assert args.sheets_action == "status"


@pytest.mark.asyncio
async def test_handle_refresh_calls_quote_service(capsys):
    result = MagicMock(
        requested=2,
        submitted=2,
        succeeded=1,
        failed=1,
        skipped=0,
        statuses={"formula_error": 1, "ok": 1},
    )
    services = MagicMock()
    services.quote_service.refresh_google_sheets_quotes = AsyncMock(return_value=result)
    args = Namespace(
        action="sheets",
        sheets_action="refresh",
        market="us",
        limit=2,
        json_output=False,
    )

    await quotes.handle(args, services)

    services.quote_service.refresh_google_sheets_quotes.assert_awaited_once_with(
        market_prefix="US_",
        limit=2,
    )
    out = capsys.readouterr().out
    assert "succeeded: 1" in out
    assert "formula_error=1" in out


@pytest.mark.asyncio
async def test_handle_status_prints_counts(capsys):
    services = MagicMock()
    services.quote_service.status_counts = AsyncMock(return_value={"ok": 3})
    args = Namespace(action="sheets", sheets_action="status", market="us", json_output=False)

    await quotes.handle(args, services)

    assert "ok: 3" in capsys.readouterr().out
