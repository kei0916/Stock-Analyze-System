"""Runtime type-hint compatibility tests."""

from typing import get_type_hints

from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.services.valuation import compute_valuation_from_financials


def test_compute_valuation_from_financials_type_hints_resolve():
    hints = get_type_hints(compute_valuation_from_financials)

    assert hints["fd"] is FinancialData
