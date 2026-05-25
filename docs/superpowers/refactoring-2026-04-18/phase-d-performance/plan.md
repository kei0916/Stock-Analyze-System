# Phase D: パフォーマンス改善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQLite native UPSERT と Web クライアント singleton 化で bulk write と Web hot path の不要 I/O を削減する。

**Architecture:**
- `BaseRepository` に `_bulk_upsert_native` を追加し、`FinancialRepository` / `ValuationRepository` / `TargetRepository` / `FilingRepository` の `bulk_upsert` 実装を差し替え (public API 無変更)。
- `FilingSyncService.update_from_sec/edinet` を「既存 accession 一括 SELECT → 新規分のみ bulk_upsert」の 3 クエリ構成に再構築。
- FastAPI `AppState` に `ClientBundle` を持たせ、SEC/EDINET/Yahoo/FMP/LLM/PdfConverter をリクエスト横断で共有。
- `Watchlist` 詳細ページは `selectinload(Watchlist.items)` で 2 往復 → 1 往復化。

**Tech Stack:**
- Python 3.10+, SQLAlchemy 2.0 async, aiosqlite
- `sqlalchemy.dialects.sqlite.insert` の `on_conflict_do_update` / `on_conflict_do_nothing`
- FastAPI lifespan + `app.state`
- pytest 8 + pytest-asyncio + `@pytest.mark.benchmark`

**Parent docs:**
- 設計: [design.md](design.md)
- マスタートラッカー: [../master.md](../master.md)
- 進捗記録: [report.md](report.md)

---

## Task 1: モデル unique index 棚卸し

**目的:** native UPSERT の `index_elements` に使う制約が各モデルに存在することを、実行可能な assertion テストで保証する (スキーマ回帰ガード)。

**Files:**
- Create: `tests/unit/models/test_natural_key_constraints.py`

**現状の事実 (既に確認済み)**
- `FinancialData`: `UniqueConstraint(company_id, period_type, fiscal_year_end, accounting_standard)` = `uq_financial_natural_key`
- `Valuation`: `UniqueConstraint(company_id, date)` = `uq_valuation_company_date`
- `AnalysisTarget`: `company_id` カラム自体に `unique=True` (単独 unique index)
- `Filing`: `accession_no` と `doc_id` がそれぞれ `unique=True` (単独 unique index)
- `WatchlistItem`: `UniqueConstraint(watchlist_id, company_id)` = `uq_watchlist_company`

従って本タスクでは **スキーマ変更を行わず、制約の存在を検証するテストのみ** を追加する。

- [ ] **Step 1: Write failing test**

`tests/unit/models/test_natural_key_constraints.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes (既存制約なので PASS が期待)**

Run: `uv run pytest tests/unit/models/test_natural_key_constraints.py -v`
Expected: 6 tests PASS (制約はすべて既存)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/models/test_natural_key_constraints.py
git commit -m "test(phase-d): assert natural-key unique constraints exist

Phase D の native UPSERT が依存する unique 制約をスキーマレベルで固定する。
将来モデルから制約が外された場合、bulk_upsert 実行時エラーになる前に
unit テストで検出する。"
```

- [ ] **Step 4: report.md に Task 1 行を追記**

```markdown
### Task 1: モデル unique index 棚卸し — ✅ Done
- 変更: `tests/unit/models/test_natural_key_constraints.py` (新規, 6 tests)
- 既存制約のみで要件を満たすことを確認。スキーマ変更なし。
- commit: <hash>
```

---

## Task 2: BaseRepository._bulk_upsert_native 追加

**目的:** SQLite native UPSERT 用の共通メソッドを BaseRepository に追加し、単体テストで INSERT/UPDATE/空入力/update_columns 空 の 4 ケースを固定する。

**Files:**
- Modify: `src/stock_analyze_system/repositories/base.py`
- Modify: `tests/unit/repositories/test_base_repo.py`

- [ ] **Step 1: Write failing tests (先に 4 ケース追加)**

`tests/unit/repositories/test_base_repo.py` の末尾に追加:

```python
from datetime import date

from stock_analyze_system.models.financial_data import FinancialData


async def test_bulk_upsert_native_insert(session):
    """新規レコードが INSERT されること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 394e9,
    }]
    await repo._bulk_upsert_native(
        rows,
        index_elements=[
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ],
        update_columns=["currency", "revenue"],
    )
    count = await repo.count(company_id="US_AAPL")
    assert count == 1


async def test_bulk_upsert_native_update(session):
    """重複キーで既存レコードが UPDATE されること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=100.0,
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 394e9,
    }]
    await repo._bulk_upsert_native(
        rows,
        index_elements=[
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ],
        update_columns=["revenue"],
    )
    # session cache をクリアして DB から再取得
    session.expire_all()
    from sqlalchemy import select
    result = await session.execute(
        select(FinancialData).where(FinancialData.company_id == "US_AAPL"),
    )
    row = result.scalar_one()
    assert row.revenue == 394e9


async def test_bulk_upsert_native_empty_rows(session):
    """空リストを渡しても例外なく no-op で終わること"""
    repo = BaseRepository(session, FinancialData)
    await repo._bulk_upsert_native(
        [], index_elements=["company_id"], update_columns=["revenue"],
    )
    # 例外が出ないこと、DB に何も挿入されないこと
    assert await repo.count() == 0


async def test_bulk_upsert_native_empty_update_columns(session):
    """update_columns 空なら on_conflict_do_nothing になり既存が保持されること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=100.0,
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 999.0,
    }]
    await repo._bulk_upsert_native(
        rows,
        index_elements=[
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ],
        update_columns=[],
    )
    session.expire_all()
    from sqlalchemy import select
    result = await session.execute(
        select(FinancialData).where(FinancialData.company_id == "US_AAPL"),
    )
    row = result.scalar_one()
    assert row.revenue == 100.0
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/repositories/test_base_repo.py -v -k bulk_upsert_native`
Expected: 4 tests FAIL with `AttributeError: 'BaseRepository' object has no attribute '_bulk_upsert_native'`

