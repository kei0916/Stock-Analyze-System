# Phase A: 構造改善 — 実施記録

**Status**: ✅ Done (2026-04-25)

各 Task 完了時に追記。記録項目: 変更ファイル / commit hash / 新規追加した
モジュール・型 / 振る舞い変更点 / 備考。

---

## Task 記録

### Task 1: A-1 PageIndex サブパッケージ分割 — ✅ Done (2026-04-25)

- 変更:
  - 新規: `src/stock_analyze_system/services/pageindex/{__init__,compat,models,tree_utils,prompts,service}.py`
  - 削除: `src/stock_analyze_system/services/pageindex_service.py`
  - import 置換: `services/rag_service.py` x2, `cli/container.py`, `cli/rag.py`,
    `tests/unit/services/test_pageindex_service.py` x2 (monkeypatch ターゲット含む),
    `tests/unit/services/test_rag_service.py`, `tests/unit/cli/test_rag_cli.py`,
    `scripts/rebuild_index.py`, `scripts/rag_inference_test.py`
- 結果: 全 unit tests green、ruff clean、`grep -rn 'pageindex_service' src/ tests/ scripts/` が 0 件
- commit: `847a640`

### Task 2: A-2 TypedDict 化 — ✅ Done (2026-04-25)

- 変更: `src/stock_analyze_system/services/valuation.py`
  (`ValuationRow` / `PerRangeDict` 追加 + 3 関数の戻り型精緻化)
- 結果: `tests/unit/services/test_valuation_service.py` green、ruff clean
- commit: `eb27c5e`

### Task 3: A-3 Phase B closure — ✅ Done (2026-04-25)

- 変更:
  - `src/stock_analyze_system/cli/valuation.py` (`_valuation_to_row(v: Valuation)`)
  - `src/stock_analyze_system/cli/watchlist.py` (5 `_handle_*` に docstring)
  - `src/stock_analyze_system/cli/serve.py` (`register_parser` / `handle` docstring)
  - `src/stock_analyze_system/web/app.py` (`_add_security_headers` / `create_app` docstring)
- 結果: 全 unit tests green、ruff clean
- commit: `662c2d4`

### Task 4: A-4 bulk_add returning 化 — ✅ Done (2026-04-25)

- 変更:
  - `src/stock_analyze_system/repositories/target.py`
    (事前 SELECT 排除、`sqlite_insert(...).on_conflict_do_nothing(...).returning(...)` の 1 query 化)
  - `tests/unit/repositories/test_other_repos.py`
    (`test_target_bulk_add_intra_batch_duplicates`,
     `test_target_bulk_add_partial_existing_returns_only_new_count` 追加)
- 振る舞い変更: intra-batch dup を 1 件としてカウントするようになった
  (旧実装は `len(new_rows)` で over-count)
- 結果: 全 target テスト green
- commit: `6660231`

### Task 5: A-5 AppState.dispose 並列化 — ✅ Done (2026-04-25)

- 変更:
  - `src/stock_analyze_system/web/dependencies.py`
    (`asyncio.gather(*close_calls, return_exceptions=True)` 化、logger 導入)
  - `tests/unit/web/test_dependencies.py`
    (`test_dispose_invokes_gather_with_all_close_calls`,
     `test_dispose_continues_when_one_client_close_raises` 追加)
- 振る舞い変更: 4 op (sec/edinet/fmp + engine) が並列実行、例外は warning ログで silent 飲み込み (R7 α 案)
- 結果: 全 web テスト green
- commit: `6420ca5`

### Task 6: Docs update — ✅ Done (2026-04-25)

- 変更: master.md / report.md (本ファイル) / current-status-2026-04-25.md
- commit: (Task 6 commit 自身)

---

## PageIndex 旧→新 ファイル mapping

| 旧 (pageindex_service.py 内) | 新 (pageindex/ 内) | 行数 |
|---|---|---|
| `_install_pypdf_compat`, lib import block | `compat.py` | 〜50 |
| `BuildTiming`, `QueryTiming`, `BuildResult`, `QueryResult` | `models.py` | 〜60 |
| `_count_nodes`, `_collect_node_map`, `_node_page`, `_extract_page_count`, `_strip_text` | `tree_utils.py` | 〜65 |
| `_DOCUMENT_GUARDRAIL_JA`, `_DOCUMENT_GUARDRAIL_EN` | `prompts.py` | 〜15 |
| `PageIndexService` クラス + `_build_semaphore` | `service.py` | 〜250 |
| (公開 API re-export) | `__init__.py` | 〜15 |

## 新規追加した TypedDict

| ファイル | 名前 | キー数 | 用途 |
|---|---|---|---|
| `services/valuation.py` | `ValuationRow` | 9 | `compute_valuation_from_financials` / `compare_valuations` の戻り値要素 |
| `services/valuation.py` | `PerRangeDict` | 3 | `compute_per_range` の戻り値 |

## Phase D follow-up 2 件 — Before/After

### bulk_add returning 化 (A-4)
- Before: 事前 SELECT で existing_ids を取得 → INSERT (2 query) → `len(new_rows)` 返却 (intra-batch dup を over-count)
- After: `sqlite_insert(...).on_conflict_do_nothing(...).returning(company_id)` 1 query → 実際の insert 件数返却

