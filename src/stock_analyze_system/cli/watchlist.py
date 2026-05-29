# src/stock_analyze_system/cli/watchlist.py
"""ウォッチリストサブコマンド"""
from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import format_json, format_table
from stock_analyze_system.exceptions import DuplicateError, NotFoundError

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("watchlist", help="ウォッチリスト管理")
    sub = parser.add_subparsers(dest="action")
    sub.required = True

    create_p = sub.add_parser("create", help="ウォッチリスト作成")
    create_p.add_argument("name", type=str, help="ウォッチリスト名")
    create_p.add_argument("--description", type=str, default=None)

    sub.add_parser("list", help="ウォッチリスト一覧")

    show_p = sub.add_parser("show", help="ウォッチリスト詳細")
    show_p.add_argument("watchlist_id", type=int)

    add_p = sub.add_parser("add", help="銘柄を追加")
    add_p.add_argument("watchlist_id", type=int)
    add_p.add_argument("company_id", type=str)

    rm_p = sub.add_parser("remove", help="銘柄を削除")
    rm_p.add_argument("watchlist_id", type=int)
    rm_p.add_argument("company_id", type=str)

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    """`watchlist` サブコマンドのディスパッチ。"""
    if not getattr(args, "action", None):
        sys.exit(1)

    handlers = {
        "create": _handle_create,
        "list": _handle_list,
        "show": _handle_show,
        "add": _handle_add,
        "remove": _handle_remove,
    }
    await handlers[args.action](args, services)


async def _handle_create(args: argparse.Namespace, services: ServiceContainer) -> None:
    """`watchlist create` — 新規ウォッチリストを作成する。"""
    try:
        wl = await services.watchlist_service.create_watchlist(
            args.name, description=args.description,
        )
    except DuplicateError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(format_json({"id": wl.id, "name": wl.name}))
    else:
        print(f"Created watchlist: {wl.name} (id={wl.id})")


async def _handle_list(args: argparse.Namespace, services: ServiceContainer) -> None:
    """`watchlist list` — 全ウォッチリストを一覧表示する。"""
    watchlists = await services.watchlist_service.list_watchlists()
    if not watchlists:
        print("No watchlists found.")
        return

    rows = [
        {"ID": wl.id, "Name": wl.name, "Description": wl.description or ""}
        for wl in watchlists
    ]
    if args.json:
        print(format_json(rows))
    else:
        print(format_table(rows))


async def _handle_show(args: argparse.Namespace, services: ServiceContainer) -> None:
    """`watchlist show` — 指定 ID のウォッチリスト詳細と銘柄一覧を表示する。"""
    wl = await services.watchlist_service.get_with_items(args.watchlist_id)
    if wl is None:
        print(f"Watchlist {args.watchlist_id} not found.", file=sys.stderr)
        sys.exit(1)

    rows = [
        {"Company": item.company_id, "Status": item.status}
        for item in wl.items
    ]

    if args.json:
        print(format_json({
            "id": wl.id, "name": wl.name,
            "description": wl.description, "items": rows,
        }))
    else:
        print(f"Watchlist: {wl.name} (id={wl.id})")
        if rows:
            print(format_table(rows))
        else:
            print("  (empty)")


async def _handle_add(args: argparse.Namespace, services: ServiceContainer) -> None:
    """`watchlist add` — 指定ウォッチリストに銘柄を追加する。"""
    try:
        await services.watchlist_service.add_item(
            args.watchlist_id, args.company_id,
        )
    except (NotFoundError, DuplicateError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(f"Added '{args.company_id}' to watchlist {args.watchlist_id}.")


async def _handle_remove(args: argparse.Namespace, services: ServiceContainer) -> None:
    """`watchlist remove` — 指定ウォッチリストから銘柄を除外する。"""
    try:
        await services.watchlist_service.remove_item(
            args.watchlist_id, args.company_id,
        )
    except NotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(f"Removed '{args.company_id}' from watchlist {args.watchlist_id}.")
