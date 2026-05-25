"""screening サブコマンド."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import format_table
from stock_analyze_system.services.screening import (
    FIELD_METADATA,
    SCREENING_NUMERIC_FIELDS,
    FilterClause,
    ScreenSpec,
    SortSpec,
)
from stock_analyze_system.shared.formatters import fmt_large, fmt_number

if TYPE_CHECKING:
    from stock_analyze_system.cli.container import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("screening", help="スクリーニング")
    sub = parser.add_subparsers(dest="action", required=True)

    universe = sub.add_parser("universe", help="universe 操作")
    usub = universe.add_subparsers(dest="universe_action", required=True)
    ur = usub.add_parser("refresh", help="SEC から universe を取り込み")
    ur.add_argument("--source", default="sec", choices=["sec"])

    rf = sub.add_parser("refresh", help="refresh screening cache")
    rf.add_argument("--source", default="yahoo", choices=["yahoo", "sec-google"])
    rf.add_argument("--limit", type=int, default=None)
    rf.add_argument("--stale-hours", type=int, default=24)
    rf.add_argument("--concurrency", type=int, default=8)

    rn = sub.add_parser("run", help="スクリーニング実行")
    rn.add_argument("--gte", action="append", default=[], metavar="FIELD=V")
    rn.add_argument("--lte", action="append", default=[], metavar="FIELD=V")
    rn.add_argument("--between", action="append", default=[], metavar="FIELD=LO,HI")
    rn.add_argument("--eq", action="append", default=[], metavar="FIELD=V")
    rn.add_argument("--in", dest="in_", action="append", default=[], metavar="FIELD=V1,V2,...")
    rn.add_argument("--sort", default=None, metavar="FIELD")
    order_group = rn.add_mutually_exclusive_group()
    order_group.add_argument("--asc", action="store_false", dest="desc", help="昇順")
    order_group.add_argument("--desc", action="store_true", dest="desc", help="降順 (default)")
    rn.set_defaults(desc=True)
    rn.add_argument("--limit", type=int, default=50)
    rn.add_argument("--offset", type=int, default=0)
    rn.add_argument("--include-null", action="store_true")
    rn.add_argument("--json", action="store_true", dest="json_output")

    at = sub.add_parser("add-targets", help="ターゲットに追加")
    at.add_argument("ids", nargs="+", metavar="COMPANY_ID")

    sub.add_parser("fields", help="filter 可能 field 一覧")

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: "ServiceContainer") -> None:
    if args.action == "fields":
        for m in FIELD_METADATA:
            kind = "numeric" if m.field in SCREENING_NUMERIC_FIELDS else "categorical"
            print(f"  {m.field:<22}  [{kind}]  {m.label}  ({m.format})")
        return

    universe_svc = services.screening_universe_service

    if args.action == "refresh" and args.source == "sec-google":
        metrics_svc = services.screening_metrics_service
        if universe_svc is None or metrics_svc is None:
            print(
                "ERROR: screening universe or metrics service is unavailable.",
                file=sys.stderr,
            )
            sys.exit(1)
        universe = await universe_svc.refresh_universe()
        _print_universe_refresh(universe)
        r = await metrics_svc.refresh_from_sec_google(
            limit=args.limit,
            refresh_universe=False,
        )
        print("Screening metrics refresh (source=sec-google)")
        print(f"  eligible: {r.eligible}, succeeded: {r.succeeded}")
        print(f"  skipped (no financials): {r.skipped_no_financials}")
        print(f"  skipped (no quote): {r.skipped_no_quote}")
        print(f"  failed: {r.failed}")
        return

    screen_svc = services.screening_service
    if universe_svc is None or screen_svc is None:
        print("ERROR: screening service is unavailable. Check container wiring.", file=sys.stderr)
        sys.exit(1)

    if args.action == "universe":
        if args.universe_action == "refresh":
            r = await universe_svc.refresh_universe()
            _print_universe_refresh(r)
        return

    if args.action == "refresh":
        universe = await universe_svc.refresh_universe()
        _print_universe_refresh(universe)
        r = await universe_svc.enrich_with_yahoo(
            limit=args.limit,
            stale_hours=args.stale_hours,
            max_concurrency=args.concurrency,
        )
        print(
            f"Enrichment (source=yahoo, eligible={r.eligible}, attempted={r.attempted}, "
            f"concurrency={args.concurrency})"
        )
        print(f"  succeeded: {r.succeeded}, failed: {r.failed}, skipped: {r.skipped}")
        print(f"  elapsed: {r.elapsed_seconds:.1f}s")
        return

    if args.action == "run":
        spec = _build_screen_spec(args)
        try:
            result = await screen_svc.run_screen(spec)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
        if args.json_output:
            print(
                json.dumps(
                    {
                        "items": [
                            {
                                "company_id": it.company_id,
                                "ticker": it.ticker,
                                "name": it.name,
                                "sector": it.sector,
                                "market": it.market,
                                "metrics": it.metrics,
                            }
                            for it in result.items
                        ],
                        "total_matched": result.total_matched,
                        "limit": result.limit,
                        "offset": result.offset,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            _print_screen_table(result)
        return

    if args.action == "add-targets":
        try:
            r = await screen_svc.add_to_targets(args.ids)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
        print(
            f"analysis_targets: requested={r.requested} added={r.added} "
            f"already_present={r.already_present} skipped={r.skipped}"
        )
        return


def _print_universe_refresh(result) -> None:
    print("Universe refresh (source=sec)")
    print(f"  fetched: {result.fetched}")
    print(
        f"  inserted: {result.inserted}, updated: {result.updated}, skipped: {result.skipped}",
    )


def _parse_kv(item: str, *, expect_pair: bool = False) -> tuple[str, list[str]]:
    if "=" not in item:
        raise ValueError(f"expected FIELD=VALUE, got {item!r}")
    field, raw = item.split("=", 1)
    parts = [p for p in raw.split(",") if p != ""] if expect_pair else [raw]
    return field, parts


def _build_screen_spec(args: argparse.Namespace) -> ScreenSpec:
    filters: list[FilterClause] = []
    for s in args.gte:
        f, parts = _parse_kv(s)
        filters.append(FilterClause(f, "gte", float(parts[0])))
    for s in args.lte:
        f, parts = _parse_kv(s)
        filters.append(FilterClause(f, "lte", float(parts[0])))
    for s in args.between:
        f, parts = _parse_kv(s, expect_pair=True)
        if len(parts) != 2:
            raise ValueError(f"--between expects FIELD=LO,HI, got {s!r}")
        filters.append(FilterClause(f, "between", (float(parts[0]), float(parts[1]))))
    for s in args.eq:
        f, parts = _parse_kv(s)
        filters.append(FilterClause(f, "eq", parts[0]))
    for s in args.in_:
        f, parts = _parse_kv(s, expect_pair=True)
        filters.append(FilterClause(f, "in", parts))
    sort = SortSpec(field=args.sort, desc=args.desc) if args.sort else None
    return ScreenSpec(
        filters=filters,
        sort=sort,
        limit=args.limit,
        offset=args.offset,
        include_null=args.include_null,
    )


def _print_screen_table(result) -> None:
    rows = [
        {
            "ticker": it.ticker or "",
            "name": (it.name or "")[:28],
            "sector": (it.sector or "")[:22],
            "market_cap": fmt_large(it.metrics.get("market_cap"), precision=2),
            "PER": fmt_number(it.metrics.get("trailing_per"), precision=1),
            "ROE": fmt_number(it.metrics.get("roe"), precision=2),
        }
        for it in result.items
    ]
    print(format_table(rows, headers=["ticker", "name", "sector", "market_cap", "PER", "ROE"]))
    print(f"matched={result.total_matched}, shown={len(result.items)} (offset={result.offset})")
