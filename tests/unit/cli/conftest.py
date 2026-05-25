"""CLI テスト共通ヘルパー"""
from unittest.mock import AsyncMock

from stock_analyze_system.cli.container import ServiceContainer


def make_services(**overrides):
    defaults = {
        "company_service": AsyncMock(),
        "financial_service": AsyncMock(),
        "valuation_service": AsyncMock(),
        "filing_service": AsyncMock(),
        "watchlist_service": AsyncMock(),
        "target_service": AsyncMock(),
        "job_service": AsyncMock(),
        "financial_sync": AsyncMock(),
        "filing_sync": AsyncMock(),
        "filing_content_service": AsyncMock(),
    }
    defaults.update(overrides)
    return ServiceContainer(**defaults)
