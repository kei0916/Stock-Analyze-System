"""Phase D 前提: native UPSERT が依存する unique 制約の存在を保証する。

このテストは、設計で index_elements として指定するカラム集合が
実際にテーブル定義に unique 制約として存在することを検証する。
制約が失われた場合、SQLite の ON CONFLICT がターゲットを解決できず
bulk_upsert が実行時エラーになるため、スキーマ変更時のガードとして機能する。
"""
from __future__ import annotations

from sqlalchemy import UniqueConstraint

from stock_analyze_system.models.analysis_target import AnalysisTarget
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.models.watchlist import WatchlistItem


def _unique_column_sets(model) -> list[frozenset[str]]:
    """モデルの unique 制約をカラム名集合のリストで返す (複合/単独とも)"""
    sets: list[frozenset[str]] = []
    for constraint in model.__table__.constraints:
        if isinstance(constraint, UniqueConstraint):
            sets.append(frozenset(c.name for c in constraint.columns))
    for index in model.__table__.indexes:
        if index.unique:
            sets.append(frozenset(c.name for c in index.columns))
    for column in model.__table__.columns:
        if column.unique:
            sets.append(frozenset({column.name}))
    return sets


def test_financial_has_natural_key_unique():
    sets = _unique_column_sets(FinancialData)
    assert frozenset(
        {"company_id", "period_type", "fiscal_year_end", "accounting_standard"}
    ) in sets


def test_valuation_has_natural_key_unique():
    assert frozenset({"company_id", "date"}) in _unique_column_sets(Valuation)


def test_analysis_target_has_company_id_unique():
    assert frozenset({"company_id"}) in _unique_column_sets(AnalysisTarget)


def test_filing_has_accession_no_unique():
    assert frozenset({"accession_no"}) in _unique_column_sets(Filing)


def test_filing_has_doc_id_unique():
    assert frozenset({"doc_id"}) in _unique_column_sets(Filing)


def test_watchlist_item_has_natural_key_unique():
    assert frozenset({"watchlist_id", "company_id"}) in _unique_column_sets(
        WatchlistItem
    )
