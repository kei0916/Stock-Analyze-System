# Phase C — DRY / 重複排除 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase D で整備した API の重複と、新旧 API の二重化を、helper / adapter / enum の最小追加で解消する。外部観測可能な挙動 (public API shape と既存テスト) は不変、ただし Phase C に限って Phase D 置換済みの旧 method は削除可 (spec §Master rule 例外)。

**Architecture:** 3 Task クラスタを独立 TDD サイクルで回す。
1. `BaseRepository._bulk_upsert_by_natural_key` を追加し、`FinancialRepository.bulk_upsert` / `ValuationRepository.bulk_upsert` を 1 行 delegate に縮小。
2. `FilingSource` enum + `FilingSourceAdapter` dataclass + `FilingSyncService._sync(adapter, ...)` を導入し、`update_from_sec` / `update_from_edinet` の同形 body を 1 箇所に集約。
3. `cli/watchlist.py:_handle_show` を `get_with_items` に移行し、`WatchlistService.get_watchlist` / `list_items` を削除 (master.md ルール例外を明記)。

**Tech Stack:** Python 3.12 / SQLAlchemy 2.0 async + `sqlalchemy.dialects.sqlite.insert` (native UPSERT) / `@dataclass(frozen=True)` + `Callable`/`Awaitable` typing / StrEnum / pytest + pytest-asyncio。

**Spec:** [`design.md`](design.md) (commit 20fc0ff, 375 行)

**作業順序**: Task 1 → Task 2a → Task 2b → Task 3a → Task 3b → Task 4 (最終まとめ)。Task 間に依存は無いが、このまま上から順に実行すると各 commit が小さくレビューしやすい。

---

## Task 1: `BaseRepository._bulk_upsert_by_natural_key` + Financial/Valuation delegate 化

**Files:**
- Modify: `src/stock_analyze_system/repositories/base.py` (末尾に helper メソッド追加)
- Modify: `src/stock_analyze_system/repositories/financial.py:52-66` (`bulk_upsert` 本体を delegate に縮小)
- Modify: `src/stock_analyze_system/repositories/valuation.py:46-60` (同上)
- Test: `tests/unit/repositories/test_base_repo.py` (末尾に `TestBulkUpsertByNaturalKey` クラス相当の 4 test 追加)

**Scope 明示** (spec §Task 1 より):
- **適用**: `FinancialRepository`, `ValuationRepository` の `bulk_upsert` のみ
- **非適用**: `FilingRepository.bulk_upsert` (accession_no / doc_id がグローバル一意で scope 概念に合わない)
- **非適用**: `TargetRepository.bulk_add` (事前 SELECT による正確な追加件数を返す semantic を保持)

---

- [ ] **Step 1.1: 失敗テスト 4 件を追加**

`tests/unit/repositories/test_base_repo.py` の末尾に以下を追記:

```python
async def test_bulk_upsert_by_natural_key_without_scope(session):
    """scope なし: records をそのまま INSERT、index_elements が natural_key_cols 一致。"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28), "revenue": 1.0,
    }]
    n = await repo._bulk_upsert_by_natural_key(
        rows,
        natural_key_cols=(
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
        ),
    )
    assert n == 1
    assert await repo.count(company_id="US_AAPL") == 1


async def test_bulk_upsert_by_natural_key_with_scope(session):
    """scope あり: 各 row に {scope_key: scope_value} が前置され保存される。"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = BaseRepository(session, FinancialData)
    records = [{
        "accounting_standard": "US-GAAP", "currency": "USD",
        "period_type": "annual", "fiscal_year_end": date(2024, 9, 28),
        "revenue": 2.0,
    }]
    n = await repo._bulk_upsert_by_natural_key(
        records,
        natural_key_cols=(
            "period_type", "fiscal_year_end", "accounting_standard",
        ),
        scope_key="company_id", scope_value="US_AAPL",
    )
    assert n == 1
    assert await repo.count(company_id="US_AAPL") == 1


async def test_bulk_upsert_by_natural_key_empty_records(session):
    """空入力なら 0 を返し SQL を発行しない。"""
    repo = BaseRepository(session, FinancialData)
    n = await repo._bulk_upsert_by_natural_key(
        [], natural_key_cols=("company_id",),
    )
    assert n == 0
    assert await repo.count() == 0


async def test_bulk_upsert_by_natural_key_no_update_columns(session):
    """natural_key が全カラムを覆う場合: on_conflict_do_nothing で既存を保持。"""
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
    # 全カラムを natural_key に含める → update_columns が空になる
    rows = [{
        "company_id": "US_AAPL", "accounting_standard": "US-GAAP",
        "currency": "USD", "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28),
    }]
    n = await repo._bulk_upsert_by_natural_key(
        rows,
        natural_key_cols=(
            "company_id", "accounting_standard", "currency",
            "period_type", "fiscal_year_end",
        ),
    )
    assert n == 1
    session.expire_all()
    from sqlalchemy import select
    result = await session.execute(
        select(FinancialData).where(FinancialData.company_id == "US_AAPL"),
    )
    row = result.scalar_one()
    assert row.revenue == 100.0  # 既存保持
```

- [ ] **Step 1.2: テスト失敗を確認**

Run: `uv run pytest tests/unit/repositories/test_base_repo.py -v`
Expected: 4 new tests FAIL with `AttributeError: 'BaseRepository' object has no attribute '_bulk_upsert_by_natural_key'` (既存テストは PASS)

