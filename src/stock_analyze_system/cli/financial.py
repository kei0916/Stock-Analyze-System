"""財務データサブコマンド"""
from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import fmt_large, fmt_number, format_json, format_table
from stock_analyze_system.cli.helpers import require_company
from stock_analyze_system.models.enums import PeriodType

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer

_PCT_KEYS = frozenset({
    "operating_margin", "net_margin", "roe", "roa", "roic",
    "equity_ratio", "revenue_growth", "eps_growth", "fcf_growth",
    "dividend_payout_ratio", "total_payout_ratio",
})


def _fmt_metric(key: str, val: float | None) -> str:
    if val is None:
        return "N/A"
    if key in _PCT_KEYS:
        return f"{val * 100:.2f}%"
    return fmt_number(val)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("financial", help="財務データ表示")
    sub = parser.add_subparsers(dest="action")
    sub.required = True

    show_p = sub.add_parser("show", help="財務データ一覧")
    show_p.add_argument("company_id", type=str)
    show_p.add_argument("--period", type=str, default=PeriodType.ANNUAL, choices=list(PeriodType))
    show_p.add_argument("--years", type=int, default=5)

    metrics_p = sub.add_parser("metrics", help="財務指標表示")
    metrics_p.add_argument("company_id", type=str)
    metrics_p.add_argument("--period", type=str, default=PeriodType.ANNUAL, choices=list(PeriodType))
    metrics_p.add_argument("--years", type=int, default=5)

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    if not getattr(args, "action", None):
        print("Usage: stock-analyze financial {show|metrics}")
        sys.exit(1)
    handlers = {"show": _handle_show, "metrics": _handle_metrics}
    await handlers[args.action](args, services)


async def _handle_show(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    await require_company(services.company_service, args.company_id)
    data = await services.financial_service.get_timeseries(
        args.company_id, args.period, years=args.years,
    )
    if not data:
        print(f"No financial data for '{args.company_id}'.")
        return
    rows = [{
        "Period End": str(fd.fiscal_year_end), "Type": fd.period_type,
        "Revenue": fmt_large(fd.revenue), "Op Income": fmt_large(fd.operating_income),
        "Net Income": fmt_large(fd.net_income), "EPS": fmt_number(fd.eps),
        "EBITDA": fmt_large(fd.ebitda),
    } for fd in data]
    if args.json:
        print(format_json(rows))
    else:
        print(f"Financial Data: {args.company_id} ({args.period})")
        print(format_table(rows))


async def _handle_metrics(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
    await require_company(services.company_service, args.company_id)
    ts_data = await services.financial_service.get_timeseries(
        args.company_id, args.period, years=args.years,
    )
    if not ts_data:
        print(f"No financial data for '{args.company_id}'.")
        return
    metrics_list = services.financial_service.compute_timeseries_metrics(ts_data)
    rows = [{
        "Period End": str(m["fiscal_year_end"]),
        "Op Margin": _fmt_metric("operating_margin", m.get("operating_margin")),
        "Net Margin": _fmt_metric("net_margin", m.get("net_margin")),
        "ROE": _fmt_metric("roe", m.get("roe")),
        "Rev Growth": _fmt_metric("revenue_growth", m.get("revenue_growth")),
        "EPS Growth": _fmt_metric("eps_growth", m.get("eps_growth")),
    } for m in metrics_list]
    if args.json:
        print(format_json(metrics_list))
    else:
        print(f"Financial Metrics: {args.company_id} ({args.period})")
        print(format_table(rows))
