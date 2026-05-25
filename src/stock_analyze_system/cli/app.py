"""CLIルートパーサーとディスパッチャ"""
from __future__ import annotations
import argparse
import sys

from stock_analyze_system.cli import (
    company, filings, financial, jobs, quotes, rag, screening, serve, stooq, target,
    valuation, watchlist, worker,
)
from stock_analyze_system.config import load_config
from stock_analyze_system.logging_config import setup_logging
from stock_analyze_system.models.base import create_db_engine, get_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-analyze",
        description="Stock Analyze System — US/JP 株式財務分析CLI",
    )
    parser.add_argument("--json", action="store_true", default=False, help="JSON形式で出力")
    parser.add_argument("--config", type=str, default="config/settings.yaml", help="設定ファイルパス")
    parser.add_argument("--db-path", type=str, default=None, help="データベースパス上書き")

    subparsers = parser.add_subparsers(dest="command")
    company.register_parser(subparsers)
    financial.register_parser(subparsers)
    valuation.register_parser(subparsers)
    filings.register_parser(subparsers)
    jobs.register_parser(subparsers)
    quotes.register_parser(subparsers)
    watchlist.register_parser(subparsers)
    target.register_parser(subparsers)
    screening.register_parser(subparsers)
    stooq.register_parser(subparsers)
    rag.register_parser(subparsers)
    serve.register_parser(subparsers)
    worker.register_parser(subparsers)

    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    config = load_config(args.config)
    if args.db_path:
        config.database.path = args.db_path

    setup_logging(config.logging)

    # Long-running process commands own their lifecycle.
    if args.command in {"serve", "worker"}:
        await args.handler(args, config)
        return

    from stock_analyze_system.cli.helpers import setup_services
    engine = await create_db_engine(config.database.path)
    exit_code = 0
    try:
        async with get_session(engine) as session:
            services = await setup_services(session, config)
            result = await args.handler(args, services)
            if isinstance(result, int):
                exit_code = result
    finally:
        await engine.dispose()
    if exit_code:
        sys.exit(exit_code)
