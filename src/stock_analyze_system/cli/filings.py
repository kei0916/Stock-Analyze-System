"""ファイリングサブコマンド"""
from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import format_json, format_table
from stock_analyze_system.cli.helpers import require_company

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("filings", help="ファイリング管理")
    sub = parser.add_subparsers(dest="action")
    sub.required = True

    list_p = sub.add_parser("list", help="ファイリング一覧")
    list_p.add_argument("company_id", type=str)

    dl_p = sub.add_parser("download", help="ファイリングをダウンロード")
    dl_p.add_argument("company_id", type=str)

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: ServiceContainer) -> int | None:
    if not getattr(args, "action", None):
        sys.exit(1)
    handlers = {"list": _handle_list, "download": _handle_download}
    return await handlers[args.action](args, services)


async def _handle_list(args: argparse.Namespace, services: ServiceContainer) -> None:
    await require_company(services.company_service, args.company_id)
    filings = await services.filing_service.list_filings(args.company_id)
    if not filings:
        print(f"No filings found for '{args.company_id}'.")
        return
    rows = [
        {
            "ID": f.id,
            "Type": f.filing_type,
            "Source": f.source,
            "FY": f.fiscal_year,
            "Period End": str(f.period_end) if f.period_end else "N/A",
            "Filed At": str(f.filed_at) if f.filed_at else "N/A",
        }
        for f in filings
    ]
    if args.json:
        print(format_json(rows))
    else:
        print(f"Filings: {args.company_id}")
        print(format_table(rows))


async def _handle_download(
    args: argparse.Namespace,
    services: ServiceContainer,
) -> int | None:
    company = await require_company(services.company_service, args.company_id)
    if company.cik:
        synced = await services.filing_sync.update_from_sec(args.company_id, company.cik)
    elif company.edinet_code:
        synced = await services.filing_sync.update_from_edinet(
            args.company_id, company.edinet_code
        )
    else:
        print(
            f"No CIK or EDINET code for '{args.company_id}'. Cannot download filings.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Synced {synced} filing metadata record(s) for '{args.company_id}'.")

    summary = await services.filing_content_service.fetch_for_company(args.company_id)
    print(
        "Fetched content: "
        f"{summary.fetched} new, {summary.skipped} already-present, "
        f"{len(summary.failed)} failed."
    )
    if summary.failed:
        for filing_id, msg in summary.failed:
            print(f"  filing_id={filing_id}: {msg}", file=sys.stderr)
        return 1
    return None
