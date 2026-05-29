"""Yahoo v7 batch enrich の end-to-end 統合テスト.

実 SQLite + mock Yahoo HTTP で、バッチ取得 → bulk upsert の経路が
ScreeningCache に正しく着地するかを確認する。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.services.screening_universe import (
    ScreeningUniverseService,
)


@pytest.mark.asyncio
async def test_batch_enrich_end_to_end(session):
    """10社のバッチenrich: 1回のHTTP呼び出しでDB stateに正しく反映される"""
    for i in range(10):
        session.add(Company(
            id=f"US_T{i}", ticker=f"T{i}",
            name=f"Test {i}", market="Nasdaq",
            accounting_standard="US-GAAP",
        ))
    await session.commit()

    mock_response = {
        "quoteResponse": {
            "result": [
                {"symbol": f"T{i}", "regularMarketPrice": float(i * 10 + 1)}
                for i in range(10)
            ],
            "error": None,
        }
    }

    with patch(
        "stock_analyze_system.ingestion.yahoo_finance.YfData",
    ) as MockYfData:
        mock_data = MagicMock()
        mock_data.get_raw_json.return_value = mock_response
        MockYfData.return_value = mock_data

        service = ScreeningUniverseService(
            screening_repo=ScreeningRepository(session),
            company_repo=CompanyRepository(session),
            sec_client=MagicMock(),
            yahoo_client=YahooFinanceClient(rate=1000.0),
        )
        result = await service.enrich_with_yahoo()

    assert result.succeeded == 10
    assert result.failed == 0
    assert result.skipped == 0
    # All 10 tickers go in a single batch HTTP call.
    assert mock_data.get_raw_json.call_count == 1

    session.expire_all()
    for i in range(10):
        cache = await session.get(ScreeningCache, f"US_T{i}")
        assert cache is not None
        assert cache.stock_price == float(i * 10 + 1)