- [ ] **Step 1.3: `_bulk_upsert_by_natural_key` を実装**

`src/stock_analyze_system/repositories/base.py` の import と末尾に追記:

```python
# 先頭 import に追加
from collections.abc import Sequence
```

```python
# クラス末尾 (既存 _bulk_upsert_native の直後) に追加
    async def _bulk_upsert_by_natural_key(
        self,
        records: list[dict],
        natural_key_cols: Sequence[str],
        *,
        scope_key: str | None = None,
        scope_value: Any = None,
    ) -> int:
        """自然キーで一括 UPSERT。

        scope_key 指定時は各 row に {scope_key: scope_value} を前置し、
        index_elements にも含める。update_columns は row 全キーから
        index_elements を除いた残り。空入力で 0、非空で len(records) を返す。
        """
        if not records:
            return 0
        if scope_key is not None:
            rows = [{scope_key: scope_value, **r} for r in records]
            index_elements = [scope_key, *natural_key_cols]
        else:
            rows = list(records)
            index_elements = list(natural_key_cols)
        update_columns = [c for c in rows[0].keys() if c not in index_elements]
        await self._bulk_upsert_native(
            rows,
            index_elements=index_elements,
            update_columns=update_columns,
        )
        return len(records)
```

- [ ] **Step 1.4: 4 test が PASS することを確認**

Run: `uv run pytest tests/unit/repositories/test_base_repo.py -v`
Expected: 4 new tests PASS, 全 既存 tests PASS

- [ ] **Step 1.5: `FinancialRepository.bulk_upsert` を delegate に縮小**

`src/stock_analyze_system/repositories/financial.py:52-66` を以下に置換:

```python
    async def bulk_upsert(
        self, company_id: str, records: list[dict],
    ) -> int:
        """一括 upsert。戻り値は処理レコード数。"""
        return await self._bulk_upsert_by_natural_key(
            records,
            FINANCIAL_NATURAL_KEY,
            scope_key="company_id",
            scope_value=company_id,
        )
```

- [ ] **Step 1.6: `ValuationRepository.bulk_upsert` を delegate に縮小**

`src/stock_analyze_system/repositories/valuation.py:46-60` を以下に置換:

```python
    async def bulk_upsert(
        self, company_id: str, records: list[dict],
    ) -> int:
        """一括 upsert。戻り値は処理レコード数。"""
        return await self._bulk_upsert_by_natural_key(
            records,
            ("date",),
            scope_key="company_id",
            scope_value=company_id,
        )
```

- [ ] **Step 1.7: 全 repo テストが既存 API で PASS することを確認**

Run: `uv run pytest tests/unit/repositories/ -v`
Expected: 全 tests PASS (既存 `test_financial_repo.py` / `test_valuation_repo.py` / `test_other_repos.py` 無変更)

- [ ] **Step 1.8: 全 suite 回帰確認**

Run: `uv run pytest`
Expected: 全 tests PASS (既存 737 + 新規 4 = 741 target)

- [ ] **Step 1.9: ruff チェック**

Run: `uv run ruff check src/stock_analyze_system/repositories/ tests/unit/repositories/`
Expected: Phase C 新規コードで 0 errors (既存の 8 errors は Phase D からの繰越で Phase C 対象外)

- [ ] **Step 1.10: Commit**

```bash
git add src/stock_analyze_system/repositories/base.py \
        src/stock_analyze_system/repositories/financial.py \
        src/stock_analyze_system/repositories/valuation.py \
        tests/unit/repositories/test_base_repo.py
git commit -m "$(cat <<'EOF'
refactor(repo): introduce _bulk_upsert_by_natural_key helper

- BaseRepository._bulk_upsert_by_natural_key を追加 (scope_key/value 対応)
- FinancialRepository.bulk_upsert / ValuationRepository.bulk_upsert を 1 行 delegate に縮小
- 新規 4 unit tests (scope 有/無 x update 有/無)
- 既存テスト無変更で PASS

Phase C Task 1. See docs/superpowers/refactoring-2026-04-18/phase-c-dry/design.md §Task 1.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2a: `FilingSource` enum + `FilingRepository.bulk_upsert(source=FilingSource)`

**Files:**
- Modify: `src/stock_analyze_system/models/enums.py` (末尾に `FilingSource` 追加)
- Modify: `src/stock_analyze_system/repositories/filing.py:85-104` (`source` param 型を `str` → `FilingSource`)
- Modify: `src/stock_analyze_system/services/filing_sync.py:74, 123` (`source="SEC"` / `"EDINET"` を enum に置換)
- Test: `tests/unit/repositories/test_filing_repo.py:145, 154` (文字列 → enum 置換、エラー分岐は enum 外値に変更)

**破壊的変更**: `FilingRepository.bulk_upsert(source=)` は `str` → `FilingSource`。caller は `FilingSyncService` のみ (src 内)、tests 2 箇所。Phase C の master rule 例外節で網羅済。

---

- [ ] **Step 2a.1: `FilingSource` enum を追加**

`src/stock_analyze_system/models/enums.py` の末尾に追記:

```python
class FilingSource(StrEnum):
    """ファイリング取得元 (SEC EDGAR / EDINET)。

    FilingRepository.bulk_upsert / FilingSyncService._sync のディスパッチキー。
    """
    SEC = "SEC"
    EDINET = "EDINET"
