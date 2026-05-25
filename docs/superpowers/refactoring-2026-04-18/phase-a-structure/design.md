# Phase A: 構造改善 — 設計書

**Status**: Draft (2026-04-25)
**Scope**: pageindex_service.py 分割 + Phase B/D 積み残し回収 (Comprehensive)
**Branch**: master (Phase A 専用 branch を作成予定)

---

## 1. Goal

Phase A は本リファクタリングプロジェクトの「構造改善」フェーズ。
2 つの目的を 1 Phase で達成する:

1. **構造改善**: 514 行に肥大化した `services/pageindex_service.py` を責務別の
   サブパッケージに分割し、各モジュールを 100〜250 行に収める
2. **Phase B/D 積み残し回収 (Comprehensive 案)**: master.md の Backlog に
   残っていた 4 項目をまとめて消費する
   - TypedDict 化 (valuation/metrics dict)
   - `_valuation_to_row` 型精緻化
   - cli/web の docstring Google 化未完箇所
   - `TargetRepository.bulk_add` の returning 化
   - `AppState.dispose` の並列 close 化

---

## 2. Architecture

### 2.1 PageIndex サブパッケージ (A-1)

旧構造:

```
src/stock_analyze_system/services/pageindex_service.py    # 514 行
```

新構造:

```
src/stock_analyze_system/services/pageindex/
├── __init__.py        # 公開 API (PageIndexService + 4 dataclass) を re-export
├── compat.py          # _install_pypdf_compat + pageindex lib の try/except import
├── models.py          # BuildTiming / QueryTiming / BuildResult / QueryResult
├── tree_utils.py      # 5 個の module-level helper (_count_nodes ほか)
├── prompts.py         # _DOCUMENT_GUARDRAIL_* + ビルド/クエリプロンプト定数
└── service.py         # PageIndexService 本体 + _build_semaphore
```

import 互換性方針: **shim を残さず全 import を新パスに置換** (10 箇所)。

### 2.2 TypedDict 導入 (A-2)

`services/valuation.py` の上部 (`from __future__` 直後) に 2 つの TypedDict を
配置し、3 関数の戻り型を精緻化する。

```python
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
```

戻り型変更:
- `compute_valuation_from_financials` `dict[str, Any]` → `ValuationRow`
- `compare_valuations` `list[dict[str, Any]]` → `list[ValuationRow]`
- `compute_per_range` `dict[str, float | None]` → `PerRangeDict`
- `compute_group_deviation` は `_zscore` 列を動的追加するため **据え置き**
  (`total=False` TypedDict を導入すると表現力が弱まり可読性が下がる)

### 2.3 Phase B closure (A-3)

未完項目をまとめて 1 task で処理:

| ファイル | 内容 |
|---|---|
| `cli/valuation.py:125` | `_valuation_to_row(v)` の `v` を `Valuation` に注釈 (TYPE_CHECKING import 追加) |
| `cli/watchlist.py` | `_handle_create / list / show / add / remove` の 5 関数に 1 行 docstring 追加 |
| `cli/serve.py` | `register_parser` / `handle` に Google スタイル docstring 追加 |
| `web/app.py` | `_validate_config` 以外 (`create_app`, `_setup_*` 系) に 1 行 docstring 追加 |

### 2.4 `bulk_add` returning 化 (A-4)

`repositories/target.py:bulk_add` を SELECT + INSERT の 2 query から
SQLite native UPSERT + RETURNING の 1 query に置換。

旧 (簡略):
```python
async def bulk_add(self, records: list[dict]) -> int:
    if not records:
        return 0
    incoming_ids = [r["company_id"] for r in records]
    stmt = select(AnalysisTarget.company_id).where(...)
    existing_ids = set((await self._session.execute(stmt)).scalars().all())
    new_rows = [r for r in records if r["company_id"] not in existing_ids]
    if not new_rows:
        return 0
    await self._bulk_upsert_native(new_rows, index_elements=["company_id"], update_columns=[])
    return len(new_rows)
```

新 (簡略):
```python
async def bulk_add(self, records: list[dict]) -> int:
    if not records:
        return 0
    stmt = (
        sqlite_insert(AnalysisTarget)
        .values(records)
        .on_conflict_do_nothing(index_elements=["company_id"])
        .returning(AnalysisTarget.company_id)
    )
    result = await self._session.execute(stmt)
    return len(result.scalars().all())
```

