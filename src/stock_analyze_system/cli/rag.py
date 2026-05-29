"""RAG分析サブコマンド"""
from __future__ import annotations

import argparse
import sys
import time
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import format_json, format_table
from stock_analyze_system.cli.helpers import add_filing_type_argument
from stock_analyze_system.shared.json_utils import json_dumps_ja
from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer
    from stock_analyze_system.services.rag_service import RagService


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("rag", help="RAG分析")
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help="JSON出力 (root --json も尊重)",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    # rag analyze
    p_analyze = sub.add_parser("analyze", help="定型分析実行")
    p_analyze.add_argument("company_id", help="企業ID (例: US_AAPL)")
    p_analyze.add_argument(
        "--type", dest="type", choices=ANALYSIS_TYPE_NAMES, default=None,
        help="分析タイプ (省略時は全4タイプ実行)",
    )
    p_analyze.add_argument("--quality", action="store_true", help="高精度モデル使用")
    add_filing_type_argument(p_analyze)

    # rag ask
    p_ask = sub.add_parser("ask", help="自由質問")
    p_ask.add_argument("company_id", help="企業ID")
    p_ask.add_argument("question", help="質問文")
    p_ask.add_argument("--quality", action="store_true", help="高精度モデル使用")
    p_ask.add_argument("--model", default=None, help="モデル明示指定")
    add_filing_type_argument(p_ask)

    # rag index
    p_index = sub.add_parser("index", help="インデックス構築")
    p_index.add_argument("company_id", nargs="?", default=None, help="企業ID (省略時は--all必須)")
    p_index.add_argument("--all", action="store_true", dest="all_companies", help="全企業の未構築インデックスを一括構築")
    add_filing_type_argument(p_index)

    # rag status
    p_status = sub.add_parser("status", help="インデックス状態")
    p_status.add_argument("company_id", help="企業ID")

    # rag health
    sub.add_parser("health", help="LLMヘルスチェック")

    # rag show
    p_show = sub.add_parser("show", help="分析結果表示")
    p_show.add_argument("company_id", help="企業ID")
    p_show.add_argument("--filing-id", type=int, default=None, help="ファイリングID")
    add_filing_type_argument(p_show)

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: ServiceContainer) -> int | None:
    from stock_analyze_system.services.filing_section_extractor import (
        ExtractionInputMissingError,
    )
    from stock_analyze_system.services.rag_service import (
        PageIndexDisabledError,
        UnsupportedFilingForExtractorError,
    )

    if services.rag_service is None:
        # defense-in-depth: ADR-004 amendment §B では rag_service は常時 non-None.
        # setup_services が失敗した稀ケースのみ到達.
        print("RAG service is not configured.", file=sys.stderr)
        return 1

    rag = services.rag_service
    action = args.action

    try:
        if action == "health":
            return await _handle_health(rag, args)
        if action == "index":
            return await _handle_index(rag, services, args)
        if action == "analyze":
            return await _handle_analyze(rag, services, args)
        if action == "ask":
            return await _handle_ask(rag, services, args)
        if action == "status":
            return await _handle_status(rag, args)
        if action == "show":
            return await _handle_show(rag, services, args)
    except PageIndexDisabledError as exc:
        # ADR-004 amendment §B: ask/index/status は PageIndex 経路.
        # pageindex.enabled=false 時は明示 exit (Web 側の 503 と等価).
        print(f"PageIndex is disabled: {exc}", file=sys.stderr)
        print(
            "Set pageindex.enabled=true in config/settings.yaml to use this command.",
            file=sys.stderr,
        )
        return 1
    except ExtractionInputMissingError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "Run `stock-analyze filings download <company_id>` to fetch raw HTML.",
            file=sys.stderr,
        )
        return 2
    except UnsupportedFilingForExtractorError as exc:
        print(str(exc), file=sys.stderr)
        return 2


async def _handle_health(rag: RagService, args: argparse.Namespace) -> int | None:
    result = await rag.health_check()
    if args.json:
        print(format_json(result))
    else:
        status = result["status"]
        print(f"LLM Status: {status}")
        print(f"  Model:   {result.get('model', 'N/A')}")
        print(f"  Backend: {result.get('backend', 'N/A')}")
        print(f"  URL:     {result.get('base_url', 'N/A')}")
        if status == "error":
            print(f"  Error:   {result.get('error', '')}", file=sys.stderr)
            return 1


def _log_fetching_if_missing(filing) -> None:
    if filing.storage_path:
        return
    print(
        f"Filing content not present; fetching from {filing.source}...",
        flush=True,
    )


