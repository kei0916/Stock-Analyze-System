"""ジョブサブコマンド (sync / daily)"""
from __future__ import annotations

import argparse
from datetime import date as date_type
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import format_json

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer


def _parse_filing_date(value: str) -> date_type:
    """Parse --filing-date as YYYY-MM-DD."""
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise argparse.ArgumentTypeError(
            "--filing-date must be in YYYY-MM-DD format"
        )
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--filing-date must be in YYYY-MM-DD format"
        ) from exc


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """``jobs`` サブコマンドとそのサブコマンド群をパーサに登録する。

    Args:
        subparsers: メイン parser の ``add_subparsers()`` で得たアクションオブジェクト。
    """
    parser = subparsers.add_parser("jobs", help="ジョブ管理")
    sub = parser.add_subparsers(dest="action")
    sub.required = True

    sync_p = sub.add_parser("sync", help="単一企業のデータ同期")
    sync_p.add_argument("company_id", type=str, help="企業ID")

    daily_p = sub.add_parser("daily", help="日次更新バッチ")
    daily_p.add_argument(
        "--market", type=str, choices=["us", "jp"],
        default="us", help="対象市場",
    )
    daily_p.add_argument(
        "--filing-date",
        type=_parse_filing_date,
        default=None,
        help="SEC filingDate to process (YYYY-MM-DD); defaults to current SEC date",
    )

    valuations_p = sub.add_parser(
        "valuations",
        help="分析ターゲットの株価・バリュエーション更新",
    )
    valuations_p.add_argument(
        "--market",
        type=str,
        choices=["all", "us", "jp"],
        default="all",
        help="対象市場",
    )
    valuations_p.add_argument(
        "--quote-provider",
        choices=["yahoo", "google_sheets"],
        default="yahoo",
        help="株価取得元",
    )

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    """``jobs`` サブコマンドのディスパッチ。"""
    if not getattr(args, "action", None):
        sys.exit(1)

    handlers = {
        "sync": _handle_sync,
        "daily": _handle_daily,
        "valuations": _handle_valuations,
    }
    await handlers[args.action](args, services)


async def _handle_sync(args: argparse.Namespace, services: ServiceContainer) -> None:
    """単一企業のデータ同期を実行し結果を表示する。"""
    print(f"Syncing data for '{args.company_id}'...")
    result = await services.job_service.sync_company(args.company_id)

    if args.json:
        print(format_json({
            "company_id": result.company_id,
            "financials_count": result.financials_count,
            "filings_count": result.filings_count,
            "valuations_count": result.valuations_count,
            "errors": result.errors,
        }))
    else:
        print(f"  Company:    {result.company_id}")
        print(f"  Financials: {result.financials_count}")
        print(f"  Filings:    {result.filings_count}")
        print(f"  Valuations: {result.valuations_count}")
        if result.errors:
            print(f"  Errors:     {', '.join(result.errors)}")
        print("Sync complete.")


async def _handle_daily(args: argparse.Namespace, services: ServiceContainer) -> None:
    """日次更新バッチを実行し結果を表示する。"""
    print(f"Running daily update for market: {args.market.upper()}...")
    result = await services.job_service.run_daily_update(
        market=args.market,
        target_date=getattr(args, "filing_date", None),
    )

    if args.json:
        print(format_json({
            "market": result.market,
            "total_companies": result.total_companies,
            "results": [
                {
                    "company_id": r.company_id,
                    "financials_count": r.financials_count,
                    "filings_count": r.filings_count,
                    "valuations_count": r.valuations_count,
                    "errors": r.errors,
                }
                for r in result.results
            ],
        }))
    else:
        print(f"  Total companies: {result.total_companies}")
        success = sum(1 for r in result.results if not r.errors)
        failed = sum(1 for r in result.results if r.errors)
        print(f"  Succeeded: {success}")
        print(f"  Failed:    {failed}")
        if failed:
            for r in result.results:
                if r.errors:
                    print(f"    {r.company_id}: {', '.join(r.errors)}")
        print("Daily update complete.")


async def _handle_valuations(
    args: argparse.Namespace,
    services: ServiceContainer,
) -> None:
    """分析ターゲットの株価・バリュエーション更新を実行し結果を表示する。"""
    print(f"Running target valuation update for market: {args.market.upper()}...")
    result = await services.job_service.run_target_valuation_update(
        market=args.market,
        quote_provider=getattr(args, "quote_provider", "yahoo"),
    )

    if args.json:
        print(format_json({
            "market": result.market,
            "total_companies": result.total_companies,
            "results": [
                {
                    "company_id": r.company_id,
                    "financials_count": r.financials_count,
                    "filings_count": r.filings_count,
                    "valuations_count": r.valuations_count,
                    "errors": r.errors,
                    "skipped_reasons": r.skipped_reasons,
                }
                for r in result.results
            ],
        }))
    else:
        print(f"  Total targets: {result.total_companies}")
        success = sum(
            1 for r in result.results
            if not r.errors and not r.skipped_reasons
        )
        failed = sum(1 for r in result.results if r.errors)
        skipped = sum(1 for r in result.results if r.skipped_reasons)
        print(f"  Succeeded: {success}")
        print(f"  Failed:    {failed}")
        print(f"  Skipped:   {skipped}")
        for r in result.results:
            if r.errors:
                print(f"    {r.company_id}: {', '.join(r.errors)}")
            elif r.skipped_reasons:
                print(f"    {r.company_id}: skipped={', '.join(r.skipped_reasons)}")
            else:
                print(f"    {r.company_id}: valuations={r.valuations_count}")
        print("Target valuation update complete.")