戻り値 semantic は不変 (実際に追加された件数)。
required: SQLite 3.35+ (Python 3.12 同梱の sqlite3 は 3.45+ で問題なし)。

### 2.5 `AppState.dispose` 並列化 (A-5)

`web/dependencies.py:73` の `dispose` を sequential から並列に変更。
close 対象は実装上 **HTTP client 3 つ (sec/edinet/fmp) + DB engine = 計 4 op**。
master.md の "db/llm/pdf" 記述は実装と差異があり、本 design では実装に合わせる。

```python
async def dispose(self) -> None:
    op_names: list[str] = []
    close_calls: list[Awaitable] = []
    for name, client in (
        ("sec", self.clients.sec),
        ("edinet", self.clients.edinet),
        ("fmp", self.clients.fmp),
    ):
        close_fn = getattr(client, "close", None)
        if close_fn is not None:
            op_names.append(name)
            close_calls.append(close_fn())
    op_names.append("engine")
    close_calls.append(self.engine.dispose())

    results = await asyncio.gather(*close_calls, return_exceptions=True)
    for op, result in zip(op_names, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("dispose: %s close failed: %s", op, result)
```

例外処理方針 (R7 設計判断): **(α) silent log + 例外は飲み込む** を採用。
shutdown パスでは「閉じれるものは閉じる」を優先し、raise しない。

---

## 3. Components & Data Flow

### 3.1 PageIndex モジュール責務

| モジュール | 責務 | 公開シンボル | 依存 |
|---|---|---|---|
| `compat.py` | `pypdf → PyPDF2` エイリアス、`pageindex` lib の optional import | `PageIndex`, `PAGEINDEX_AVAILABLE` | 標準 lib のみ |
| `models.py` | 戻り値 dataclass | `BuildTiming`, `QueryTiming`, `BuildResult`, `QueryResult` (各 `to_dict` / `__str__` / `format_cli` 含む) | 標準 lib のみ |
| `tree_utils.py` | tree 操作の純粋 helper | `_count_nodes`, `_collect_node_map`, `_node_page`, `_extract_page_count`, `_strip_text` | 標準 lib のみ |
| `prompts.py` | プロンプト定数 | `_DOCUMENT_GUARDRAIL_JA`, `_DOCUMENT_GUARDRAIL_EN`, build/query プロンプト template | 標準 lib のみ |
| `service.py` | `PageIndexService` 本体 + `_build_semaphore` | `PageIndexService` | `compat`, `models`, `tree_utils`, `prompts`, 既存外部依存 (`repositories.doc_index` ほか) |
| `__init__.py` | 公開 API の re-export | `PageIndexService`, `BuildResult`, `QueryResult`, `BuildTiming`, `QueryTiming` | 上記 5 モジュール |

### 3.2 依存方向 (循環なし)

```
compat.py        ← 一番下 (外部 lib import)
   ↑
models.py        ← 純粋データ
prompts.py       ← 純粋定数
tree_utils.py    ← 純粋関数
   ↑
service.py       ← 上記 4 つを集約、PageIndexService 本体
   ↑
__init__.py      ← 公開 API の re-export
```

下位モジュールは上位モジュールを import しない。

### 3.3 import 置換対象 (10 箇所)

| 旧 path | 新 path | 場所 |
|---|---|---|
| `services.pageindex_service import PageIndexService` | `services.pageindex import PageIndexService` | `cli/container.py:111`, `cli/rag.py:105`, `services/rag_service.py:18` |
| `services.pageindex_service import QueryResult` | `services.pageindex import QueryResult` | `services/rag_service.py:11`, `tests/unit/services/test_rag_service.py:9`, `tests/unit/cli/test_rag_cli.py:10` |
| `services.pageindex_service import _count_nodes, _collect_node_map` | `services.pageindex.tree_utils import _count_nodes, _collect_node_map` | `scripts/rebuild_index.py:10` |
| `services.pageindex_service import (...)` | `services.pageindex import (...)` | `scripts/rag_inference_test.py:27`, `tests/unit/services/test_pageindex_service.py:15` |
| `services import pageindex_service as pageindex_module` | `services.pageindex import service as pageindex_module` | `tests/unit/services/test_pageindex_service.py:14` (monkeypatch ターゲット変更) |

---

## 4. Testing Strategy

### 4.1 振る舞い不変 task (A-1〜A-3)