```

- [ ] **Step 2a.2: enum 追加だけで全 test が PASS することを確認**

Run: `uv run pytest tests/unit/test_models.py tests/unit/repositories/test_filing_repo.py tests/unit/services/test_filing_sync.py -v`
Expected: 全 tests PASS (まだ型変更していないので既存動作)

- [ ] **Step 2a.3: `FilingRepository.bulk_upsert` signature を更新**

`src/stock_analyze_system/repositories/filing.py:85-104` を以下に置換:

```python
    async def bulk_upsert(
        self, company_id: str, records: list[dict], *, source: FilingSource,
    ) -> int:
        if source is FilingSource.SEC:
            key_col = "accession_no"
        elif source is FilingSource.EDINET:
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

import に `FilingSource` を追加:

```python
from stock_analyze_system.models.enums import FilingSource
```

- [ ] **Step 2a.4: 呼び出し側を enum に更新 (services/filing_sync.py)**

`src/stock_analyze_system/services/filing_sync.py` の import:

```python
from stock_analyze_system.models.enums import FilingSource, FilingType, PeriodType
```

`src/stock_analyze_system/services/filing_sync.py:74`:

```python
        if new_rows:
            await self._repo.bulk_upsert(company_id, new_rows, source=FilingSource.SEC)
```

`src/stock_analyze_system/services/filing_sync.py:123`:

```python
        if new_rows:
            await self._repo.bulk_upsert(company_id, new_rows, source=FilingSource.EDINET)
```

**Note**: row dict 内の `"source": "SEC"` / `"source": "EDINET"` (line 61, 114) は Filing モデルのカラム値であり enum 変換不要 (Phase B で別途検討する表記ズレ案件、今は触らない)。

- [ ] **Step 2a.5: 既存 repo テストを enum に更新**

`tests/unit/repositories/test_filing_repo.py` の import 追加:

```python
from stock_analyze_system.models.enums import FilingSource
```

`tests/unit/repositories/test_filing_repo.py:145` を以下に置換:

```python
    count = await repo.bulk_upsert("US_AAPL", rows, source=FilingSource.SEC)
```

`tests/unit/repositories/test_filing_repo.py:150-154` の `rejects_unknown_source` test を以下に置換 (現在は `source="OTHER"` 文字列だが、enum 化後は存在しない値を渡すテストは型エラーになるので、別名の「`FilingSource` 以外の値を渡すと ValueError」に変更。ただし mypy 厳格化していない現状では `object()` のような値を押し込めば動作テストになる):

```python
async def test_bulk_upsert_filings_rejects_unknown_source(session):
    repo = FilingRepository(session)
    import pytest
    # enum 以外の値でも records が非空なら ValueError を投げる挙動を保証
    class _Fake:
        def __str__(self):
            return "OTHER"
    with pytest.raises(ValueError, match="unknown source"):
        await repo.bulk_upsert(
            "US_AAPL",
            [{"filing_type": "10-K"}],  # 非空 records で分岐に入れる
            source=_Fake(),  # type: ignore[arg-type]
        )
```

**理由**: 旧実装は `if not records` が enum 判定の後だったため空 records でも ValueError を投げていたが、新実装 (Step 2a.3) でも enum 判定が先なので同じ分岐順序 → `[{...}]` を渡さずとも投げる。ただし型ヒント (`source: FilingSource`) と相性が悪い「明らかに不正な値」テストとして `_Fake()` を渡すのが安全。

- [ ] **Step 2a.6: filing_sync テストを enum に更新**

`tests/unit/services/test_filing_sync.py` で `bulk_upsert` の呼び出し assertion に `source=` を確認している箇所があれば enum 値に置換する。現状 `call_args[0][1]` で positional の rows しか assert していないので、**新規追加なし・既存無変更で PASS 見込み**。念のため grep で確認:

Run: `grep -n 'source=' tests/unit/services/test_filing_sync.py`
Expected: 何もヒットしない (= 更新不要)

- [ ] **Step 2a.7: 全 suite 回帰確認**

Run: `uv run pytest`
Expected: 全 tests PASS (新規 0, 既存 741)

- [ ] **Step 2a.8: ruff チェック**

Run: `uv run ruff check src/stock_analyze_system/models/enums.py src/stock_analyze_system/repositories/filing.py src/stock_analyze_system/services/filing_sync.py tests/unit/repositories/test_filing_repo.py`
Expected: 0 new errors

- [ ] **Step 2a.9: Commit**

```bash
git add src/stock_analyze_system/models/enums.py \
        src/stock_analyze_system/repositories/filing.py \
        src/stock_analyze_system/services/filing_sync.py \
        tests/unit/repositories/test_filing_repo.py
git commit -m "$(cat <<'EOF'
refactor(filing): introduce FilingSource enum

- models/enums.py に FilingSource(StrEnum) を追加 (SEC/EDINET)
- FilingRepository.bulk_upsert(source=) を str → FilingSource に型変更
- FilingSyncService の呼び出し 2 箇所を enum 値に置換
- test_filing_repo.py の source 文字列を FilingSource.SEC に置換

Phase C Task 2a. Phase B の stringly-typed 候補を Task 2b の前提として先取り。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2b: `FilingSourceAdapter` + `FilingSyncService._sync`

**Files:**
- Modify: `src/stock_analyze_system/services/filing_sync.py` (module top: `_map_sec_record` / `_map_edinet_record` + `FilingSourceAdapter` 追加、`FilingSyncService._sync` 追加、`update_from_sec` / `update_from_edinet` を adapter 組立 + `_sync` delegate に置換)
- Test: `tests/unit/services/test_filing_sync.py` (末尾に `TestFilingSyncInternal` クラスで 5 ケース追加)

**既存テストの扱い**: `TestFilingSyncService` / `TestUpdateFromSecErrors` / `TestUpdateFromEdinet` は `update_from_sec` / `update_from_edinet` の behavioral test で API 不変なので無変更 PASS 見込み。ただし例外捕捉の広さが変わるため注意 (下記 Step 2b.5 参照)。

---

- [ ] **Step 2b.1: `_sync` 内部単体テスト 5 件を追加 (失敗テスト)**

`tests/unit/services/test_filing_sync.py` の末尾に追記 (imports は `dataclass` / `FilingSource` を追加):

```python
import pytest
from stock_analyze_system.models.enums import FilingSource
from stock_analyze_system.services.filing_sync import FilingSourceAdapter