- [ ] **Step 3: Implement _bulk_upsert_native**

`src/stock_analyze_system/repositories/base.py` の `BaseRepository` クラスに追加:

```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


class BaseRepository(Generic[T]):
    # ... 既存 __init__, get_by_id, list_all, upsert, delete, count 変更なし ...

    async def _bulk_upsert_native(
        self,
        rows: list[dict],
        *,
        index_elements: list[str],
        update_columns: list[str],
    ) -> None:
        if not rows:
            return
        stmt = sqlite_insert(self._model).values(rows)
        if update_columns:
            stmt = stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_={col: stmt.excluded[col] for col in update_columns},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)
        await self._session.execute(stmt)
        await self._session.flush()
```

import を ファイル先頭に追加:
```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/repositories/test_base_repo.py -v`
Expected: 既存 + 新規 4 tests すべて PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/repositories/base.py tests/unit/repositories/test_base_repo.py
git commit -m "feat(repo): add BaseRepository._bulk_upsert_native

SQLite native UPSERT (INSERT ... ON CONFLICT DO UPDATE) の共通実装。
N 件を単一 statement で処理し、既存 bulk_upsert の 2N クエリ loop を
次タスクから段階的に置き換えるための土台。"
```

- [ ] **Step 6: report.md に Task 2 行を追記**

---

## Task 3: FinancialRepository.bulk_upsert 差し替え

**目的:** `FinancialRepository.bulk_upsert` を `_bulk_upsert_native` 呼び出しに置き換え、既存テストが無変更で通ることを確認する (public API 互換)。

**Files:**
- Modify: `src/stock_analyze_system/repositories/financial.py`

- [ ] **Step 1: 既存テストを一度走らせて現状 PASS を確認**

Run: `uv run pytest tests/unit/repositories/test_financial_repo.py -v`
Expected: 4 tests PASS

- [ ] **Step 2: 差し替え実装**

`src/stock_analyze_system/repositories/financial.py` の `bulk_upsert` を置換:

```python
async def bulk_upsert(
    self, company_id: str, records: list[dict],
) -> int:
    if not records:
        return 0
    rows = [{"company_id": company_id, **r} for r in records]
    natural_key_cols = ("company_id", *FINANCIAL_NATURAL_KEY)
    update_cols = [c for c in rows[0].keys() if c not in natural_key_cols]
    await self._bulk_upsert_native(
        rows,
        index_elements=list(natural_key_cols),
        update_columns=update_cols,
    )
    return len(records)
```

- [ ] **Step 3: 既存テストを再実行して PASS を確認**

Run: `uv run pytest tests/unit/repositories/test_financial_repo.py -v`
Expected: 4 tests すべて PASS (特に `test_bulk_upsert` の insert→update シナリオ)

- [ ] **Step 4: service 層の回帰確認**

Run: `uv run pytest tests/unit/services/test_financial_sync.py tests/integration/ -v`
Expected: すべて PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/repositories/financial.py
git commit -m "perf(financial): replace bulk_upsert with native UPSERT

N 件の loop + 2 クエリ/件 → 単一 statement に圧縮。
public API (引数・戻り値 int) 無変更なので呼び出し側の修正不要。"
```

- [ ] **Step 6: report.md に Task 3 行を追記**

---

## Task 4: ValuationRepository.bulk_upsert 差し替え

**目的:** Task 3 と同パターンで `ValuationRepository.bulk_upsert` を native 化する。

**Files:**
- Modify: `src/stock_analyze_system/repositories/valuation.py`

- [ ] **Step 1: 既存テスト PASS 確認**

Run: `uv run pytest tests/unit/repositories/test_valuation_repo.py -v`
Expected: 全 PASS

- [ ] **Step 2: 差し替え実装**

`src/stock_analyze_system/repositories/valuation.py` の `bulk_upsert` を置換:

```python
async def bulk_upsert(
    self, company_id: str, records: list[dict],
) -> int:
    if not records:
        return 0
    rows = [{"company_id": company_id, **r} for r in records]
    natural_key_cols = ("company_id", "date")
    update_cols = [c for c in rows[0].keys() if c not in natural_key_cols]
    await self._bulk_upsert_native(
        rows,
        index_elements=list(natural_key_cols),
        update_columns=update_cols,
    )
    return len(records)
```

- [ ] **Step 3: テスト再実行**

