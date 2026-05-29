"""ValuationService のテスト"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock


from stock_analyze_system.services.valuation import ValuationService


def _make_valuation(**kwargs):
    v = MagicMock()
    defaults = {
        "company_id": "US_AAPL", "date": date(2024, 1, 1),
        "stock_price": 185.0, "market_cap": 3e12,
        "per": 28.5, "pbr": 45.0, "ev_ebitda": 22.0,
        "psr": 7.5, "fcf_yield": 0.035,
    }
    defaults.update(kwargs)
    for k, v_val in defaults.items():
        setattr(v, k, v_val)
    return v


class TestUpsertValuation:
    async def test_upsert_valuation(self):
        """upsert_valuation がリポジトリ経由で動作すること"""
        repo = AsyncMock()
        repo.upsert.return_value = MagicMock(id=1)
        svc = ValuationService(repo)
        await svc.upsert_valuation("US_AAPL", {
            "date": date(2024, 1, 1), "currency": "USD",
            "stock_price": 185.0, "per": 28.5,
        })
        repo.upsert.assert_called_once()


class TestCompareValuations:
    async def test_compare_valuations(self):
        """複数企業の最新バリュエーション比較"""
        repo = AsyncMock()
        repo.get_latest.side_effect = [
            _make_valuation(company_id="US_AAPL", per=28.0),
            _make_valuation(company_id="US_MSFT", per=35.0),
        ]
        svc = ValuationService(repo)
        results = await svc.compare_valuations(["US_AAPL", "US_MSFT"])
        assert len(results) == 2
        assert results[0]["company_id"] == "US_AAPL"
        assert results[0]["per"] == 28.0

    async def test_compare_valuations_missing(self):
        """バリュエーションが無い企業は None 値で返ること"""
        repo = AsyncMock()
        repo.get_latest.return_value = None
        svc = ValuationService(repo)
        results = await svc.compare_valuations(["US_NONEXIST"])
        assert len(results) == 1
        assert results[0]["per"] is None


class TestComputePerRange:
    def test_normal(self):
        valuations = [
            _make_valuation(per=20.0),
            _make_valuation(per=25.0),
            _make_valuation(per=30.0),
        ]
        svc = ValuationService(AsyncMock())
        result = svc.compute_per_range(valuations)
        assert result["high"] == 30.0
        assert result["low"] == 20.0
        assert result["median"] == 25.0

    def test_empty(self):
        svc = ValuationService(AsyncMock())
        result = svc.compute_per_range([])
        assert result == {"high": None, "median": None, "low": None}

    def test_none_per_excluded(self):
        valuations = [
            _make_valuation(per=None),
            _make_valuation(per=20.0),
        ]
        svc = ValuationService(AsyncMock())
        result = svc.compute_per_range(valuations)
        assert result["high"] == 20.0


class TestComputeGroupDeviation:
    def test_zscore_calculation(self):
        """z-score が正しく計算されること"""
        comparisons = [
            {"company_id": "A", "per": 20.0, "pbr": 2.0, "ev_ebitda": 10.0, "psr": 3.0},
            {"company_id": "B", "per": 30.0, "pbr": 4.0, "ev_ebitda": 15.0, "psr": 5.0},
            {"company_id": "C", "per": 25.0, "pbr": 3.0, "ev_ebitda": 12.5, "psr": 4.0},
        ]
        svc = ValuationService(AsyncMock())
        results = svc.compute_group_deviation(comparisons)
        # 新発見5修正: 元のリストが変更されていないこと（新しいリストが返される）
        assert results is not comparisons
        assert all("per_zscore" in r for r in results)

    def test_insufficient_data(self):
        """データが2件未満の場合 zscore は None"""
        comparisons = [
            {"company_id": "A", "per": 20.0, "pbr": 2.0, "ev_ebitda": 10.0, "psr": 3.0},
        ]
        svc = ValuationService(AsyncMock())
        results = svc.compute_group_deviation(comparisons)
        assert results[0]["per_zscore"] is None
