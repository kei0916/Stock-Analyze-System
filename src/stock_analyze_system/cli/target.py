"""分析ターゲットサブコマンド"""
from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import format_json, format_table
from stock_analyze_system.exceptions import NotFoundError

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("target", help="分析ターゲット管理")
    sub = parser.add_subparsers(dest="action")
    sub.required = True

    sub.add_parser("list", help="ターゲット一覧")

    add_p = sub.add_parser("add", help="ターゲット追加")
    add_p.add_argument("company_id", type=str)

    rm_p = sub.add_parser("remove", help="ターゲット削除")
    rm_p.add_argument("company_id", type=str)

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    if not getattr(args, "action", None):
        sys.exit(1)

    handlers = {
        "list": _handle_list,
        "add": _handle_add,
        "remove": _handle_remove,
    }
    await handlers[args.action](args, services)


async def _handle_list(args: argparse.Namespace, services: ServiceContainer) -> None:
    targets = await services.target_service.list_targets()
    if not targets:
        print("No analysis targets.")
        return

    rows = [
        {"Company": t.company_id, "Source": t.source, "Criteria": t.criteria or ""}
        for t in targets
    ]
    if args.json:
        print(format_json(rows))
    else:
        print(format_table(rows))


async def _handle_add(args: argparse.Namespace, services: ServiceContainer) -> None:
    await services.target_service.add_target(args.company_id)
    print(f"Added '{args.company_id}' to analysis targets.")


async def _handle_remove(args: argparse.Namespace, services: ServiceContainer) -> None:
    try:
        await services.target_service.remove_target(args.company_id)
    except NotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(f"Removed '{args.company_id}' from analysis targets.")