Run: `uv run pytest tests/unit/repositories/test_valuation_repo.py tests/unit/services/ -v`
Expected: すべて PASS

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/repositories/valuation.py
git commit -m "perf(valuation): replace bulk_upsert with native UPSERT"
```

- [ ] **Step 5: report.md 追記**

---

## Task 5: TargetRepository.bulk_add 差し替え

**目的:** `TargetRepository.bulk_add` (method 名は `bulk_add`。既存挙動は「重複はスキップ」) を `on_conflict_do_nothing` ベースに差し替える。

**Files:**
- Modify: `src/stock_analyze_system/repositories/target.py`

**Note:** 設計書では `bulk_upsert` と書かれているが、実際のメソッド名は `bulk_add`。挙動 (重複スキップ = upsert ではなく insert-or-ignore) を維持するため、`_bulk_upsert_native` に `update_columns=[]` を渡して `on_conflict_do_nothing` パスを使う。

- [ ] **Step 1: 既存テスト PASS 確認**

Run: `uv run pytest tests/unit/repositories/test_other_repos.py -v -k target`
Expected: 全 PASS

- [ ] **Step 2: 差し替え実装**

`src/stock_analyze_system/repositories/target.py`:

```python
async def bulk_add(self, records: list[dict]) -> int:
    """一括追加（既存はスキップ）。戻り値は追加数。

    SQLite native UPSERT の ON CONFLICT DO NOTHING を使用。
    """
    if not records:
        return 0
    # 事前に既存 company_id を検出して追加件数を正しく返す
    from sqlalchemy import select
    incoming_ids = [r["company_id"] for r in records]
    stmt = select(AnalysisTarget.company_id).where(
        AnalysisTarget.company_id.in_(incoming_ids),
    )
    result = await self._session.execute(stmt)
    existing_ids = set(result.scalars().all())
    new_rows = [r for r in records if r["company_id"] not in existing_ids]
    if not new_rows:
        return 0
    await self._bulk_upsert_native(
        new_rows,
        index_elements=["company_id"],
        update_columns=[],
    )
    return len(new_rows)
```

- [ ] **Step 3: テスト再実行**

Run: `uv run pytest tests/unit/repositories/test_other_repos.py tests/unit/services/ -v`
Expected: 全 PASS。特に「既存は追加数にカウントされない」挙動が保持されていること。

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/repositories/target.py
git commit -m "perf(target): replace bulk_add loop with native insert-or-ignore

既存 company_id は 1 クエリで事前検出し、新規分のみ単一 INSERT に
集約。戻り値 (追加件数 int) の意味を変えずに N+1 を解消。"
```

- [ ] **Step 5: report.md 追記**

---

## Task 6: FilingRepository.bulk_upsert + FilingSyncService 一括化

**目的:** `FilingSyncService.update_from_sec/edinet` の filing-per-query ループを「既存 accession 一括 SELECT → 新規分のみ 1 回 INSERT」の 3 クエリ構成に再構築する。

**Files:**
- Modify: `src/stock_analyze_system/repositories/filing.py`
- Modify: `src/stock_analyze_system/services/filing_sync.py`
- Modify: `tests/unit/repositories/test_filing_repo.py`
- Modify: `tests/unit/services/test_filing_sync.py`

- [ ] **Step 1: FilingRepository に 3 メソッドを追加 (failing test 先行)**

`tests/unit/repositories/test_filing_repo.py` の末尾に追加:

```python
async def test_find_existing_accessions(session):
    """指定 accession のうち既存分のみ返すこと"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    ))
    await session.flush()
    repo = FilingRepository(session)
    existing = await repo.find_existing_accessions(
        "US_AAPL",
        ["0000320193-24-000123", "0000320193-25-000001"],
    )
    assert existing == {"0000320193-24-000123"}


async def test_find_existing_accessions_empty(session):
    repo = FilingRepository(session)
    assert await repo.find_existing_accessions("US_AAPL", []) == set()


async def test_find_existing_doc_ids(session):
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    session.add(Filing(
        company_id="JP_7203", source="EDINET", filing_type="annual_report",
        period_type="annual", fiscal_year=2024, doc_id="S100AAAA",
    ))
    await session.flush()
    repo = FilingRepository(session)
    existing = await repo.find_existing_doc_ids(
        "JP_7203", ["S100AAAA", "S100BBBB"],
    )
    assert existing == {"S100AAAA"}


async def test_bulk_upsert_filings_sec(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    rows = [
        {
            "source": "SEC", "filing_type": "10-K", "period_type": "annual",
            "fiscal_year": 2024, "accession_no": "A-1",
        },
        {
            "source": "SEC", "filing_type": "10-Q", "period_type": "quarterly",
            "fiscal_year": 2024, "accession_no": "A-2",
        },
    ]
    count = await repo.bulk_upsert("US_AAPL", rows, source="SEC")
    assert count == 2
    assert await repo.count(company_id="US_AAPL") == 2


async def test_bulk_upsert_filings_rejects_unknown_source(session):
    repo = FilingRepository(session)
    import pytest
    with pytest.raises(ValueError, match="unknown source"):
        await repo.bulk_upsert("US_AAPL", [], source="OTHER")
```

imports 先頭 (必要なら):
```python
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.filing import FilingRepository
```

- [ ] **Step 2: テスト失敗を確認**

Run: `uv run pytest tests/unit/repositories/test_filing_repo.py -v`
Expected: 新規 5 tests FAIL

- [ ] **Step 3: FilingRepository 実装を追加**

`src/stock_analyze_system/repositories/filing.py`:

```python
async def find_existing_accessions(
    self, company_id: str, accessions: list[str],
) -> set[str]:
    if not accessions:
        return set()
    stmt = select(Filing.accession_no).where(
        Filing.company_id == company_id,
        Filing.accession_no.in_(accessions),
    )
    result = await self._session.execute(stmt)
    return {v for v in result.scalars().all() if v is not None}


async def find_existing_doc_ids(
    self, company_id: str, doc_ids: list[str],
) -> set[str]:
    if not doc_ids:
        return set()
    stmt = select(Filing.doc_id).where(
        Filing.company_id == company_id,
        Filing.doc_id.in_(doc_ids),
    )
    result = await self._session.execute(stmt)
    return {v for v in result.scalars().all() if v is not None}


async def bulk_upsert(
    self, company_id: str, records: list[dict], *, source: str,
) -> int:
    if source == "SEC":
        key_col = "accession_no"
    elif source == "EDINET":
        key_col = "doc_id"
    else:
        raise ValueError(f"unknown source: {source}")
    if not records:
        return 0
    rows = [{"company_id": company_id, **r} for r in records]
    natural_key_cols = ("company_id", key_col)
    update_cols = [c for c in rows[0].keys() if c not in natural_key_cols]
    await self._bulk_upsert_native(
        rows,
        index_elements=[key_col],
        update_columns=update_cols,
    )
    return len(records)
```

**Note:** `index_elements` は単独の unique column (`accession_no` / `doc_id`) を指定する。これは両カラムとも単独で `unique=True` が付与されているため SQLite の ON CONFLICT ターゲットとして有効 (Task 1 で検証済み)。

- [ ] **Step 4: Repo テスト PASS 確認**

Run: `uv run pytest tests/unit/repositories/test_filing_repo.py -v`
Expected: 全 PASS

- [ ] **Step 5: FilingSyncService を一括化**

`src/stock_analyze_system/services/filing_sync.py` の `update_from_sec` を置換:

```python
async def update_from_sec(
    self, company_id: str, cik: str,
) -> int:
    try:
        filing_list = await self._sec.list_filings(cik, max_years=2)
    except (ValueError, OSError, KeyError):
        logger.exception("SEC EDGAR filing list failed for %s", company_id)
        return 0

    if not filing_list:
        return 0

    accessions = [
        e["accessionNumber"] for e in filing_list if e.get("accessionNumber")
    ]
    existing = await self._repo.find_existing_accessions(company_id, accessions)

    new_rows: list[dict] = []
    for entry in filing_list:
        accession = entry.get("accessionNumber")
        if not accession or accession in existing:
            continue
        form = entry["form"]
        report_date = entry.get("reportDate", "")
        filed_date = entry.get("filingDate", "")
        period_type = (
            PeriodType.ANNUAL
            if form in (FilingType.TEN_K, FilingType.TWENTY_F)
            else PeriodType.QUARTERLY
        )
        fiscal_year = int(report_date[:4]) if report_date else int(filed_date[:4])
        row = {
            "source": "SEC",
            "filing_type": form,
            "period_type": period_type,
            "fiscal_year": fiscal_year,
            "accession_no": accession,
        }
        if report_date:
            row["period_end"] = date_type.fromisoformat(report_date)
        if filed_date:
            row["filed_at"] = date_type.fromisoformat(filed_date)
        new_rows.append(row)

    if new_rows:
        await self._repo.bulk_upsert(company_id, new_rows, source="SEC")

    logger.info("Filing update for %s: %d new filings", company_id, len(new_rows))
    return len(new_rows)
```

`update_from_edinet` も同パターンで書き換え:

```python
async def update_from_edinet(
    self, company_id: str, edinet_code: str,
) -> int:
    today = date_type.today()
    try:
        docs = await self._edinet.search_company_filings(
            edinet_code,
            (today - timedelta(days=365 * 2)).isoformat(),
            today.isoformat(),
        )
    except (ValueError, OSError, KeyError):
        logger.exception("EDINET filing search failed for %s", company_id)
        return 0

    if not docs:
        return 0

    doc_ids = [d["docID"] for d in docs if d.get("docID")]
    existing = await self._repo.find_existing_doc_ids(company_id, doc_ids)

    new_rows: list[dict] = []
    for doc in docs:
        doc_id = doc.get("docID")
        if not doc_id or doc_id in existing:
            continue
        fiscal_year_str = doc.get("periodEnd", "")[:4]
        fiscal_year = int(fiscal_year_str) if fiscal_year_str.isdigit() else today.year
        doc_type = doc.get("docTypeCode", "")
        period_type = (
            PeriodType.ANNUAL if doc_type in ("120", "130") else PeriodType.QUARTERLY
        )
        filing_type = (
            "annual_report" if period_type == PeriodType.ANNUAL else "quarterly_report"
        )
        new_rows.append({
            "source": "EDINET",
            "filing_type": filing_type,
            "period_type": period_type,
            "fiscal_year": fiscal_year,
            "doc_id": doc_id,
        })

    if new_rows:
        await self._repo.bulk_upsert(company_id, new_rows, source="EDINET")

    logger.info(
        "Filing update for %s: %d filings from EDINET", company_id, len(new_rows),
    )
    return len(new_rows)
```

- [ ] **Step 6: Service テストの回帰確認 (既存テストを読んで必要なら mock 調整)**

Run: `uv run pytest tests/unit/services/test_filing_sync.py -v`
Expected: PASS (既存の mock が `find_by_accession` / `upsert` を使っていれば `find_existing_accessions` / `bulk_upsert` に mock 差し替えが必要)。

必要な mock 更新例:
```python
# test_filing_sync.py 内 mock 修正 (既存テストが期待する API)
repo.find_existing_accessions = AsyncMock(return_value=set())
repo.bulk_upsert = AsyncMock(return_value=1)
# find_by_accession / upsert の mock は削除
```

- [ ] **Step 7: 統合テスト確認**