新規テスト追加なし。既存テストの import 追従のみ。

| Task | 確認テスト | 期待 |
|---|---|---|
| A-1 | `tests/unit/services/test_pageindex_service.py`, `test_rag_service.py`, `tests/unit/cli/test_rag_cli.py` | 0 件失敗・0 件 skip 増加 |
| A-2 | `tests/unit/services/test_valuation_service.py` (既存 21 ケース) | green |
| A-3 | `tests/unit/cli/test_valuation_cli.py`, `test_watchlist_cli.py`, `test_serve_cli.py`, `tests/unit/web/test_app.py` | green |

### 4.2 振る舞い変更 task (A-4 / A-5) — TDD

**A-4 新規テスト**:
1. `test_bulk_add_returns_actual_inserted_count_under_concurrent_duplicate`
2. `test_bulk_add_skips_existing_via_on_conflict`

既存 4 ケース (`tests/unit/repositories/test_target_repo.py`) も green を維持。

**A-5 新規テスト**:
1. `test_dispose_invokes_gather_with_all_close_calls` — `asyncio.gather` を mock し、4 op (sec/edinet/fmp の close + engine.dispose) すべてが 1 回の `gather` 呼び出しに渡されることを assert (構造検証、timing 非依存)
2. `test_dispose_continues_when_one_client_close_raises` — 1 client の close を `side_effect=Exception(...)` にしても、他 3 op が呼ばれることを `AsyncMock.called` で確認 + `logger.warning` が呼ばれることを assert

### 4.3 実行コマンド

```bash
# 各 task 完了時 (touched layer)
scripts/infisical-run uv run pytest tests/unit/services/ -q   # A-1, A-2
scripts/infisical-run uv run pytest tests/unit/cli/ -q        # A-1, A-3
scripts/infisical-run uv run pytest tests/unit/web/ -q        # A-3, A-5
scripts/infisical-run uv run pytest tests/unit/repositories/test_target_repo.py -q  # A-4

# Phase A 完了時の最終 green 確認
scripts/infisical-run uv run pytest tests/unit -q
scripts/infisical-run uv run ruff check src/
```

---

## 5. Risk & Rollback

### 5.1 リスクマトリクス

| # | リスク | 発生可能性 | 影響 | 対策 |
|---|---|---|---|---|
| R1 | PageIndex 分割で循環 import | 中 | High | `compat → models/prompts/tree_utils → service → __init__` の片方向依存を design で明示。実装前に各モジュールの import 文をレビュー |
| R2 | `pageindex_service.py` 削除後の import 残存で runtime ImportError | 中 | High | `grep -rn 'pageindex_service' src/ tests/ scripts/` を CI 前に必ず実行。受入条件 #3 #4 で gate |
| R3 | tests の monkeypatch ターゲット書き換え漏れ | 中 | Medium | `tests/unit/services/test_pageindex_service.py` の `pageindex_service as pageindex_module` を手動書き換え + 該当テスト green 確認 (monkeypatch が効かないと assertion 結果が変わるため検出可) |
| R4 | TypedDict 化で既存呼び出し側に型エラー | 低 | Low | runtime には dict、`dict[str, Any]` ⊃ TypedDict の包含関係。ruff のみ使用 (mypy 未導入) のため runtime 影響 0 |
| R5 | `bulk_add` returning 化で SQLite 3.35 未満エラー | 低 | High | Python 3.12 同梱 sqlite3 は 3.45+。本プロジェクト dev/prod とも該当 |
| R6 | `bulk_add` ON CONFLICT で UNIQUE 以外の制約違反が silent skip | 低 | Medium | `index_elements=["company_id"]` を明示 → company_id UNIQUE 違反のみ skip。他は raise (SQLAlchemy 通常挙動) |
| R7 | `dispose` の `gather(return_exceptions=True)` で例外サイレント | 中 | Medium | (α) 案採用: `logger.warning` で記録、raise しない。理由は §2.5 |
| R8 | `dispose` 並列化で close 順序依存問題 | 低 | Low | shutdown パスのため新規 req は既に停止。順序非依存と判断 |

### 5.2 Rollback プラン

各 task が独立 commit のため、問題発生時は `git revert <commit>` で個別戻し可能。

