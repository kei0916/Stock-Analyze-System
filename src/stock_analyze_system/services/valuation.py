"""バリュエーションサービス"""
from __future__ import annotations

import copy
import logging
import statistics
from datetime import date as date_type
from typing import Any, TypedDict

from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.repositories.valuation import ValuationRepository
from stock_analyze_system.services import metrics

logger = logging.getLogger(__name__)

_DEVIATION_METRICS = ("per", "pbr", "ev_ebitda", "psr")


class ValuationRow(TypedDict):
    """compute_valuation_from_financials / compare_valuations の戻り値要素."""

    currency: str | None
    date: date_type | None
    stock_price: float | None
    market_cap: float | None
    per: float | None
    pbr: float | None
    ev_ebitda: float | None
    psr: float | None
    fcf_yield: float | None


class PerRangeDict(TypedDict):
    """compute_per_range の戻り値."""

    high: float | None
    median: float | None
    low: float | None


class ValuationService:
    """バリュエーションの計算・比較サービス"""

    def __init__(self, valuation_repo: ValuationRepository):
        self._repo = valuation_repo

    async def upsert_valuation(
        self, company_id: str, data: dict[str, Any],
    ):
        """(company_id, date) の一意キーでバリュエーション行を upsert する。

        Args:
            company_id: 対象企業 ID。
            data: 少なくとも `date` キーを含む dict。他のキーはそのまま列値へ。

        Returns:
            永続化された `Valuation` モデル。
        """
        filters = {"company_id": company_id, "date": data["date"]}
        remainder = {k: v for k, v in data.items() if k != "date"}
        return await self._repo.upsert(filters, remainder)

    async def get_history(self, company_id: str, years: int = 10):
        """過去 `years` 年分のバリュエーション履歴を古い順で返す。"""
        return await self._repo.get_history(company_id, years)

    async def get_latest(self, company_id: str):
        """最新のバリュエーション 1 件を返す (存在しなければ None)。"""
        return await self._repo.get_latest(company_id)

    async def compare_valuations(
        self, company_ids: list[str],
    ) -> list[ValuationRow]:
        """複数企業の最新バリュエーションを横並び dict 列に整形する。

        Args:
            company_ids: 比較対象の企業 ID リスト。

        Returns:
            `company_id` / `date` / `stock_price` / `market_cap` /
            `per` / `pbr` / `ev_ebitda` / `psr` / `fcf_yield` を含む辞書リスト。
            バリュエーションが未登録の企業は全値 None で埋める。
        """
        _empty = {
            "date": None, "stock_price": None, "market_cap": None,
            "per": None, "pbr": None, "ev_ebitda": None,
            "psr": None, "fcf_yield": None,
        }
        results: list[ValuationRow] = []
        for company_id in company_ids:
            latest = await self._repo.get_latest(company_id)
            if latest is None:
                results.append({"company_id": company_id, **_empty})
            else:
                results.append({
                    "company_id": company_id,
                    "date": latest.date,
                    "stock_price": latest.stock_price,
                    "market_cap": latest.market_cap,
                    "per": latest.per,
                    "pbr": latest.pbr,
                    "ev_ebitda": latest.ev_ebitda,
                    "psr": latest.psr,
                    "fcf_yield": latest.fcf_yield,
                })
        return results

    def compute_per_range(self, valuations: list) -> PerRangeDict:
        """正の PER 値のみを抽出し、`high` / `median` / `low` を返す。

        Args:
            valuations: `get_history` の返値 (`Valuation` モデル列)。

        Returns:
            {"high", "median", "low"} の辞書。有効な PER が 1 件もなければ
            3 値とも None。
        """
        per_values = [v.per for v in valuations if v.per is not None and v.per > 0]
        if not per_values:
            return {"high": None, "median": None, "low": None}
        return {
            "high": max(per_values),
            "median": statistics.median(per_values),
            "low": min(per_values),
        }

    def compute_group_deviation(
        self, comparisons: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """各企業の比較行に PER/PBR/EV-EBITDA/PSR の z-score 偏差列を加える。

        入力は破壊せず、deepcopy した新しいリストに `<metric>_zscore` キーを
        追加して返す。

        Args:
            comparisons: `compare_valuations` が返す辞書リスト。

        Returns:
            各行に 4 メトリクスの z-score (小数点以下 2 桁) を付与した新リスト。
            標本数 <2 または stdev=0 の metric については None を入れる。
        """
        results = copy.deepcopy(comparisons)

        for metric in _DEVIATION_METRICS:
            values = [
                r[metric] for r in results
                if r.get(metric) is not None
            ]
            if len(values) < 2:
                for r in results:
                    r[f"{metric}_zscore"] = None
                continue

            mean = statistics.mean(values)
            stdev = statistics.stdev(values)

            for r in results:
                val = r.get(metric)
                if val is None or stdev == 0:
                    r[f"{metric}_zscore"] = None
                else:
                    r[f"{metric}_zscore"] = round((val - mean) / stdev, 2)

        return results


def compute_valuation_from_financials(
    stock_price: float | None,
    fd: FinancialData,
    currency: str,
    val_date: date_type,
    market_cap: float | None = None,
) -> ValuationRow:
    """株価と財務データから valuation dict を算出する。

    `stock_price` が None の場合は全メトリクスを None とした dict を返す
    (DB 側の upsert を途切れさせないため)。`market_cap` が明示されない場合は
    `fd.shares_outstanding * stock_price` を代替値とする。

    Args:
        stock_price: 株価 (通貨は `currency`)。None 可。
        fd: `FinancialData` レコード。EPS / equity / FCF 等を参照。
        currency: 通貨コード ("USD" / "JPY" 等)。
        val_date: バリュエーション基準日。
        market_cap: 時価総額。None の場合は `fd.shares_outstanding` から推定する。

    Returns:
        `currency` / `date` / `stock_price` / `market_cap` / `per` / `pbr` /
        `ev_ebitda` / `psr` / `fcf_yield` を含む dict。算出不能な項目は None。
    """
    if stock_price is None:
        return {
            "currency": currency,
            "date": val_date,
            "stock_price": None,
            "market_cap": market_cap,
            "per": None,
            "pbr": None,
            "ev_ebitda": None,
            "psr": None,
            "fcf_yield": None,
        }

    per_val = metrics.per(
        stock_price, fd.eps,
        market_cap=market_cap, net_income=fd.net_income,
    )

    if market_cap is not None:
        pbr_val = metrics.pbr(market_cap, fd.equity)
    else:
        shares = fd.shares_outstanding
        bvps = None
        if fd.equity is not None and shares is not None and shares > 0:
            bvps = fd.equity / shares
        pbr_val = stock_price / bvps if bvps is not None and bvps > 0 else None

    effective_mcap = market_cap
    if effective_mcap is None:
        shares = fd.shares_outstanding
        effective_mcap = stock_price * shares if shares is not None else None

    ev_ebitda_val = (
        metrics.ev_ebitda(effective_mcap, fd.total_debt, fd.cash, fd.ebitda)
        if effective_mcap is not None else None
    )
    psr_val = (
        metrics.psr(effective_mcap, fd.revenue)
        if effective_mcap is not None else None
    )
    fcf_yield_val = None
    if fd.fcf is not None and effective_mcap is not None and effective_mcap > 0:
        fcf_yield_val = fd.fcf / effective_mcap

    return {
        "currency": currency,
        "date": val_date,
        "stock_price": stock_price,
        "market_cap": effective_mcap,
        "per": per_val,
        "pbr": pbr_val,
        "ev_ebitda": ev_ebitda_val,
        "psr": psr_val,
        "fcf_yield": fcf_yield_val,
    }