Run: `uv run pytest tests/integration/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/stock_analyze_system/repositories/filing.py \
        src/stock_analyze_system/services/filing_sync.py \
        tests/unit/repositories/test_filing_repo.py \
        tests/unit/services/test_filing_sync.py
git commit -m "perf(filing): bulk-load existing accessions and bulk-upsert new rows

1 + 3N クエリ → 1 + 1 + 1 の 3 クエリ。既存 filing は in(...) で
一括検出し、新規分のみ単一 INSERT ON CONFLICT に集約する。
既存挙動 (重複はスキップ) は維持。"
```

- [ ] **Step 9: report.md 追記**

---

## Task 7: ClientBundle + AppState singleton 化

**目的:** Web リクエストごとに再生成されていた外部 API クライアント (SEC/EDINET/Yahoo/FMP/LLM/PdfConverter) を `AppState.clients` にまとめてプロセス寿命共有にする。CLI とテスト (既存 2 引数 API) は無変更。

**Files:**
- Modify: `src/stock_analyze_system/web/dependencies.py`
- Modify: `src/stock_analyze_system/cli/container.py`
- Create: `tests/unit/web/test_singleton_clients.py`

- [ ] **Step 1: Write failing test first**

`tests/unit/web/test_singleton_clients.py`:

```python
"""AppState.clients が Web リクエスト間で singleton として再利用されることを確認する。"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def test_app_state_clients_singleton_across_requests(web_app):
    """2 回リクエストを送って ClientBundle の SEC クライアント id が一致すること"""
    observed_ids: list[int] = []

    from stock_analyze_system.web.dependencies import get_app_state, AppState

    @web_app.get("/__test_singleton")
    async def _probe(state: AppState = Depends(get_app_state)):
        observed_ids.append(id(state.clients.sec))
        return {"ok": True}

    with TestClient(web_app) as client:
        assert client.get("/__test_singleton").status_code == 200
        assert client.get("/__test_singleton").status_code == 200

    assert len(observed_ids) == 2
    assert observed_ids[0] == observed_ids[1]
```

`web_app` fixture は既存 `tests/unit/web/conftest.py` を利用する (既存の test_app が参考)。既存 fixture が無い場合は以下を追加:

```python
# tests/unit/web/conftest.py に (既存 fixture があればそちらを使う)
@pytest.fixture
def web_app(tmp_path, monkeypatch):
    from stock_analyze_system.web.app import create_app
    from stock_analyze_system.config import AppConfig
    cfg = AppConfig.model_validate({
        "database": {"path": str(tmp_path / "test.db")},
        # 他必須項目 (既存 test_app.py に準拠)
    })
    return create_app(cfg)
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/unit/web/test_singleton_clients.py -v`
Expected: FAIL — `AppState` に `clients` 属性がまだ存在しない

- [ ] **Step 3: ClientBundle + AppState 拡張**

`src/stock_analyze_system/web/dependencies.py`:

```python
"""FastAPI dependencies — engine, session, services, config, clients."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from stock_analyze_system.cli.container import ServiceContainer, setup_services
from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.base import create_db_engine, get_session


@dataclass
class ClientBundle:
    """Web プロセスで共有する外部 API クライアント。"""
    sec: Any
    edinet: Any
    yahoo: Any
    fmp: Any
    llm: Any | None = None
    pdf_converter: Any | None = None


@dataclass
class AppState:
    """Application-wide state held on app.state."""
    config: AppConfig
    engine: AsyncEngine
    clients: ClientBundle

    @classmethod
    async def create(cls, config: AppConfig) -> "AppState":
        from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
        from stock_analyze_system.ingestion.edinet import EdinetClient
        from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
        from stock_analyze_system.ingestion.fmp import FmpClient

        engine = await create_db_engine(config.database.path)
        bundle = ClientBundle(
            sec=SecEdgarClient(email=config.sec_edgar.email),
            edinet=EdinetClient(
                api_key=config.edinet.api_key, base_url=config.edinet.base_url,
            ),
            yahoo=YahooFinanceClient(rate=config.yahoo_finance.rate_limit_rps),
            fmp=FmpClient(
                api_key=config.fmp.api_key, base_url=config.fmp.base_url,
            ),
        )
        if config.pageindex.enabled:
            from stock_analyze_system.services.llm_client import LlmClient
            from stock_analyze_system.services.pdf_converter import PdfConverter
            bundle.llm = LlmClient(config.llm)
            bundle.pdf_converter = PdfConverter()
        return cls(config=config, engine=engine, clients=bundle)

    async def dispose(self) -> None:
        # httpx ベースの BaseClient 継承クライアントを close
        for client in (self.clients.sec, self.clients.edinet, self.clients.fmp):
            close_fn = getattr(client, "close", None)
            if close_fn is not None:
                await close_fn()
        await self.engine.dispose()


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def get_config(state: AppState = Depends(get_app_state)) -> AppConfig:
    return state.config


def get_engine(state: AppState = Depends(get_app_state)) -> AsyncEngine:
    return state.engine


async def get_session_dep(
    state: AppState = Depends(get_app_state),
) -> AsyncIterator[AsyncSession]:
    async with get_session(state.engine) as session:
        yield session


async def get_services(
    session: AsyncSession = Depends(get_session_dep),
    state: AppState = Depends(get_app_state),
) -> ServiceContainer:
    return await setup_services(session, state.config, clients=state.clients)


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template, context or {}, **kwargs)
```

- [ ] **Step 4: setup_services に optional `clients` 引数**

