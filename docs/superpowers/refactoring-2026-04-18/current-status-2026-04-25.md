# Current Status (2026-04-25)

## Scope

2026-04-25 時点の branch
`codex-refactoring-followups-20260419` に載っている Phase A (構造改善)
完了状況を、2026-04-24 snapshot 以降の差分として追跡する。

この snapshot は project-wide refactoring tracker
[`master.md`](master.md) の Phase A 完了報告を中心とする。
過去 snapshot (2026-04-23 / 2026-04-24) の対象範囲は維持され、本 snapshot で
重複記載しない。

---

## 実装・修正済み

### Phase A (構造改善) 完了

5 task / 5 commit で完了 (詳細は
[`phase-a-structure/report.md`](phase-a-structure/report.md))。

- **A-1 PageIndex サブパッケージ分割** (`847a640`):
  `services/pageindex_service.py` (514 行) を
  `services/pageindex/{compat,models,tree_utils,prompts,service,__init__}.py`
  6 モジュールへ分割。依存方向は `compat → models/prompts/tree_utils → service → __init__` の一方向。
  9 import 元 (`services/rag_service.py` x2、`cli/container.py`、`cli/rag.py`、
  4 テストファイル、2 scripts) を新パスへ更新。
- **A-2 valuation 戻り値の TypedDict 化** (`eb27c5e`):
  `services/valuation.py` の 3 関数戻り型を `ValuationRow` (9 keys) /
  `PerRangeDict` (3 keys) に置換。`compute_group_deviation` は動的キー
  (`<metric>_zscore`) のため対象外。
- **A-3 Phase B docstring 残課題の closure** (`662c2d4`):
  `cli/valuation.py` の `_valuation_to_row(v: Valuation)` 型注釈、
  `cli/watchlist.py` 5 `_handle_*`、`cli/serve.py` / `web/app.py` 各 2 関数、
  `pageindex/service.py` の `count_nodes` docstring 拡張、
  `pyproject.toml` のステイル参照 (`pageindex_service.py → services/pageindex/compat.py`) を整備。
- **A-4 `TargetRepository.bulk_add` の returning 化** (`6660231`):
  事前 SELECT を排除、`sqlite_insert(AnalysisTarget).values(records).on_conflict_do_nothing(index_elements=["company_id"]).returning(AnalysisTarget.company_id)` で 1 query 化。
  intra-batch dup を 1 件として正確にカウントするようになった (旧実装は over-count)。
  TDD で `test_target_bulk_add_intra_batch_duplicates` /
  `test_target_bulk_add_partial_existing_returns_only_new_count` を追加。
- **A-5 `AppState.dispose` の並列化** (`6420ca5`):
  sec/edinet/fmp client `close` + `engine.dispose` を
  `asyncio.gather(*close_calls, return_exceptions=True)` で並列実行。
  個別 close 例外は `logger.warning` で記録し raise しない (R7 α 案)。
  TDD で `test_dispose_invokes_gather_with_all_close_calls` /
  `test_dispose_continues_when_one_client_close_raises` を追加。

対象ファイル (Phase A 全体):

- `src/stock_analyze_system/services/pageindex/{__init__,compat,models,tree_utils,prompts,service}.py` (新規)
- `src/stock_analyze_system/services/rag_service.py`
- `src/stock_analyze_system/services/valuation.py`
- `src/stock_analyze_system/cli/container.py`
- `src/stock_analyze_system/cli/rag.py`
- `src/stock_analyze_system/cli/valuation.py`
- `src/stock_analyze_system/cli/watchlist.py`
- `src/stock_analyze_system/cli/serve.py`
- `src/stock_analyze_system/web/app.py`
- `src/stock_analyze_system/web/dependencies.py`
- `src/stock_analyze_system/repositories/target.py`
- `pyproject.toml`
- `tests/unit/services/test_pageindex_service.py`
- `tests/unit/services/test_rag_service.py`
- `tests/unit/cli/test_rag_cli.py`
- `tests/unit/repositories/test_other_repos.py`
- `tests/unit/web/test_dependencies.py`
- `scripts/rebuild_index.py`
- `scripts/rag_inference_test.py`

削除:

- `src/stock_analyze_system/services/pageindex_service.py`

---

## RED-GREEN 記録

- A-4 `bulk_add` の intra-batch dup over-count:
  - RED: `test_target_bulk_add_intra_batch_duplicates` は旧実装で `assert 3 == 2` で失敗。
  - GREEN: `sqlite_insert(...).on_conflict_do_nothing(...).returning(...)` で 1 query 化、実 insert 件数を返却。
- A-5 `dispose` の sequential await:
  - RED: `test_dispose_invokes_gather_with_all_close_calls` は `asyncio.gather` を呼ばないので fail、`test_dispose_continues_when_one_client_close_raises` は edinet 例外で残り 2 op が skip され fail。
  - GREEN: `asyncio.gather(return_exceptions=True)` 化、4 op 並列実行 + warning ログ。

---

## Verification

すべて Infisical wrapper 経由で実行した。

- `scripts/infisical-run uv run pytest tests/unit/repositories/test_other_repos.py -v -k target`
  - 結果: 4 passed (`test_target_list_and_find`, `test_target_bulk_add`,
    `test_target_bulk_add_intra_batch_duplicates`,
    `test_target_bulk_add_partial_existing_returns_only_new_count`)
- `scripts/infisical-run uv run pytest tests/unit/web -q`
  - 結果: `100 passed`
- `scripts/infisical-run uv run pytest tests/unit -q`
  - 結果: full suite green
- `scripts/infisical-run uv run ruff check src/`
  - 結果: clean
- `grep -rn 'pageindex_service' src/ tests/ scripts/`
  - 結果: 0 hit (旧 module への参照なし)

---

## 未対応 review / follow-up

2026-04-25 時点で Phase A 範囲外として残した non-blocking 改善:

- `services/pageindex/__init__.py` の `_DOCUMENT_GUARDRAIL_JA` / `_DOCUMENT_GUARDRAIL_EN` re-export を `__all__` から除外して private に戻すか検討。
- `web/dependencies.py` の `dispose` warning ログに `exc_info=result` を付与してトレースバックを保存。

過去 snapshot で挙がっていた未対応項目 (`scripts/rag_inference_test.py` の cache key 拡張、Web RAG tab の filing type 伝播) は本 snapshot の対象外として継続。

---

## GitHub 記録

2026-04-25 の記録対象:

- repository: `kei0916/Stock-Analyze-System`
- branch: `codex-refactoring-followups-20260419`
- remote: `origin`
- 内容:
  - Phase A (構造改善) 完了 — 5 task / 5 commit (`847a640` / `eb27c5e` / `662c2d4` / `6660231` / `6420ca5`) + 本 Task 6 (docs commit)

この snapshot 以降の GitHub 上の source of truth は、上記 branch に push された
commit とする。