def _make_adapter(
    *,
    source=FilingSource.SEC,
    fetch=None,
    key_field="accessionNumber",
    find_existing=None,
    map_record=None,
):
    return FilingSourceAdapter(
        source=source,
        fetch=fetch or AsyncMock(return_value=[]),
        key_field=key_field,
        find_existing=find_existing or AsyncMock(return_value=set()),
        map_record=map_record or (lambda d: {"accession_no": d[key_field]}),
    )


class TestFilingSyncInternal:
    """FilingSyncService._sync の直接単体テスト"""

    async def test_happy_path_filters_existing(self):
        """fetch 3 件 + existing 1 件 → new_rows 2 件で bulk_upsert が呼ばれる"""
        filing_repo = AsyncMock()
        filing_repo.bulk_upsert.return_value = 2
        raw = [
            {"accessionNumber": "a1"},
            {"accessionNumber": "a2"},
            {"accessionNumber": "a3"},
        ]
        adapter = _make_adapter(
            fetch=AsyncMock(return_value=raw),
            find_existing=AsyncMock(return_value={"a2"}),
        )
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(), edinet_client=AsyncMock(),
        )
        n = await svc._sync(adapter, "US_AAPL", "0000320193")
        assert n == 2
        filing_repo.bulk_upsert.assert_called_once()
        # source=FilingSource.SEC が渡る
        kwargs = filing_repo.bulk_upsert.call_args.kwargs
        assert kwargs["source"] is FilingSource.SEC
        # new_rows の件数が fetch - existing と一致
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert len(rows) == 2

    async def test_empty_fetch_returns_zero_without_upsert(self):
        """fetch 空 → 即 return 0、bulk_upsert 未呼び出し"""
        filing_repo = AsyncMock()
        adapter = _make_adapter(fetch=AsyncMock(return_value=[]))
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(), edinet_client=AsyncMock(),
        )
        n = await svc._sync(adapter, "US_AAPL", "0000320193")
        assert n == 0
        filing_repo.bulk_upsert.assert_not_called()

    async def test_all_existing_returns_zero_without_upsert(self):
        """fetch 3 件すべて existing → new_rows 空 → return 0"""
        filing_repo = AsyncMock()
        raw = [{"accessionNumber": "a1"}, {"accessionNumber": "a2"}]
        adapter = _make_adapter(
            fetch=AsyncMock(return_value=raw),
            find_existing=AsyncMock(return_value={"a1", "a2"}),
        )
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(), edinet_client=AsyncMock(),
        )
        n = await svc._sync(adapter, "US_AAPL", "0000320193")
        assert n == 0
        filing_repo.bulk_upsert.assert_not_called()

    async def test_fetch_exception_logged_and_returns_zero(self, caplog):
        """fetch 例外 → logger.warning + return 0"""
        import logging
        filing_repo = AsyncMock()
        adapter = _make_adapter(
            fetch=AsyncMock(side_effect=OSError("API down")),
        )
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(), edinet_client=AsyncMock(),
        )
        with caplog.at_level(logging.WARNING):
            n = await svc._sync(adapter, "US_AAPL", "0000320193")
        assert n == 0
        filing_repo.bulk_upsert.assert_not_called()
        assert any("filing fetch failed" in r.message for r in caplog.records)

    async def test_map_record_called_only_for_new_entries(self):
        """map_record は (fetch - existing) 件数と同じ回数呼ばれる"""
        filing_repo = AsyncMock()
        filing_repo.bulk_upsert.return_value = 1
        raw = [{"accessionNumber": "a1"}, {"accessionNumber": "a2"}]
        map_calls = []
        def _map(d):
            map_calls.append(d)
            return {"accession_no": d["accessionNumber"]}
        adapter = _make_adapter(
            fetch=AsyncMock(return_value=raw),
            find_existing=AsyncMock(return_value={"a1"}),
            map_record=_map,
        )
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(), edinet_client=AsyncMock(),
        )
        await svc._sync(adapter, "US_AAPL", "0000320193")
        assert len(map_calls) == 1
        assert map_calls[0]["accessionNumber"] == "a2"
```

- [ ] **Step 2b.2: テスト失敗を確認**

Run: `uv run pytest tests/unit/services/test_filing_sync.py::TestFilingSyncInternal -v`
Expected: 5 tests FAIL with `ImportError: cannot import name 'FilingSourceAdapter'` 等

- [ ] **Step 2b.3: `FilingSourceAdapter` + `_map_*` + `_sync` を実装**

`src/stock_analyze_system/services/filing_sync.py` の先頭 import に追加:

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
```

既存 `from stock_analyze_system.models.enums import FilingSource, FilingType, PeriodType` は Task 2a で追加済。