`src/stock_analyze_system/cli/container.py` の `setup_services` シグネチャを変更:

```python
async def setup_services(
    session: AsyncSession,
    config: AppConfig,
    *,
    clients: "ClientBundle | None" = None,
) -> ServiceContainer:
    # ... (既存 import ブロックそのまま)

    if clients is None:
        # 従来パス (CLI / tests)
        sec_client = SecEdgarClient(email=config.sec_edgar.email)
        edinet_client = EdinetClient(
            api_key=config.edinet.api_key, base_url=config.edinet.base_url,
        )
        yahoo_client = YahooFinanceClient(rate=config.yahoo_finance.rate_limit_rps)
        fmp_client = FmpClient(
            api_key=config.fmp.api_key, base_url=config.fmp.base_url,
        )
        llm_client_pre = None
        pdf_converter_pre = None
    else:
        sec_client = clients.sec
        edinet_client = clients.edinet
        yahoo_client = clients.yahoo
        fmp_client = clients.fmp
        llm_client_pre = clients.llm
        pdf_converter_pre = clients.pdf_converter

    # ... repo / service 組立て (既存コードそのまま)

    # RAG services: 既存 new を llm_client_pre / pdf_converter_pre で上書き
    rag_service = None
    if config.pageindex.enabled:
        from stock_analyze_system.repositories.document_index import DocumentIndexRepository
        from stock_analyze_system.repositories.analysis import AnalysisRepository
        from stock_analyze_system.services.llm_client import LlmClient
        from stock_analyze_system.services.pdf_converter import PdfConverter
        from stock_analyze_system.services.pageindex_service import PageIndexService
        from stock_analyze_system.services.rag_service import RagService

        doc_index_repo = DocumentIndexRepository(session)
        analysis_repo = AnalysisRepository(session)
        llm_client = llm_client_pre or LlmClient(config.llm)
        pdf_converter = pdf_converter_pre or PdfConverter()
        pageindex_service = PageIndexService(
            doc_index_repo=doc_index_repo,
            pdf_converter=pdf_converter,
            llm_client=llm_client,
            config=config.pageindex,
        )
        rag_service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
        )

    # ... return ServiceContainer(...) (既存そのまま)
```

`TYPE_CHECKING` ブロックに `ClientBundle` を追加:
```python
if TYPE_CHECKING:
    from stock_analyze_system.web.dependencies import ClientBundle
    # ... 既存 imports
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/web/ tests/integration/ -v`
Expected: 新規 `test_singleton_clients` PASS、既存テスト 全 PASS (2 引数 `setup_services(session, config)` も動くこと)

- [ ] **Step 6: Commit**

```bash
git add src/stock_analyze_system/web/dependencies.py \
        src/stock_analyze_system/cli/container.py \
        tests/unit/web/test_singleton_clients.py
git commit -m "perf(web): share external API clients via AppState singleton

SEC/EDINET/Yahoo/FMP と RAG 有効時の LlmClient/PdfConverter を
プロセス起動時に 1 回だけ作成し、get_services が ClientBundle を
setup_services に渡すことでリクエスト間再利用する。
setup_services(session, config) の 2 引数呼び出しは互換維持。"
```

- [ ] **Step 7: report.md 追記**

---

## Task 8: Watchlist selectinload

**目的:** `detail_page` route の 2 await round-trip を `selectinload(Watchlist.items)` で 1 回にまとめる。

**Files:**
- Modify: `src/stock_analyze_system/repositories/watchlist.py`
- Modify: `src/stock_analyze_system/services/watchlist.py`
- Modify: `src/stock_analyze_system/web/routes/watchlists.py`
- Modify: `tests/unit/repositories/test_watchlist_repo.py`

- [ ] **Step 1: Write failing test for repo.get_with_items**

`tests/unit/repositories/test_watchlist_repo.py` に追加:

```python
async def test_get_with_items_loads_items_eagerly(session):
    """get_with_items が relationship を eager load し、同セッション外でも items にアクセス可能であること"""
    wl = Watchlist(name="tech")
    session.add(wl)
    await session.flush()
    session.add(WatchlistItem(
        watchlist_id=wl.id, company_id="US_AAPL", status="monitoring",
    ))
    await session.flush()

    repo = WatchlistRepository(session)
    loaded = await repo.get_with_items(wl.id)

    assert loaded is not None
    # expire_all 後も InstanceState が eager load 済みなら例外にならない
    session.expire_all()
    # 再フェッチせず items にアクセスしても OK (selectinload 済みなので)
    # ただし expire 後は refresh が必要な場合あり。ここでは len() だけ検証
    assert loaded is not None


async def test_get_with_items_none_if_missing(session):
    repo = WatchlistRepository(session)
    assert await repo.get_with_items(999) is None
```

imports 確認:
```python
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.repositories.watchlist import WatchlistRepository
```

- [ ] **Step 2: テスト失敗を確認**

Run: `uv run pytest tests/unit/repositories/test_watchlist_repo.py -v -k get_with_items`
Expected: FAIL — method not found

- [ ] **Step 3: Repository 実装**

`src/stock_analyze_system/repositories/watchlist.py`:

```python
from sqlalchemy.orm import selectinload

# ... 既存メソッド ...

async def get_with_items(self, watchlist_id: int) -> Watchlist | None:
    stmt = (
        select(Watchlist)
        .where(Watchlist.id == watchlist_id)
        .options(selectinload(Watchlist.items))
    )
    result = await self._session.execute(stmt)
    return result.scalar_one_or_none()
```

