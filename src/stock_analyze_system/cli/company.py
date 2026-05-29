"""企業管理サブコマンド"""
from __future__ import annotations
import argparse
import sys
from typing import TYPE_CHECKING
from stock_analyze_system.cli.formatters import format_json, format_table
from stock_analyze_system.cli.helpers import require_company

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer

def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("company", help="企業管理")
    sub = parser.add_subparsers(dest="action")
    sub.required = True

    reg_p = sub.add_parser("register", help="企業を登録")
    reg_p.add_argument("name", type=str, help="企業名")
    reg_p.add_argument("--market", type=str, required=True)
    reg_p.add_argument("--ticker", type=str, default=None)
    reg_p.add_argument("--security-code", type=str, default=None)
    reg_p.add_argument("--sector", type=str, default=None)
    reg_p.add_argument("--cik", type=str, default=None)
    reg_p.add_argument("--edinet-code", type=str, default=None)

    search_p = sub.add_parser("search", help="企業を検索")
    search_p.add_argument("query", type=str)
    search_p.add_argument("--limit", type=int, default=20)

    show_p = sub.add_parser("show", help="企業詳細を表示")
    show_p.add_argument("company_id", type=str)

    parser.set_defaults(handler=handle)

async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    if not getattr(args, "action", None):
        print("Usage: stock-analyze company {register|search|show}")
        sys.exit(1)
    handlers = {"register": _handle_register, "search": _handle_search, "show": _handle_show}
    await handlers[args.action](args, services)

async def _handle_register(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    data = {
        "name": args.name, "market": args.market, "ticker": args.ticker,
        "security_code": args.security_code, "sector": args.sector,
        "cik": args.cik, "edinet_code": args.edinet_code,
    }
    company = await services.company_service.register_company(data)
    if args.json:
        print(format_json({
            "id": company.id, "name": company.name,
            "market": company.market, "ticker": company.ticker,
            "security_code": company.security_code,
        }))
    else:
        print(f"Registered: {company.id} ({company.name})")

async def _handle_search(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    results = await services.company_service.search_companies(args.query, limit=args.limit)
    if not results:
        print(f"No companies found for '{args.query}'.")
        return
    rows = [{"ID": c.id, "Name": c.name, "Ticker": c.ticker, "Market": c.market} for c in results]
    if args.json:
        print(format_json(rows))
    else:
        print(format_table(rows))

async def _handle_show(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    company = await require_company(services.company_service, args.company_id)
    data = {
        "ID": company.id, "Name": company.name, "Ticker": company.ticker,
        "Security Code": company.security_code, "Market": company.market,
        "Sector": company.sector, "Accounting Standard": company.accounting_standard,
        "CIK": company.cik, "EDINET Code": company.edinet_code,
    }
    if args.json:
        print(format_json(data))
    else:
        for key, value in data.items():
            print(f"  {key:>20s}: {value if value is not None else 'N/A'}")