クラス定義前 (module top、`logger = ...` の直後) に追加:

```python
@dataclass(frozen=True)
class FilingSourceAdapter:
    """ソース別 (SEC/EDINET) の fetch / 既存検出 / mapping を束ねた adapter。

    FilingSyncService._sync の共通パイプラインにこの adapter を渡して
    ソース差分を局所化する。
    """
    source: FilingSource
    fetch: Callable[[str], Awaitable[list[dict]]]
    key_field: str
    find_existing: Callable[[str, list[str]], Awaitable[set[str]]]
    map_record: Callable[[dict], dict]


def _map_sec_record(raw: dict) -> dict:
    """SEC filing エントリ → Filing row dict。"""
    form = raw["form"]
    report_date = raw.get("reportDate", "")
    filed_date = raw.get("filingDate", "")
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
        "accession_no": raw["accessionNumber"],
    }
    if report_date:
        row["period_end"] = date_type.fromisoformat(report_date)
    if filed_date:
        row["filed_at"] = date_type.fromisoformat(filed_date)
    return row


def _map_edinet_record(raw: dict) -> dict:
    """EDINET document エントリ → Filing row dict。"""
    today = date_type.today()
    fiscal_year_str = raw.get("periodEnd", "")[:4]
    fiscal_year = int(fiscal_year_str) if fiscal_year_str.isdigit() else today.year
    doc_type = raw.get("docTypeCode", "")
    period_type = (
        PeriodType.ANNUAL if doc_type in ("120", "130") else PeriodType.QUARTERLY
    )
    filing_type = (
        "annual_report" if period_type == PeriodType.ANNUAL else "quarterly_report"
    )
    return {
        "source": "EDINET",
        "filing_type": filing_type,
        "period_type": period_type,
        "fiscal_year": fiscal_year,
        "doc_id": raw["docID"],
    }
```

`FilingSyncService` クラス内に `_sync` メソッドを追加 (既存 `update_from_sec` の前):

```python
    async def _sync(
        self,
        adapter: FilingSourceAdapter,
        company_id: str,
        external_id: str,
    ) -> int:
        """ソース横断の共通 sync パイプライン。"""
        try:
            raw = await adapter.fetch(external_id)
        except (ValueError, OSError, KeyError) as e:
            logger.warning(
                "filing fetch failed: source=%s company=%s id=%s err=%s",
                adapter.source, company_id, external_id, e,
            )
            return 0

        if not raw:
            return 0

        keys = [d[adapter.key_field] for d in raw if d.get(adapter.key_field)]
        existing = await adapter.find_existing(company_id, keys)

        new_rows: list[dict] = []
        for entry in raw:
            key_val = entry.get(adapter.key_field)
            if not key_val or key_val in existing:
                continue
            new_rows.append(adapter.map_record(entry))

        if not new_rows:
            return 0

        count = await self._repo.bulk_upsert(
            company_id, new_rows, source=adapter.source,
        )
        logger.info(
            "Filing update for %s (%s): %d new filings",
            company_id, adapter.source, count,
        )
        return count
```

**注意**:
- `fetch` 例外捕捉は旧 `update_from_sec` / `update_from_edinet` と同一 `(ValueError, OSError, KeyError)` に合わせる (既存 `test_returns_zero_on_api_failure` が `OSError` を投げているため、これを外すと既存 test が落ちる)。
- `logger.warning` を `logger.exception` にしないのは、新規 test `test_fetch_exception_logged_and_returns_zero` が `WARNING` レベルをアサートする設計のため。`update_from_sec` 旧コードは `logger.exception` だが、`_sync` 化に伴い共通化として `logger.warning` に揃える。既存 test は log レベルをアサートしていないので後方互換。

- [ ] **Step 2b.4: `update_from_sec` / `update_from_edinet` を `_sync` delegate に置換**

`src/stock_analyze_system/services/filing_sync.py` の `update_from_sec` (line 28-77) と `update_from_edinet` (line 79-128) を以下に置換:

```python
    async def update_from_sec(
        self, company_id: str, cik: str,
    ) -> int:
        """SEC EDGAR からファイリングを取得・登録。戻り値は新規登録数。"""
        adapter = FilingSourceAdapter(
            source=FilingSource.SEC,
            fetch=lambda cik_: self._sec.list_filings(cik_, max_years=2),
            key_field="accessionNumber",
            find_existing=self._repo.find_existing_accessions,
            map_record=_map_sec_record,
        )
        return await self._sync(adapter, company_id, cik)

    async def update_from_edinet(
        self, company_id: str, edinet_code: str,
    ) -> int:
        """EDINET からファイリングを取得・登録。戻り値は登録数。"""
        today = date_type.today()
        start = (today - timedelta(days=365 * 2)).isoformat()
        end = today.isoformat()
        adapter = FilingSourceAdapter(
            source=FilingSource.EDINET,
            fetch=lambda code: self._edinet.search_company_filings(code, start, end),
            key_field="docID",
            find_existing=self._repo.find_existing_doc_ids,
            map_record=_map_edinet_record,
        )
        return await self._sync(adapter, company_id, edinet_code)
```

**注意**: `self._sec.list_filings` は `(cik, max_years=2)` の signature、`self._edinet.search_company_filings` は `(code, start, end)` の signature で、adapter の `fetch(external_id)` 1 引数に合わない。そのため lambda でラップして external_id → 具体 API 呼び出しに変換する。`today` / `start` / `end` はクロージャとしてキャプチャ (EDINET 側のみ必要)。