| Task | Rollback コスト | 影響範囲 |
|---|---|---|
| A-1 PageIndex 分割 | 高 | 5 src + 3 test + 2 script |
| A-2 TypedDict | 低 | 1 ファイル |
| A-3 Phase B closure | 低 | 4 ファイル (docstring/型のみ) |
| A-4 bulk_add | 低 | 1 src + 1 test |
| A-5 dispose | 低 | 1 src + 1 test |

A-1 が最大コストのため、**最初に実装し即時 CI green 確認後に他 task に進む**。

### 5.3 Task 順序

```
1. A-1 PageIndex 分割
2. A-2 TypedDict 化       ┐
3. A-3 Phase B closure    ├─ A-1 完了後は依存なし、順序自由
4. A-4 bulk_add returning ┤
5. A-5 dispose 並列化     ┘
```

実装順は `1 → 2 → 3 → 4 → 5` (構造系 → 型系 → docstring → 性能系の順で risk 高→低)。

---

## 6. Out of Scope

| 項目 | 理由 | 後続 |
|---|---|---|
| `mypy` / `pyright` 導入 | TypedDict 化だけでは効果薄、他層整備が必要 | 別 Phase 検討 |
| `BaseRepository._bulk_upsert_native` の CHUNK_SIZE 化 | 現状 N≤500 安全、N=3000+ 運用予定なし | Phase D continuation |
| pageindex 以外の大ファイル分割 (`cli/rag.py` 236 行ほか) | outlier ではない、責務分離必要性低 | 必要が出たら個別判断 |
| `compute_group_deviation` の TypedDict 化 | `_zscore` 動的追加のため `total=False` 必要、可読性低下 | 据え置き |
| `cli/container.py` の `PageIndexService` import 遅延化 | 現状で問題なし | 不要 |
| screening_result dict 等の TypedDict 化 | Phase 5/6 機能、まず valuation で pattern 確立 | 別 Phase 検討 |

---

## 7. 成功条件

1. 全 unit tests green (skip 増加なし)
2. ruff `src/` clean
3. `src/stock_analyze_system/services/pageindex_service.py` が存在しない
4. `grep -rn 'pageindex_service' src/ tests/ scripts/` が新パス (`pageindex/...`) のみにヒット (旧 path 参照 0)
5. `services/valuation.py` の `compute_valuation_from_financials` / `compare_valuations` / `compute_per_range` の戻り型が `dict[str, Any]` ではなく TypedDict
6. `cli/{watchlist,serve,valuation}.py`, `web/app.py` の Phase B 残 docstring がすべて Google スタイル
7. `repositories/target.py:bulk_add` 内に `select(...)` の事前 SELECT が存在しない
8. `web/dependencies.py:dispose` 内で `asyncio.gather` を使用
9. `master.md` の Phase A 行が ✅ Done に更新されている
10. `phase-a-structure/report.md` が存在し、5 task 全 commit hash が記録されている
11. ドキュメント更新 (master.md / report.md / current-status-YYYY-MM-DD.md) がコミットに含まれている

---

## 8. ドキュメント更新 (Phase A 完了時)

1. **`docs/superpowers/refactoring-2026-04-18/master.md`**
   - Phase A 進捗表を `✅ Done (YYYY-MM-DD)` に更新
   - design / plan / report リンク追加
   - "Phase D follow-up" セクションから消費した 2 項目 (bulk_add / dispose) を「消費した項目」一覧へ移動

2. **`docs/superpowers/refactoring-2026-04-18/phase-a-structure/report.md` (新規)**
   - Phase B report.md と同形式
   - 各 Task の commit hash + 変更ファイル一覧
   - PageIndex 旧→新 ファイル mapping 表
   - 新規追加した TypedDict 一覧
   - Phase D follow-up 2 件の Before/After サマリ

3. **`docs/superpowers/refactoring-2026-04-18/current-status-YYYY-MM-DD.md` (新規)**
   - Phase A 完了時点のスナップショット

---

## 9. サイズ感

| Task | 推定 LOC delta | 推定テスト delta |
|---|---|---|
| A-1 PageIndex 分割 | +0 / -0 (移動のみ) | 既存追従、新規 0 |
| A-2 TypedDict | +25 / -3 | 0 |
| A-3 Phase B closure | +30 / -10 | 0 |
| A-4 bulk_add | +10 / -10 | +2 |
| A-5 dispose | +15 / -7 | +2 |

合計: 純増 **+50 LOC 程度**、新規テスト **4 件**。Phase A 全体で 1 PR (5 commit)。