async def _handle_index(
    rag: RagService, services: ServiceContainer, args: argparse.Namespace,
) -> int | None:
    from stock_analyze_system.cli.helpers import require_company, require_latest_filing
    from stock_analyze_system.services.pageindex import count_nodes
    from stock_analyze_system.services.verification_report import save_verification_report

    if getattr(args, "all_companies", False):
        targets = await services.target_service.list_targets()
        for t in targets:
            filing = await services.filing_service.get_latest_filing(t.company_id, args.filing_type)
            if filing is None:
                print(f"  {t.company_id}: no {args.filing_type} filing, skipped")
                continue
            print(f"  Building index for {t.company_id} (filing {filing.id})...")
            _log_fetching_if_missing(filing)
            tree = await rag.build_index(filing)
            node_count = count_nodes(tree)
            print(f"  {t.company_id}: {node_count} nodes")
        return

    if args.company_id is None:
        print("company_id or --all is required.", file=sys.stderr)
        return 1

    company = await require_company(services.company_service, args.company_id)
    filing = await require_latest_filing(
        services.filing_service, company.id, args.filing_type,
    )
    print(f"Building index for {company.id} (filing {filing.id})...")
    _log_fetching_if_missing(filing)
    t0 = time.perf_counter()
    tree = await rag.build_index(filing)
    elapsed = time.perf_counter() - t0
    node_count = count_nodes(tree)
    print(f"Index built: {node_count} nodes in {elapsed:.1f}s")

    # Save verification report if available
    verification_log = tree.get("verification_log")
    if verification_log:
        report_path = save_verification_report(company.id, filing.id, tree, verification_log, node_count)
        print(f"Verification report saved: {report_path}")


async def _handle_analyze(
    rag: RagService, services: ServiceContainer, args: argparse.Namespace,
) -> None:
    from stock_analyze_system.cli.helpers import require_company_and_filing
    company, filing = await require_company_and_filing(services, args.company_id, args.filing_type)

    if not args.json:
        _log_fetching_if_missing(filing)

    t0 = time.perf_counter()
    if args.type:
        if not args.json:
            print(f"Running {args.type} analysis for {company.id}...")
        result = await rag.run_analysis(filing, args.type)
        results = [result]
    else:
        if not args.json:
            print(f"Running full analysis for {company.id} (4 types)...")
        results = await rag.run_full_analysis(filing)
    total_elapsed = time.perf_counter() - t0

    if args.json:
        print(format_json([r.to_dict() for r in results]))
    else:
        for r in results:
            label = r.analysis_type
            t = r.query_result.timing
            print(f"\n{'='*60}")
            print(f"  {label}")
            print(f"{'='*60}")
            print(json_dumps_ja(r.result_json, indent=2))
            print(f"  Sources: pages {r.query_result.source_pages}")
            print(f"  Confidence: {r.query_result.confidence:.0%}")
            print(f"  Timing: {t.format_cli()}")
        print(f"\nTotal elapsed: {total_elapsed:.1f}s")


async def _handle_ask(
    rag: RagService, services: ServiceContainer, args: argparse.Namespace,
) -> None:
    from stock_analyze_system.cli.helpers import require_company_and_filing
    company, filing = await require_company_and_filing(services, args.company_id, args.filing_type)

    if not args.json:
        _log_fetching_if_missing(filing)
        print(f"Querying {company.id}...")
    t0 = time.perf_counter()
    result = await rag.ask_question(filing, args.question)
    elapsed = time.perf_counter() - t0

    if args.json:
        print(format_json(result.to_dict()))
    else:
        t = result.timing
        print(f"\nAnswer:\n{result.answer}")
        print(f"\nSources: pages {result.source_pages}")
        print(f"Sections: {', '.join(result.source_sections)}")
        print(f"Model: {result.model}")
        print(f"Confidence: {result.confidence:.0%}")
        print(f"Timing: {t.format_cli(wall_time=elapsed)}")


async def _handle_status(rag: RagService, args: argparse.Namespace) -> None:
    indices = await rag.get_index_status(args.company_id)
    if args.json:
        print(format_json(indices))
    elif not indices:
        print(f"No indices found for {args.company_id}.")
    else:
        headers = ["Filing ID", "Model", "Pages", "Nodes", "Created"]
        rows = [
            {"Filing ID": i["filing_id"], "Model": i["model_name"],
             "Pages": i["page_count"], "Nodes": i["node_count"],
             "Created": i["created_at"]}
            for i in indices
        ]
        print(format_table(rows, headers))


async def _handle_show(
    rag: RagService, services: ServiceContainer, args: argparse.Namespace,
) -> None:
    from stock_analyze_system.cli.helpers import require_company_and_filing
    company, filing = await require_company_and_filing(services, args.company_id, args.filing_type)

    filing_id = args.filing_id if args.filing_id is not None else filing.id

    analyses = await rag.get_analyses(company.id, filing_id)
    if args.json:
        print(format_json(analyses))
    elif not analyses:
        print(f"No analyses found for {company.id} filing {filing_id}.")
    else:
        for a in analyses:
            print(f"\n{'='*60}")
            print(f"  {a['analysis_type']} (model: {a['model_name']})")
            print(f"  Created: {a['created_at']}")
            print(f"{'='*60}")
            print(json_dumps_ja(a["result_json"], indent=2))