- [ ] **Step 2b.5: filing_sync テストが全 PASS することを確認**

Run: `uv run pytest tests/unit/services/test_filing_sync.py -v`
Expected: 全 tests PASS (既存 10 件 + 新規 5 件 = 15 件)

**Troubleshoot**: もし `test_returns_zero_on_api_failure` で「SEC API失敗時」がログレベル `WARNING` 起因で落ちる場合、caplog 検証がないので問題ないはず。落ちたら、例外捕捉範囲 `(ValueError, OSError, KeyError)` を厳密に確認。

- [ ] **Step 2b.6: 全 suite 回帰確認**

Run: `uv run pytest`
Expected: 全 tests PASS (741 + 5 = 746 target)

- [ ] **Step 2b.7: ruff チェック**

Run: `uv run ruff check src/stock_analyze_system/services/filing_sync.py tests/unit/services/test_filing_sync.py`
Expected: 0 new errors

- [ ] **Step 2b.8: Commit**

```bash
git add src/stock_analyze_system/services/filing_sync.py \
        tests/unit/services/test_filing_sync.py
git commit -m "$(cat <<'EOF'
refactor(filing_sync): unify source sync via adapter pattern

- FilingSourceAdapter dataclass を module-level に追加 (fetch/key_field/find_existing/map_record)
- _map_sec_record / _map_edinet_record を module 関数に抽出
- FilingSyncService._sync(adapter, ...) で共通パイプラインを実装
- update_from_sec / update_from_edinet を adapter 組立 + _sync delegate に縮小
- 新規 5 unit tests (TestFilingSyncInternal, happy/empty/all-existing/exception/map-count)
- 既存 10 tests 無変更で PASS

Phase C Task 2b. See design.md §Task 2.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3a: CLI `_handle_show` を `get_with_items` に移行

**Files:**
- Modify: `src/stock_analyze_system/cli/watchlist.py:87-109` (`_handle_show`)
- Modify: `tests/unit/cli/test_watchlist_cli.py:72-89, 169-175, 177-190, 191-203` (4 tests: 2-call mock を 1-call に統合)
- Modify: `tests/integration/test_service_assembly.py:91-93` (`list_items` → `get_with_items().items`)

---

- [ ] **Step 3a.1: CLI `_handle_show` を書き換え**

`src/stock_analyze_system/cli/watchlist.py:87-109` を以下に置換:

```python
async def _handle_show(args: argparse.Namespace, services: ServiceContainer) -> None:
    wl = await services.watchlist_service.get_with_items(args.watchlist_id)
    if wl is None:
        print(f"Watchlist {args.watchlist_id} not found.", file=sys.stderr)
        sys.exit(1)

    rows = [
        {"Company": item.company_id, "Status": item.status}
        for item in wl.items
    ]

    if args.json:
        print(format_json({
            "id": wl.id, "name": wl.name,
            "description": wl.description, "items": rows,
        }))
    else:
        print(f"Watchlist: {wl.name} (id={wl.id})")
        if rows:
            print(format_table(rows))
        else:
            print("  (empty)")
```

- [ ] **Step 3a.2: CLI show test (4 件) を 1-call mock に更新**

`tests/unit/cli/test_watchlist_cli.py:72-89` の `TestWatchlistShow.test_show` を以下に置換:

```python
class TestWatchlistShow:
    async def test_show(self, capsys):
        svc = _make_services()
        item = MagicMock()
        item.company_id = "US_AAPL"
        item.status = "monitoring"
        wl = MagicMock()
        wl.id = 1
        wl.name = "My List"
        wl.description = "Test"
        wl.items = [item]
        svc.watchlist_service.get_with_items = AsyncMock(return_value=wl)

        args = argparse.Namespace(action="show", json=False, watchlist_id=1)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "US_AAPL" in out
```

`tests/unit/cli/test_watchlist_cli.py:169-175` の `test_show_unknown_exits` を以下に置換:

```python
    async def test_show_unknown_exits(self):
        """_handle_show: get_with_items が None なら exit(1)"""
        svc = _make_services()
        svc.watchlist_service.get_with_items = AsyncMock(return_value=None)
        args = argparse.Namespace(action="show", json=False, watchlist_id=999)
        with pytest.raises(SystemExit):
            await handle(args, svc)
```

`tests/unit/cli/test_watchlist_cli.py:177-190` の `test_show_json_empty_items` を以下に置換:

```python
    async def test_show_json_empty_items(self, capsys):
        """_handle_show: items=0 & json=True"""
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "L"
        wl.description = None
        wl.items = []
        svc.watchlist_service.get_with_items = AsyncMock(return_value=wl)
        args = argparse.Namespace(action="show", json=True, watchlist_id=1)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert '"items": []' in out
```

`tests/unit/cli/test_watchlist_cli.py:191-203` の `test_show_empty_items_text` を以下に置換:

```python
    async def test_show_empty_items_text(self, capsys):
        """_handle_show: items=0 & json=False → (empty) 表示"""
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "L"
        wl.description = None
        wl.items = []
        svc.watchlist_service.get_with_items = AsyncMock(return_value=wl)
        args = argparse.Namespace(action="show", json=False, watchlist_id=1)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "(empty)" in out
```

- [ ] **Step 3a.3: integration test を更新**

`tests/integration/test_service_assembly.py:91-93` を以下に置換:

```python
        wl_with_items = await services.watchlist_service.get_with_items(wl.id)
        company_ids = sorted(item.company_id for item in wl_with_items.items)
        assert company_ids == ["US_A", "US_B"]
