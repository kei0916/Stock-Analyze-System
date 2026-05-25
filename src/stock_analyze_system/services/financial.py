"""財務データサービス"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stock_analyze_system.models.financial_data import FinancialData

from stock_analyze_system.models.enums import PeriodType
from stock_analyze_system.models.financial_data import FINANCIAL_NATURAL_KEY
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.services import metrics

logger = logging.getLogger(__name__)

_YOY_MIN_DAYS = 330
_YOY_MAX_DAYS = 400


class FinancialService:
    """財務データの取得・指標計算サービス"""

    def __init__(self, financial_repo: FinancialRepository):
        self._repo = financial_repo

    async def upsert_financial_data(
        self, company_id: str, data: dict[str, Any],
    ):
        """財務データを upsert"""
        filters = {"company_id": company_id, **{k: data[k] for k in FINANCIAL_NATURAL_KEY}}
        remainder = {k: v for k, v in data.items() if k not in FINANCIAL_NATURAL_KEY}
        return await self._repo.upsert(filters, remainder)

    async def get_timeseries(
        self, company_id: str, period_type: str = PeriodType.ANNUAL, years: int = 10,
    ):
        return await self._repo.get_timeseries(company_id, period_type, years)

    async def get_latest(self, company_id: str, period_type: str = PeriodType.ANNUAL):
        return await self._repo.get_latest(company_id, period_type)

    def compute_metrics(self, fd: FinancialData) -> dict[str, float | None]:
        """単一期間の全指標を計算"""
        return {
            "operating_margin": metrics.operating_margin(fd.operating_income, fd.revenue),
            "net_margin": metrics.net_margin(fd.net_income, fd.revenue),
            "roe": metrics.roe(fd.net_income, fd.equity),
            "roa": metrics.roa(fd.net_income, fd.total_assets),
            "roic": metrics.roic(
                fd.operating_income, fd.tax_expense, fd.income_before_tax,
                fd.total_debt, fd.equity, fd.cash,
            ),
            "asset_turnover": metrics.asset_turnover(fd.revenue, fd.total_assets),
            "inventory_turnover": metrics.inventory_turnover(fd.cogs, fd.inventory),
            "equity_ratio": metrics.equity_ratio(fd.equity, fd.total_assets),
            "current_ratio": metrics.current_ratio(fd.current_assets, fd.current_liabilities),
            "de_ratio": metrics.de_ratio(fd.total_debt, fd.equity),
            "dividend_payout_ratio": metrics.dividend_payout_ratio(
                fd.dividends_paid, fd.net_income, dps=fd.dps, eps=fd.eps,
            ),
            "total_payout_ratio": metrics.total_payout_ratio(
                fd.dividends_paid, fd.share_repurchases, fd.net_income,
            ),
        }

    def compute_timeseries_metrics(
        self, data_list: list,
    ) -> list[dict[str, Any]]:
        """時系列指標（YoY成長率含む）を計算。data_list は newest-first。"""
        is_quarterly = (
            len(data_list) > 0 and data_list[0].period_type == PeriodType.QUARTERLY
        )

        yoy_map: dict[int, Any] = {}
        if is_quarterly:
            for idx, fd in enumerate(data_list):
                for j in range(idx + 1, len(data_list)):
                    delta = (fd.fiscal_year_end - data_list[j].fiscal_year_end).days
                    if _YOY_MIN_DAYS <= delta <= _YOY_MAX_DAYS:
                        yoy_map[idx] = data_list[j]
                        break

        results: list[dict[str, Any]] = []
        for i, fd in enumerate(data_list):
            entry: dict[str, Any] = {
                "fiscal_year_end": fd.fiscal_year_end,
                "period_type": fd.period_type,
                "revenue": fd.revenue,
                "operating_income": fd.operating_income,
                "net_income": fd.net_income,
                "total_assets": fd.total_assets,
                "equity": fd.equity,
                "eps": fd.eps,
                "fcf": fd.fcf,
                "ebitda": fd.ebitda,
            }
            entry.update(self.compute_metrics(fd))

            if is_quarterly:
                prev = yoy_map.get(i)
            elif i + 1 < len(data_list):
                prev = data_list[i + 1]
            else:
                prev = None

            if prev is not None:
                entry["revenue_growth"] = metrics.revenue_growth(fd.revenue, prev.revenue)
                entry["eps_growth"] = metrics.eps_growth(fd.eps, prev.eps)
                entry["fcf_growth"] = metrics.fcf_growth(fd.fcf, prev.fcf)
                entry["revenue_anomaly"] = metrics.is_anomaly(fd.revenue, prev.revenue)
            else:
                entry["revenue_growth"] = None
                entry["eps_growth"] = None
                entry["fcf_growth"] = None
                entry["revenue_anomaly"] = None

            results.append(entry)
        return results