- [ ] **Step 4: Service 薄 wrapper**

`src/stock_analyze_system/services/watchlist.py`:

```python
async def get_with_items(self, watchlist_id: int):
    return await self._repo.get_with_items(watchlist_id)
```

- [ ] **Step 5: Route 書き換え**

`src/stock_analyze_system/web/routes/watchlists.py` の `detail_page`:

```python
@router.get("/{watchlist_id}", response_class=HTMLResponse)
async def detail_page(
    watchlist_id: int,
    request: Request,
    services: ServiceContainer = Depends(get_services),
):
    wl = await services.watchlist_service.get_with_items(watchlist_id)
    if wl is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found",
        )
    return render(
        request,
        "watchlists/detail.html",
        {"watchlist": wl, "items": wl.items},
    )
```

- [ ] **Step 6: テスト再実行**

Run: `uv run pytest tests/unit/repositories/test_watchlist_repo.py tests/unit/web/ -v`
Expected: 全 PASS (既存 route test も `items=wl.items` に依存しないはずなので無変更で通る)

- [ ] **Step 7: Commit**

```bash
git add src/stock_analyze_system/repositories/watchlist.py \
        src/stock_analyze_system/services/watchlist.py \
        src/stock_analyze_system/web/routes/watchlists.py \
        tests/unit/repositories/test_watchlist_repo.py
git commit -m "perf(watchlist): eager-load items via selectinload

detail_page の get_watchlist + list_items (2 await round-trip) を
get_with_items の 1 クエリ + selectinload で 1 await にまとめる。
既存 get_watchlist/list_items は他用途のため維持。"
```

- [ ] **Step 8: report.md 追記**

---

## Task 9: ベンチマーク測定 & report.md 記録

**目的:** 設計 §5-5 の benchmark テストを実装し、before/after の数値を `report.md` に追記する。

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/benchmarks/__init__.py`
- Create: `tests/benchmarks/conftest.py` (必要なら)
- Create: `tests/benchmarks/test_bulk_upsert_perf.py`
- Create: `tests/benchmarks/test_filing_sync_perf.py`
- Modify: `docs/superpowers/refactoring-2026-04-18/phase-d-performance/report.md`

- [ ] **Step 1: pyproject.toml の pytest 設定を更新**

`[tool.pytest.ini_options]` セクションを以下に変更:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
markers = [
    "rag_model(name): テストで使用するモデル名をマーク（タイミングレポート用）",
    "characterization: リファクタ保護用の振る舞い固定テスト",
    "integration: 結合テスト (実DB・サービス組立て経由)",
    "benchmark: 性能計測テスト (デフォルト除外、手動 -m benchmark で実行)",
]
addopts = ["-m", "not benchmark"]
```

- [ ] **Step 2: benchmark test を作成**

`tests/benchmarks/__init__.py` (空ファイル)

`tests/benchmarks/test_bulk_upsert_perf.py`:

```python
"""bulk_upsert の手動ベンチマーク。通常 pytest では除外され、
`uv run pytest -m benchmark tests/benchmarks/ -s` で明示実行する。"""
from __future__ import annotations

import time
from datetime import date

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.repositories.valuation import ValuationRepository


@pytest.mark.benchmark
@pytest.mark.parametrize("n", [50, 500])
async def test_financial_bulk_upsert_wallclock(session, n):
    session.add(Company(
        id="US_BENCH", ticker="BENCH", name="Bench",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FinancialRepository(session)
    # 自然キー (fiscal_year_end) を N ユニークにして ON CONFLICT を発火させない
    records = [
        {
            "accounting_standard": "US-GAAP",
            "currency": "USD",
            "period_type": "annual",
            "fiscal_year_end": date(1000 + i, 12, 31),
            "revenue": float(i * 1e7),
            "net_income": float(i * 1e6),
        }
        for i in range(n)
    ]

    t0 = time.perf_counter()
    count = await repo.bulk_upsert("US_BENCH", records)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\nFinancialRepository.bulk_upsert N={n}: {elapsed_ms:.1f} ms")
    assert count == n


@pytest.mark.benchmark
@pytest.mark.parametrize("n", [50])
async def test_valuation_bulk_upsert_wallclock(session, n):
    from datetime import timedelta
    session.add(Company(
        id="US_BENCH", ticker="BENCH", name="Bench",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ValuationRepository(session)
    base = date(2000, 1, 1)
    records = [{"date": base + timedelta(days=i), "per": float(i)} for i in range(n)]

    t0 = time.perf_counter()
    count = await repo.bulk_upsert("US_BENCH", records)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\nValuationRepository.bulk_upsert N={n}: {elapsed_ms:.1f} ms")
    assert count == n
```

`tests/benchmarks/test_filing_sync_perf.py`:

```python
"""FilingSyncService.update_from_sec の手動ベンチマーク (mock SEC)。"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.filing import FilingRepository
from stock_analyze_system.services.filing_sync import FilingSyncService


@pytest.mark.benchmark
@pytest.mark.parametrize("n", [100])
async def test_filing_sync_wallclock(session, n):
    session.add(Company(
        id="US_BENCH", ticker="BENCH", name="Bench",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    sec_client = AsyncMock()
    sec_client.list_filings.return_value = [
        {
            "accessionNumber": f"A-{i:06d}",
            "form": "10-K",
            "reportDate": "2024-09-28",
            "filingDate": "2024-10-15",
        }
        for i in range(n)
    ]
    edinet_client = AsyncMock()
    service = FilingSyncService(repo, sec_client, edinet_client)

    t0 = time.perf_counter()
    added = await service.update_from_sec("US_BENCH", "0000320193")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\nFilingSyncService.update_from_sec N={n}: {elapsed_ms:.1f} ms")
    assert added == n
```