```

- [ ] **Step 3a.4: CLI test + integration test が PASS することを確認**

Run: `uv run pytest tests/unit/cli/test_watchlist_cli.py tests/integration/test_service_assembly.py -v`
Expected: 全 tests PASS

- [ ] **Step 3a.5: 全 suite 回帰確認**

Run: `uv run pytest`
Expected: 全 tests PASS (746 維持、cli/integration は既存件数のまま)

- [ ] **Step 3a.6: Commit**

```bash
git add src/stock_analyze_system/cli/watchlist.py \
        tests/unit/cli/test_watchlist_cli.py \
        tests/integration/test_service_assembly.py
git commit -m "$(cat <<'EOF'
refactor(cli): migrate watchlist show to get_with_items

- cli/watchlist.py の _handle_show を get_watchlist + list_items の 2-call から get_with_items 1-call に統合
- test_watchlist_cli.py の show 系 4 tests を 1-call mock に更新
- test_service_assembly.py の list_items 呼出しを get_with_items().items に更新

Phase C Task 3a. See design.md §Task 3-1/3-3.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3b: `WatchlistService.get_watchlist` / `list_items` 削除 + master.md ルール追補

**Files:**
- Modify: `src/stock_analyze_system/services/watchlist.py:28-32` (2 methods 削除)
- Modify: `docs/superpowers/refactoring-2026-04-18/master.md` (§ルール §4 に Phase C 例外追記)

**事前確認**: `grep watchlist_service.get_watchlist|watchlist_service.list_items` で src/tests 両方 0 ヒットであること (Task 3a 後にはそうなっているはず)。

---

- [ ] **Step 3b.1: src 内 残 caller の最終確認**

Run:
```bash
uv run python -c "import subprocess; subprocess.run(['grep', '-rn', 'watchlist_service.get_watchlist\\|watchlist_service.list_items', 'src/', 'tests/'])"
```
Expected: 何もヒットしない (Task 3a で全移行済)。もしヒットしたら該当箇所を先に修正。

- [ ] **Step 3b.2: `WatchlistService` から 2 methods を削除**

`src/stock_analyze_system/services/watchlist.py:28-32` を削除:

```python
    # 削除対象:
    async def get_watchlist(self, watchlist_id: int):
        return await self._repo.get_by_id(watchlist_id)

    async def list_items(self, watchlist_id: int):
        return await self._repo.list_items(watchlist_id)
```

削除後の `WatchlistService` は `create_watchlist` / `list_watchlists` / `add_item` / `remove_item` / `get_with_items` の 5 methods。

**非削除 (念押し)**: `WatchlistRepository.list_items` / `get_by_id` は repo 層に残す (Phase E 棚卸し対象)。`get_with_items` 内部で `get_by_id` は未使用だが、repo 側の public API は本 Phase C の対象外。

- [ ] **Step 3b.3: service test が PASS することを確認**

Run: `uv run pytest tests/unit/services/test_watchlist_service.py -v`
Expected: 全 tests PASS (削除 2 methods に対する個別テストは元々存在しない ≒ Step 3a 前の `grep` でも該当なしだった)

- [ ] **Step 3b.4: master.md §ルール を Phase C 例外対応に更新**

`docs/superpowers/refactoring-2026-04-18/master.md` の `## ルール` セクション (行 23-30) の §4 を以下に置換:

```markdown
4. **後方互換**: public API (service/repository 外部メソッド) は Phase D〜B では不変。
   **例外 (Phase C で適用済)**: Phase D で新 API (例: `get_with_items`) に置換された
   旧 method は、全 caller (src/tests 含む) が移行済みであれば Phase C で削除可。
   削除対象は Phase C spec で明示する。
5. **Phase A のみ** API 変更許容 (spec で明示)。
```

**注意**: 旧 §4 は 1 項目だった。Phase A を §5 として新規採番することで、既存 Phase A spec が書かれたとき §4 と §5 で整合が取れる。現状 Phase A spec は未着手なので影響なし。

- [ ] **Step 3b.5: 全 suite 回帰確認**

Run: `uv run pytest`
Expected: 全 tests PASS (746 維持)

- [ ] **Step 3b.6: ruff チェック**

Run: `uv run ruff check src/stock_analyze_system/services/watchlist.py`
Expected: 0 new errors

- [ ] **Step 3b.7: Commit**

```bash
git add src/stock_analyze_system/services/watchlist.py \
        docs/superpowers/refactoring-2026-04-18/master.md
git commit -m "$(cat <<'EOF'
refactor(watchlist): drop superseded service methods

- WatchlistService.get_watchlist / list_items を削除 (Phase D で get_with_items に置換済)
- master.md §ルール §4 に Phase C 例外を明記、Phase A を §5 に繰り下げ
- WatchlistRepository 側は非削除 (Phase E で棚卸し)

Phase C Task 3b. See design.md §Task 3-2/3-4 §Master rule 例外の明示.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Phase C 完了報告 — `report.md` + `master.md` 進捗更新

**Files:**
- Create: `docs/superpowers/refactoring-2026-04-18/phase-c-dry/report.md`
- Modify: `docs/superpowers/refactoring-2026-04-18/master.md` (Phase 進捗表 §Phase C 行を ⚪ → ✅、`report.md` リンク)

---

- [ ] **Step 4.1: /simplify を走らせて Phase C 変更を軽く棚卸し**

Run: `claude -p /simplify` (対話なしで実行できる場合) もしくは手動で `git diff` をかぶせてレビュー。
Expected: Phase C 内で 3 subagent (Reuse / Quality / Efficiency) のレビューを 1 回回す。発見は Phase C 内修正 or backlog 追記で処理。

**Note**: 実装時に /simplify が自動化されていない場合はスキップ可 (手動 diff レビューで代替)。

- [ ] **Step 4.2: `report.md` を作成**

`docs/superpowers/refactoring-2026-04-18/phase-c-dry/report.md` を新規作成:

```markdown
# Phase C — DRY / 重複排除 Report

