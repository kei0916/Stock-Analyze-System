"""バリュエーションサブコマンド (show / compare / range / deviation)"""
from __future__ import annotations
import argparse
import sys
from typing import TYPE_CHECKING
from stock_analyze_system.cli.formatters import fmt_large, fmt_number, format_json, format_table
from stock_analyze_system.cli.helpers import require_company

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer
    from stock_analyze_system.models.valuation import Valuation

def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """``valuation`` サブコマンドとそのサブコマンド群をパーサに登録する。

    Args:
        subparsers: メイン parser の ``add_subparsers()`` で得たアクションオブジェクト。
    """
    parser = subparsers.add_parser("valuation", help="バリュエーション表示")
    sub = parser.add_subparsers(dest="action")
    sub.required = True
    show_p = sub.add_parser("show", help="バリュエーション履歴")
    show_p.add_argument("company_id", type=str)
    show_p.add_argument("--years", type=int, default=5)
    compare_p = sub.add_parser("compare", help="複数企業比較")
    compare_p.add_argument("company_ids", nargs="+", type=str)
    range_p = sub.add_parser("range", help="PERレンジ (高値/中央値/安値)")
    range_p.add_argument("company_id", type=str)
    dev_p = sub.add_parser("deviation", help="グループ偏差分析 (z-score)")
    dev_p.add_argument("company_ids", nargs="+", type=str)
    parser.set_defaults(handler=handle)

async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    """``valuation`` サブコマンドのディスパッチ。"""
    if not getattr(args, "action", None):
        sys.exit(1)
    handlers = {
        "show": _handle_show, "compare": _handle_compare,
        "range": _handle_range, "deviation": _handle_deviation,
    }
    await handlers[args.action](args, services)

async def _handle_show(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    """バリュエーション履歴を表示する。"""
    await require_company(services.company_service, args.company_id)
    valuations = await services.valuation_service.get_history(args.company_id, years=args.years)
    if not valuations:
        print(f"No valuation data for '{args.company_id}'.")
        return
    rows = [_valuation_to_row(v) for v in valuations]
    if args.json:
        print(format_json(rows))
    else:
        print(f"Valuation: {args.company_id}")
        print(format_table(rows))

async def _handle_compare(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    """複数企業のバリュエーションを比較表示する。"""
    for cid in args.company_ids:
        await require_company(services.company_service, cid)
    comparisons = await services.valuation_service.compare_valuations(args.company_ids)
    rows = [{
        "Company": r["company_id"], "Date": str(r.get("date", "N/A")),
        "Price": fmt_number(r.get("stock_price")), "PER": fmt_number(r.get("per")),
        "PBR": fmt_number(r.get("pbr")), "EV/EBITDA": fmt_number(r.get("ev_ebitda")),
        "PSR": fmt_number(r.get("psr")),
    } for r in comparisons]
    if args.json:
        print(format_json(comparisons))
    else:
        print("Valuation Comparison (latest)")
        print(format_table(rows))

async def _handle_range(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    """PER の高値・中央値・安値レンジを表示する。"""
    await require_company(services.company_service, args.company_id)
    valuations = await services.valuation_service.get_history(args.company_id, years=10)
    if not valuations:
        print(f"No valuation data for '{args.company_id}'.")
        return
    per_range = services.valuation_service.compute_per_range(valuations)
    if per_range["high"] is None:
        print("No PER data available.")
        return
    if args.json:
        print(format_json({"company_id": args.company_id, **per_range}))
    else:
        print(f"PER Range: {args.company_id}")
        print(f"  High:   {per_range['high']:.2f}")
        print(f"  Median: {per_range['median']:.2f}")
        print(f"  Low:    {per_range['low']:.2f}")

async def _handle_deviation(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    """グループ内の z-score 偏差分析を表示する。"""
    if len(args.company_ids) < 2:
        print("At least 2 companies required for deviation analysis.", file=sys.stderr)
        sys.exit(1)
    for cid in args.company_ids:
        await require_company(services.company_service, cid)
    comparisons = await services.valuation_service.compare_valuations(args.company_ids)
    results = services.valuation_service.compute_group_deviation(comparisons)
    rows = []
    for r in results:
        row = {"Company": r["company_id"]}
        for metric in ("per", "pbr", "ev_ebitda", "psr"):
            val = r.get(metric)
            z = r.get(f"{metric}_zscore")
            val_str = fmt_number(val)
            z_str = f"({z:+.2f}σ)" if z is not None else ""
            row[metric.upper().replace("_", "/")] = f"{val_str} {z_str}".strip()
        rows.append(row)
    if args.json:
        print(format_json(results))
    else:
        print(f"Valuation Deviation (n={len(args.company_ids)})")
        print(format_table(rows))

def _valuation_to_row(v: Valuation) -> dict:
    """Valuation オブジェクトをテーブル表示用 dict に変換する。"""
    return {
        "Date": str(v.date), "Price": fmt_number(v.stock_price),
        "Market Cap": fmt_large(v.market_cap), "PER": fmt_number(v.per),
        "PBR": fmt_number(v.pbr), "EV/EBITDA": fmt_number(v.ev_ebitda),
        "PSR": fmt_number(v.psr), "FCF Yield": fmt_number(v.fcf_yield),
    }