### dispose 並列化 (A-5)
- Before: sec → edinet → fmp → engine の sequential await。1 失敗で残り skip
- After: `asyncio.gather(*close_calls, return_exceptions=True)` で並列実行。例外は warning ログ、後続継続

---

## Code-review nice-to-haves (Phase A 範囲外、後続 follow-up 候補)

Phase A 各 Task の code review で挙がった非ブロッキングの改善案 (本 Phase では未対応):

- **A-1**: `services/pageindex/__init__.py` の `_DOCUMENT_GUARDRAIL_JA` / `_DOCUMENT_GUARDRAIL_EN` re-export — 内部利用に限定するなら `__all__` から除外して private に戻す検討余地あり。
- **A-5**: `web/dependencies.py` の `dispose` warning ログに `exc_info=result` を渡してトレースバックを保存する余地あり (現状は `str(exc)` のみ)。shutdown 失敗診断時に有用。

これらは Phase A 受入条件の対象外。必要に応じて Phase D follow-up または別 Phase で扱う。

---

## Corrigendum (2026-04-26 / Codex review feedback)

Phase A 完了直後 (2026-04-25) の本 report に書いた「ruff (touched layer) clean」は、
**当時の検証スコープが `src/` に限定されていたため、`scripts/` を含めると不正確だった**。
独立検証として実施した Codex レビューが以下を発見:

- `scripts/rebuild_index.py` (Task 1 で import 置換した) が module-level に
  `print()` → `import sqlite3` を持っていたため `E402` (import not at top) で
  ruff fail。同じくハードコードされた filing_id=2 / company_id="US_AAPL" で
  `data/stock_analyze.db` に raw INSERT する debug snippet になっていた。
- `scripts/debug_verify_toc.py` (untracked, Phase A 中に発生した実験用 script) も
  `F541` (f-string without placeholders) で ruff fail、`/tmp/PageIndex` 直 import あり。

加えて、`tree_utils.py` の 5 helper は名前に `_` prefix が付いていながら
`scripts/rag_inference_test.py` / `scripts/rebuild_index.py` / 旧 `pageindex_service.py`
等から横断的に import されており、private 表記と実態の乖離があった。

**Follow-up commit `5d025c8` (2026-04-26)** で 5 つの根本原因を一括修正:

1. `tree_utils.py` の 5 helper を public 化 (`count_nodes` / `collect_node_map` /
   `node_page` / `extract_page_count` / `strip_text`)。`__init__.py` に re-export 追加、
   `PageIndexService.count_nodes` の冗長 wrapper 削除。
2. `scripts/rebuild_index.py` を `PageIndexService` + `DocumentIndexRepository` ベースの
   proper CLI に書き換え (filing-id/company-id/--dry-run、明示的 DB lifecycle)。
3. `scripts/verify_refactoring_phase.py` に `ruff check src tests scripts` gate を追加 →
   今後の phase で同種の "src だけ clean" 詐称を機械的に防止。
4. `scripts/debug_verify_toc.py` は untracked なので local 削除のみ (commit 不要)。

修正後: 780 unit tests green、ruff clean (`src+tests+scripts`)、
`verify_refactoring_phase.py` OK、`scripts/rebuild_index.py --help` 動作確認済み。

教訓: 「touched layer」と書く時は、検証コマンドの引数を文中に明記し、
machine-verifiable な形で記録に残す。「内部レビュー OK」≠「全領域 clean」。

---

## サマリー

| 指標 | Before (`a4ff84a`) | After (Phase A 完了) | 差分 |
|---|---|---|---|
| `pageindex_service.py` 行数 | 514 (1 ファイル) | 0 (削除、6 モジュールへ分配) | -514 / +500 (再分配) |
| 最大 service ファイル行数 | 514 | 〜250 (`pageindex/service.py`) | -264 |
| TypedDict 化された関数戻り型 | 0 | 3 | +3 |
| `_handle_*` 等の docstring 残課題 | 12 関数 | 0 | -12 |
| `bulk_add` query 数 | 2 (SELECT + INSERT) | 1 (UPSERT RETURNING) | -1 |
| `AppState.dispose` 並行度 | 1 (sequential) | 4 (parallel) | +3 |
| 全 unit tests | green | green | — |
| ruff (touched layer) | clean | clean (※完了時 `src/` のみ。`scripts/` を含めた完全 clean は follow-up `5d025c8` 後。Corrigendum 参照) | — |

---

## スコープ外 (次 Phase)

- `mypy` / `pyright` 導入 → 別 Phase
- `BaseRepository._bulk_upsert_native` の CHUNK_SIZE 化 (SQLite 32766 変数上限) → Phase D continuation
- pageindex 以外の大ファイル分割 (`cli/rag.py` 236 行ほか) → 必要が出た時点で個別判断
- `compute_group_deviation` の TypedDict 化 (`_zscore` 動的列) → 据え置き
- screening_result dict 等の TypedDict 化 → 別 Phase

---

## Phase A 完了 (2026-04-25)

- Task 1〜6 すべて完了
- 全 unit tests green
- ruff clean (Phase A 範囲で新規 error 0)
- design §成功条件 1〜11 すべて満たす
- 次 Phase: 未定 (master.md の Backlog を参照)