**Status**: ✅ Done (2026-04-XX)

## 成果物

| Task | Commit | 内容 |
|---|---|---|
| 1 | `<sha>` | `BaseRepository._bulk_upsert_by_natural_key` 追加 + Financial/Valuation delegate 化 |
| 2a | `<sha>` | `FilingSource(StrEnum)` 追加 + `FilingRepository.bulk_upsert(source=FilingSource)` |
| 2b | `<sha>` | `FilingSourceAdapter` + `_sync` + `_map_sec_record` / `_map_edinet_record` |
| 3a | `<sha>` | CLI `_handle_show` を `get_with_items` に移行 |
| 3b | `<sha>` | `WatchlistService.get_watchlist` / `list_items` 削除 + master.md ルール追補 |

## テスト

- 新規: BaseRepo 4 + FilingSyncInternal 5 = **9 tests 追加**
- 既存: 737 → 変更後 746 tests (API 不変で全 PASS)
- coverage: 96% 維持

## 削減効果

- `FinancialRepository.bulk_upsert` : 15 行 → 6 行 (delegate)
- `ValuationRepository.bulk_upsert` : 15 行 → 6 行 (delegate)
- `FilingSyncService.update_from_sec` : 50 行 → 10 行 (adapter 組立)
- `FilingSyncService.update_from_edinet` : 50 行 → 13 行 (adapter 組立)
- `WatchlistService` : 2 methods (計 6 行) 削除

## Phase D からの Backlog 消費

- [x] `services/filing_sync.py` の update_from_sec/edinet 重複 → `_sync` で集約
- [x] `FinancialRepository.bulk_upsert` / `ValuationRepository.bulk_upsert` → helper で delegate
- [x] `WatchlistService.get_watchlist` / `list_items` → 削除 (master rule 例外適用)
- [x] (Phase B から繰上げ) `FilingRepository.bulk_upsert(source=)` stringly-typed → enum 化

## Phase C 中に発見した Backlog (次 Phase 以降)

(該当時に記載)

## 参照

- Spec: [design.md](design.md)
- Master tracker: [../master.md](../master.md)
```

実装時に `<sha>` を `git log --oneline` から埋める。

- [ ] **Step 4.3: `master.md` 進捗表を更新**

`docs/superpowers/refactoring-2026-04-18/master.md` の Phase 進捗表 (行 11-17) の Phase C 行を以下に置換:

```markdown
| 2 | C — 重複排除 (DRY) | 類似パターンの統合・共通ヘルパー抽出 | ✅ **Done** | [design.md](phase-c-dry/design.md) | [plan.md](phase-c-dry/plan.md) | [report.md](phase-c-dry/report.md) |
```

Backlog セクションの「Phase C (DRY) 候補」3 項目はすべて消費したのでセクションごと削除 (もしくは「✅ Phase C で消費済」コメントに置換)。残る Backlog は Phase B / Phase E / Phase D follow-up 分。

- [ ] **Step 4.4: 最終コミット**

```bash
git add docs/superpowers/refactoring-2026-04-18/phase-c-dry/report.md \
        docs/superpowers/refactoring-2026-04-18/master.md
git commit -m "$(cat <<'EOF'
docs(refactor): Phase C done — DRY consolidation complete

- BaseRepository._bulk_upsert_by_natural_key / FilingSourceAdapter / _sync を導入
- Financial/Valuation.bulk_upsert を 1 行 delegate 化
- FilingSyncService を adapter pattern に集約
- WatchlistService の旧 API 2 methods を削除
- 746 tests PASS, coverage 96% 維持

Phase C completion. Backlog の Phase C 候補 3 件 + Phase B FilingSource stringly-typed を消費。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4.5: branch 最終確認**

Run: `git log --oneline -10`
Expected: Task 1 → 2a → 2b → 3a → 3b → 4 の 6 commits が直列に並ぶ

Run: `uv run pytest`
Expected: 全 746 tests PASS

---

## 受け入れ基準 (spec 再掲)

1. ✅ `FinancialRepository.bulk_upsert` / `ValuationRepository.bulk_upsert` が 1 行 delegate に縮む
2. ✅ `FilingSyncService.update_from_sec` / `update_from_edinet` が共通 `_sync(adapter, ...)` に集約
3. ✅ `WatchlistService.get_watchlist` / `list_items` が削除、CLI + Web が `get_with_items` 統一
4. ✅ 既存 737 tests 全 PASS + 新規 9 tests で helper/adapter を検証
5. ✅ 外部 public API の挙動に regression なし

---

## 実行 Note

- Task 間に依存なし (順序変更可)
- Task 2a と 2b は独立してテスト可能だが enum → signature → adapter の順が自然
- Task 3a と 3b は必ず 3a → 3b の順 (3a 完了前に 3b を打つと src 内 caller 残る)
- 各 Task commit 後 `uv run pytest` PASS を確認してから次 Task へ
