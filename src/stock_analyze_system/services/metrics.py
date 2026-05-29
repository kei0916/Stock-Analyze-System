"""財務指標の純粋関数群（同期・副作用なし）"""
from __future__ import annotations


def _safe_div(
    numerator: float | None, denominator: float | None,
    *, require_positive_denom: bool = False,
) -> float | None:
    """numerator / denominator を安全に計算。無効な入力は None を返す。"""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    if require_positive_denom and denominator < 0:
        return None
    return numerator / denominator


# ── Profitability ──────────────────────────────────────────────

def operating_margin(operating_income: float | None,
                     revenue: float | None) -> float | None:
    return _safe_div(operating_income, revenue, require_positive_denom=True)


def net_margin(net_income: float | None,
               revenue: float | None) -> float | None:
    return _safe_div(net_income, revenue, require_positive_denom=True)


def roe(net_income: float | None,
        equity: float | None) -> float | None:
    return _safe_div(net_income, equity, require_positive_denom=True)


def roa(net_income: float | None,
        total_assets: float | None) -> float | None:
    return _safe_div(net_income, total_assets, require_positive_denom=True)


def roic(operating_income: float | None,
         tax_expense: float | None,
         income_before_tax: float | None,
         total_debt: float | None,
         equity: float | None,
         cash: float | None) -> float | None:
    if any(v is None for v in (operating_income, tax_expense,
                                income_before_tax, total_debt, equity, cash)):
        return None
    if income_before_tax == 0 or income_before_tax < 0:
        return None
    tax_rate = tax_expense / income_before_tax
    nopat = operating_income * (1.0 - tax_rate)
    invested_capital = total_debt + equity - cash
    if invested_capital <= 0:
        return None
    return nopat / invested_capital


# ── Efficiency ─────────────────────────────────────────────────

def asset_turnover(revenue: float | None,
                   total_assets: float | None) -> float | None:
    return _safe_div(revenue, total_assets, require_positive_denom=True)


def inventory_turnover(cogs: float | None,
                       inventory: float | None) -> float | None:
    return _safe_div(cogs, inventory, require_positive_denom=True)


# ── Stability ──────────────────────────────────────────────────

def equity_ratio(equity: float | None,
                 total_assets: float | None) -> float | None:
    return _safe_div(equity, total_assets, require_positive_denom=True)


def current_ratio(current_assets: float | None,
                  current_liabilities: float | None) -> float | None:
    return _safe_div(current_assets, current_liabilities, require_positive_denom=True)


def de_ratio(total_debt: float | None,
             equity: float | None) -> float | None:
    return _safe_div(total_debt, equity, require_positive_denom=True)


# ── Growth ─────────────────────────────────────────────────────

def revenue_growth(revenue_current: float | None,
                   revenue_previous: float | None) -> float | None:
    if revenue_current is None or revenue_previous is None:
        return None
    if revenue_previous <= 0:
        return None
    return (revenue_current - revenue_previous) / revenue_previous


def eps_growth(eps_current: float | None,
               eps_previous: float | None) -> float | None:
    if eps_current is None or eps_previous is None:
        return None
    if eps_previous == 0 or eps_previous < 0:
        return None
    return (eps_current - eps_previous) / eps_previous


def fcf_growth(fcf_current: float | None,
               fcf_previous: float | None) -> float | None:
    if fcf_current is None or fcf_previous is None:
        return None
    if fcf_previous == 0 or fcf_previous < 0:
        return None
    return (fcf_current - fcf_previous) / fcf_previous


# ── Shareholder Return ─────────────────────────────────────────

def dividend_payout_ratio(dividends_paid: float | None = None,
                          net_income: float | None = None,
                          dps: float | None = None,
                          eps: float | None = None) -> float | None:
    if dividends_paid is not None and net_income is not None and net_income > 0:
        return abs(dividends_paid) / net_income
    if dps is not None and eps is not None and eps > 0:
        return dps / eps
    return None


def total_payout_ratio(dividends_paid: float | None,
                       share_repurchases: float | None,
                       net_income: float | None) -> float | None:
    if any(v is None for v in (dividends_paid, share_repurchases, net_income)):
        return None
    if net_income <= 0:
        return None
    return (abs(dividends_paid) + abs(share_repurchases)) / net_income


# ── Valuation ──────────────────────────────────────────────────

def per(stock_price: float | None = None,
        eps: float | None = None,
        market_cap: float | None = None,
        net_income: float | None = None) -> float | None:
    if stock_price is not None and eps is not None and eps > 0:
        return stock_price / eps
    if market_cap is not None and net_income is not None and net_income > 0:
        return market_cap / net_income
    return None


def pbr(market_cap: float | None,
        equity: float | None) -> float | None:
    return _safe_div(market_cap, equity, require_positive_denom=True)


def ev_ebitda(market_cap: float | None,
              total_debt: float | None,
              cash: float | None,
              ebitda: float | None) -> float | None:
    if any(v is None for v in (market_cap, total_debt, cash, ebitda)):
        return None
    if ebitda <= 0:
        return None
    ev = market_cap + total_debt - cash
    return ev / ebitda


def psr(market_cap: float | None,
        revenue: float | None) -> float | None:
    return _safe_div(market_cap, revenue, require_positive_denom=True)


# ── Utilities ──────────────────────────────────────────────────

def is_anomaly(current: float | None,
               previous: float | None,
               threshold: float = 0.3) -> bool | None:
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    change = abs((current - previous) / previous)
    return change > threshold