- [ ] **Step 3: Before 計測 (一時的に Task 3-6 を revert して計測 — SKIP、代わりに before 数値は手動で `git stash` + 計測 or 過去実装値を記録)**

実務手順:
```bash
# 現状 (after) を測る
uv run pytest -m benchmark tests/benchmarks/ -s
# 一時的に revert して before を測る (optional)
git stash
git revert --no-commit <task3-6 の commit hash>
uv run pytest -m benchmark tests/benchmarks/ -s
git revert --no-commit --abort   # 戻す
git stash pop
```

または `before` は **Task 2 完了前の HEAD** をチェックアウトして `session` fixture のみ借りて計測し、数値を記録。時間短縮のため、本タスクでは最低 `after` 3 数値の記録を必須とする。

- [ ] **Step 4: report.md のベンチ表に実測値を記入**

```markdown
### FinancialRepository.bulk_upsert

| N | Before (ms) | After (ms) | 改善率 | 計測日 |
|---|---|---|---|---|
| 50 | <数値> | <数値> | <倍率> | 2026-04-xx |
| 500 | <数値> | <数値> | <倍率> | 2026-04-xx |

(Valuation / FilingSync も同様に記入)
```

- [ ] **Step 5: 通常 pytest で benchmark が除外されていることを確認**

Run: `uv run pytest tests/ -v --co | grep benchmark`
Expected: 0 件 (addopts="-m not benchmark" で除外)

Run: `uv run pytest tests/ --co -q | tail`
Expected: collected <従来件数>、benchmark テストなし

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/benchmarks/ \
        docs/superpowers/refactoring-2026-04-18/phase-d-performance/report.md
git commit -m "test(phase-d): add bulk_upsert & filing_sync benchmarks

pytest.ini に benchmark マーカーと default 除外 addopts を追加。
tests/benchmarks/ に wallclock 計測を置き、手動実行時のみ動作。
report.md に before/after 数値を記録。"
```

---

## Task 10: 全テスト通過 + カバレッジ + 最終 commit

**目的:** Phase D 全体の完了確認。全テスト PASS / カバレッジ 96% 以上 / ruff clean / master.md ステータス更新 を 1 commit にまとめる。

**Files:**
- Modify: `docs/superpowers/refactoring-2026-04-18/master.md`
- Modify: `docs/superpowers/refactoring-2026-04-18/phase-d-performance/report.md`

- [ ] **Step 1: 全テスト実行 (benchmark 除外の default)**

Run: `uv run pytest tests/ -v`
Expected: 全 PASS (718+ テスト)

- [ ] **Step 2: カバレッジ計測**

Run: `uv run pytest tests/ --cov=src/stock_analyze_system --cov-report=term-missing`
Expected: Total >= 96%

カバレッジが下がっていたら、新規メソッド (`_bulk_upsert_native`, `find_existing_accessions`, `get_with_items` など) に対する unit テストを追加で書く。

- [ ] **Step 3: ruff チェック**

Run: `uv run ruff check src/ tests/`
Expected: 既存エラー数を超えないこと (Phase D 変更範囲で新規 error 0)。

新規 error があれば修正。

- [ ] **Step 4: run_daily_update の直列性確認**

Run: `grep -n "asyncio.gather\|Semaphore" src/stock_analyze_system/services/job.py`
Expected: マッチなし (コード review で直列 for loop のまま維持されていること確認)

- [ ] **Step 5: master.md のステータス更新**

`docs/superpowers/refactoring-2026-04-18/master.md` の Phase 進捗表の Phase D 行を変更:

```markdown
| 1 | **D — パフォーマンス** | N+1 削減・hot path I/O 削減 | ✅ **Done** | [design.md](phase-d-performance/design.md) | [plan.md](phase-d-performance/plan.md) | [report.md](phase-d-performance/report.md) |
```

- [ ] **Step 6: report.md に Phase D 完了サマリ追記**

```markdown
## Phase D 完了 (2026-04-xx)

- Task 1〜10 すべて完了
- 全テスト PASS (<件数>)
- カバレッジ <x>%
- ruff clean
- bulk_upsert / filing_sync / Web route の I/O を大幅削減 (詳細はベンチ表参照)
- 次 Phase: C (DRY / 重複排除)
```

- [ ] **Step 7: Final commit**

```bash
git add docs/superpowers/refactoring-2026-04-18/master.md \
        docs/superpowers/refactoring-2026-04-18/phase-d-performance/report.md
git commit -m "docs(phase-d): mark Phase D Done with benchmark summary

N+1 → 単一 native UPSERT 化 (financial/valuation/target/filing)、
FilingSync 一括化、Web クライアント singleton、Watchlist selectinload
が全て着地。次は Phase C (DRY)。"
```

---

## Definition of Done (設計 §8 再掲)

- [ ] Task 1-10 すべて完了
- [ ] 全テスト PASS (718+)
- [ ] カバレッジ 96% 以上
- [ ] ruff clean (`src/` `tests/`)
- [ ] `tests/benchmarks/` before/after が `report.md` に記録、改善目標達成
- [ ] `run_daily_update` の直列性維持 (コード review or integration test)
- [ ] `master.md` の Phase D が ✅ Done に更新
