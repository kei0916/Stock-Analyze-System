"""Quote refresh CLI commands."""
from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stock_analyze_system.cli.container import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("quotes", help="株価キャッシュ管理")
    sub = parser.add_subparsers(dest="action", required=True)

    sheets = sub.add_parser("sheets", help="Google Sheets quote provider")
    sheets_sub = sheets.add_subparsers(dest="sheets_action", required=True)

    refresh = sheets_sub.add_parser("refresh", help="Google Sheetsから株価を更新")
    refresh.add_argument("--market", choices=["us"], default="us")
    refresh.add_argument("--limit", type=int, default=None)
    refresh.add_argument("--json", action="store_true", dest="json_output")

    status = sheets_sub.add_parser("status", help="株価キャッシュのステータス集計")
    status.add_argument("--market", choices=["us"], default="us")
    status.add_argument("--json", action="store_true", dest="json_output")

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: "ServiceContainer") -> None:
    quote_service = getattr(services, "quote_service", None)
    if quote_service is None:
        print("ERROR: quote_service is unavailable. Check container wiring.", file=sys.stderr)
        sys.exit(1)

    if args.action == "sheets" and args.sheets_action == "refresh":
        result = await quote_service.refresh_google_sheets_quotes(
            market_prefix=_market_prefix(args.market),
            limit=args.limit,
        )
        if args.json_output:
            print(json.dumps(result.__dict__, ensure_ascii=False))
        else:
            statuses = ", ".join(f"{k}={v}" for k, v in result.statuses.items())
            print("Google Sheets quote refresh complete.")
            print(f"  requested: {result.requested}")
            print(f"  submitted: {result.submitted}")
            print(f"  succeeded: {result.succeeded}")
            print(f"  failed:    {result.failed}")
            print(f"  skipped:   {result.skipped}")
            print(f"  statuses:  {statuses}")
        return

    if args.action == "sheets" and args.sheets_action == "status":
        counts = await quote_service.status_counts(provider="google_sheets")
        if args.json_output:
            print(json.dumps(counts, ensure_ascii=False))
        else:
            for status, count in sorted(counts.items()):
                print(f"{status}: {count}")
        return


def _market_prefix(market: str) -> str:
    if market == "us":
        return "US_"
    raise ValueError(f"unsupported market: {market}")
