"""CLIリソース検証ヘルパー"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from stock_analyze_system.cli.container import ServiceContainer, setup_services  # noqa: F401
from stock_analyze_system.models.enums import FilingType


def add_filing_type_argument(parser: argparse.ArgumentParser) -> None:
    """--filing-type 引数を追加する"""
    parser.add_argument(
        "--filing-type", default=FilingType.TEN_K,
        type=FilingType, choices=list(FilingType),
        help="ファイリングタイプ (デフォルト: 10-K)",
    )


async def require_company_and_filing(services: Any, company_id: str, filing_type: Any):
    """企業とファイリングを取得。見つからなければ sys.exit(1)"""
    company = await require_company(services.company_service, company_id)
    filing = await require_latest_filing(services.filing_service, company.id, filing_type)
    return company, filing


async def require_company(company_service: Any, company_id: str) -> Any:
    company = await company_service.get_company(company_id)
    if company is None:
        print(f"Company '{company_id}' not found.", file=sys.stderr)
        sys.exit(1)
    return company


async def require_latest_filing(filing_service: Any, company_id: str, filing_type: str) -> Any:
    filing = await filing_service.get_latest_filing(company_id, filing_type)
    if filing is None:
        print(f"No '{filing_type}' filings found for '{company_id}'.", file=sys.stderr)
        sys.exit(1)
    return filing
