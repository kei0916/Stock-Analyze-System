"""指定 filing の PageIndex を再構築し DocumentIndexRepository 経由で永続化する.

使用例:
    uv run python scripts/rebuild_index.py \\
        --filing-id 2 --company-id US_AAPL \\
        --pdf data/filings/SEC/US_AAPL/2025/annual/10-K/0000320193-25-000079/converted.pdf

Notes:
    * `asyncio.to_thread` を回避し、`PageIndexService.build_index` を直接呼ぶ。
    * `--dry-run` で DB 書込みをスキップしてビルドのみ実行できる。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path

from stock_analyze_system.config import load_config
from stock_analyze_system.models.base import create_db_engine, get_session
from stock_analyze_system.repositories.document_index import DocumentIndexRepository
from stock_analyze_system.services.llm_client import LlmClient
from stock_analyze_system.services.pageindex import (
    PageIndexService,
    count_nodes,
    extract_page_count,
)
from stock_analyze_system.services.pdf_converter import PdfConverter
from stock_analyze_system.shared.json_utils import json_dumps_ja

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filing-id", type=int, required=True, help="DB上のfiling_id")
    parser.add_argument("--company-id", required=True, help="企業ID (例: US_AAPL)")
    parser.add_argument("--pdf", required=True, help="変換済みPDFパス")
    parser.add_argument("--config", default="config/settings.yaml", help="設定ファイル")
    parser.add_argument("--db", default="data/stock_analyze.db", help="SQLite DBパス")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="ビルドのみ実行し DB 書込みはスキップする",
    )
    return parser.parse_args()


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error("PDF not found: %s", pdf_path)
        return 1

    config = load_config(args.config)
    if not config.pageindex.enabled:
        logger.error("PageIndex integration is disabled in %s", args.config)
        return 1

    llm_client = LlmClient(config.llm)
    model = llm_client.resolve_model(quality=False)
    logger.info("Model: %s, Base URL: %s, PDF: %s", model, llm_client.base_url, pdf_path)

    engine = await create_db_engine(args.db)
    try:
        async with get_session(engine) as session:
            repo = DocumentIndexRepository(session)
            service = PageIndexService(
                doc_index_repo=repo,
                pdf_converter=PdfConverter(),
                llm_client=llm_client,
                config=config.pageindex,
            )

            t0 = time.perf_counter()
            result = await service.build_index(pdf_path)
            elapsed = time.perf_counter() - t0
            tree = result.tree
            nodes = count_nodes(tree)
            pages = extract_page_count(tree)
            logger.info("Build done in %.1fs — nodes=%d, pages=%d", elapsed, nodes, pages)

            if args.dry_run:
                logger.info("--dry-run specified; skipping DB write")
                return 0

            await repo.save_index(
                filing_id=args.filing_id,
                company_id=args.company_id,
                data={
                    "index_json": json_dumps_ja(tree),
                    "model_name": model,
                    "page_count": pages,
                    "node_count": nodes,
                },
            )
            logger.info("Saved index for filing_id=%d (%s)", args.filing_id, args.company_id)
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
