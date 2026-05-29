# Project-wide Refactoring Tracker (2026-04-18 〜)

**Goal**: プロジェクト全体 (90 ファイル / 6,552 行 / テスト 718 件・カバレッジ 97%) を 5 軸で整理する。各 Phase は独立した spec → plan → 実装 → commit サイクルで完結させる。

**前提**: 2026-04-18 の test-coverage-strengthening で安全網 (97% カバレッジ) を整備済み。破壊的変更を安心して入れられる状態。

---

## Phase 進捗表

| Order | Phase | Focus | Status | Spec | Plan | Report |
|---|---|---|---|---|---|---|
| 1 | **D — パフォーマンス** | N+1 削減・hot path I/O 削減 | ✅ **Done** | [design.md](phase-d-performance/design.md) | [plan.md](phase-d-performance/plan.md) | [report.md](phase-d-performance/report.md) |
| 2 | C — 重複排除 (DRY) | 類似パターンの統合・共通ヘルパー抽出 | ✅ **Done** | [design.md](phase-c-dry/design.md) | [plan.md](phase-c-dry/plan.md) | [report.md](phase-c-dry/report.md) |
| 3 | **E — デッドコード削除** | 未使用 import・到達不能コード・未使用分岐の撤去 | ✅ **Done** | [design.md](phase-e-deadcode/design.md) | [plan.md](phase-e-deadcode/plan.md) | [report.md](phase-e-deadcode/report.md) |
| 4 | B — 可読性・命名 | 関数名・引数・コメント精査、スタイル統一 | ✅ **Done** | [design.md](phase-b-readability/design.md) | [plan.md](phase-b-readability/plan.md) | [report.md](phase-b-readability/report.md) |
| 5 | A — 構造改善 | 巨大ファイル分割 (`pageindex_service.py` 514 行)、依存整理 | ✅ **Done** | [design.md](phase-a-structure/design.md) | [plan.md](phase-a-structure/plan.md) | [report.md](phase-a-structure/report.md) |

**凡例**: ⚪ Pending / 🔵 In Progress / ✅ Done / ⏸️ Paused

---

## 最新更新

- 2026-04-25: [current-status-2026-04-25.md](current-status-2026-04-25.md)
  - Phase A (構造改善) 完了。`pageindex_service.py` 514 行を `services/pageindex/`
    6 モジュール (compat / models / tree_utils / prompts / service / __init__) に
    分割し、`ValuationRow` / `PerRangeDict` で valuation 戻り型を TypedDict 化、
    Phase B docstring 残課題を closure、`TargetRepository.bulk_add` を
    SQLite native UPSERT + RETURNING で 1 query 化、`AppState.dispose` を
    `asyncio.gather` で並列化。
  - Phase A の 5 commit: `847a640` (split) / `eb27c5e` (TypedDict) /
    `662c2d4` (Phase B closure) / `6660231` (bulk_add) / `6420ca5` (dispose)。
- 2026-04-24: [current-status-2026-04-24.md](current-status-2026-04-24.md)
  - Qwen3.6 切替後の LLM / RAG 安定化、security hardening review follow-up
    (stale bucket GC / PDF fetcher / PageIndex timeout)、`pypdf` 移行と
    direct PageIndex import compatibility、Web RAG throttling の UX 改善を記録。
  - `pytest -q -W error::DeprecationWarning -W error::RuntimeWarning`
    で `805 passed, 4 deselected` を確認。
  - 未対応 review 項目として、`rag_inference_test.py` の cache key 拡張と
    Web RAG tab の filing type 伝播を別節へ切り出し済み。
- 2026-04-23: [current-status-2026-04-23.md](current-status-2026-04-23.md)
  - PageIndex fallback / metadata の review follow-up、unauthenticated redirect
    への security headers 適用、external API `AsyncRateLimiter` の schedule
    drift 修正、Infisical wrapper の dotenv fallback 強制無効化を統合記録。
  - 追加記録: Ollama を user-level install として `0.21.1` へ更新。
    Qwen3.6 27B GGUF は Ollama `0.21.1` でも `qwen35` architecture
    未対応により generation 不可であり、現時点の実用ルートは llama.cpp 直接起動。
  - 追加記録: `LlmConfig` default、既定 LLM model/model_quality、
    RAG 手動検証 script、RAG timing fixture を
    `openai/Qwen3.6-27B-Q4_K_M.gguf` へ切替。
  - GitHub 記録対象 branch / commit の source of truth は
    `current-status-2026-04-23.md` の「GitHub 記録」節に追記。
- 2026-04-21: [current-status-2026-04-21.md](current-status-2026-04-21.md)
  - current branch の最終 snapshot として、Web security hardening /
    review follow-up、Phase C 完了、tracker/report 補正、latest verification を統合記録。
  - Secret management は Infisical 実行へ切り替え。通常 command は
    `env STOCK_ANALYZE_LOAD_DOTENV=0 infisical run --env=dev --path=/ -- <command>`
    を用い、repo-local `.env` fallback は後方互換用途に限定。
    手入力用の標準入口は [infisical-local-commands.md](infisical-local-commands.md)
    に記録した `scripts/infisical-run <command>`。
    GitHub 記録対象 commit は `current-status-2026-04-21.md` の
    「GitHub 記録」節に追記。
- 2026-04-20: [current-status-2026-04-20.md](current-status-2026-04-20.md)
  - GreenBoost / `llama-server` 検証の結論、`.htm` filing 対応、
    `FmpClient.is_available()` と `PageIndexService.query()` の follow-up bugfix、
    Web security hardening と review follow-up、未対応 review 項目を記録。
- 2026-04-20: [phase-c-dry/report.md](phase-c-dry/report.md)
  - Phase C の誤記録を再監査で補正したうえで、Task 1 → Task 2 → Task 3 を
    再実装し、tracker を `✅ Done` に更新。
- 2026-04-19: [current-status-2026-04-19.md](current-status-2026-04-19.md)
  - current branch の実装済み内容、review follow-up で反映済みの修正、RAG/PageIndex 周辺の follow-up 修正、fresh `pytest` 緑を記録。

---

## ルール

1. **Phase 間の境界**: 各 Phase 完了時に commit + テスト緑を必須。次 Phase 着手前に main へマージ。
2. **各 Phase 内の粒度**: 1 Task = 1 TDD サイクル = 1 commit。タスク完了ごとに Phase の `report.md` へ追記。
3. **スコープ固定**: 他 Phase の作業を先取りしない。発見した他 Phase の候補は master.md の「Backlog」に積む。
4. **後方互換**: public API (service/repository 外部メソッド) は Phase D〜B では不変。
   **例外** (Phase C で適用): Phase D で新 API (例: `get_with_items`) に置換された
   旧 method は、全 caller (src/tests 含む) が移行済みであれば削除可。
   削除対象は Phase C spec で明示する。Phase A でのみそれ以外の API 変更を許容 (spec で明示)。

---

## 確定済みの out-of-scope / 今後の課題

| 項目 | 理由 | 将来のトリガー |
|---|---|---|
| `run_daily_update` の並列化 | LLM + SEC filings でデッドロック発生、現状は意図的に直列 | GreenBoost 予約量削減では未解決。`llama-server` の総コンテキスト予算 (`-c 131072`, unified KV) と prompt サイズ見直し後に並列再実験 |

---

## Backlog (Phase 進行中に発見した候補)

Phase D /simplify レビューで発見。該当 Phase で扱う。

**Phase C (DRY):**
- 2026-04-20 再監査で判明した doc / code の不一致を補正し、
  同日中に Task 1 → Task 2 → Task 3 を再実装して完了。
- 消費した項目:
  `BaseRepository._bulk_upsert_by_natural_key`、
  `FilingSource` + `FilingSourceAdapter` + `FilingSyncService._sync()`、
  `watchlist show` の `get_with_items()` 移行と旧 service method 削除。

**Phase B (可読性):**
- 2026-04-25 完了。services/ingestion/cli/web 横断で履歴コメント 11 件を除去、
  対象 3 クラスタ (docstring Google 化 / fd: Any → "FinancialData" / CLI
  `_handle_*` 型注釈統一) を 3 実装 commit + 2 fixup commit に集約。
- 消費した項目:
  Bug #7 / Bug #4 / 新発見3 / 新発見1 / 新発見2 / 新発見5 / 新発見4 /
  Bug #16 / Bug #3 / Bug #17 / Bug #15 + 新1 / Bug #8 の 11 件履歴除去、
  `compute_valuation_from_financials` の `fd: Any → FinancialData`、
  `cli/{company,financial,rag,valuation}.py` の `_handle_*` 型注釈統一。
- Follow-up (Phase A で検討):
  - `_valuation_to_row(v)` の `v: "Valuation"` 精緻化
  - `cli/watchlist.py` 他 method の Google 化、`cli/serve.py` / `web/app.py`
    の周辺関数整備
- Post-review hardening:
  - `scripts/verify_refactoring_phase.py` を追加し、履歴ラベル残存と
    `master.md` の markdown link が git-tracked file を指すことを機械検証。
  - `compute_valuation_from_financials` の `FinancialData` 型注釈は
    `typing.get_type_hints()` で解決可能な runtime import に変更。

**Phase E (デッドコード):**
- 2026-04-24 完了。3 layer (repo / service / shared) で 11 個の未使用 public
  method / function を削除し、4 commit で集約。
- 消費した項目:
  `FilingRepository.find_by_accession` / `find_by_doc_id`、
  `WatchlistRepository.list_items`、`CompanyRepository.list_by_market`、
  `FinancialService.build_chart_data` (+ `_CHART_KEYS` / `_PCT_KEYS` / `_to_pct`)、
  `ValuationService.build_chart_data`、`RagService.ask_questions`、
  `metrics.peg_ratio` / `metrics.cagr`、
  `formatters.fmt_pct` / `formatters.fmt_ratio`。

**Phase D follow-up (性能・スケール):**
- `BaseRepository._bulk_upsert_native` で N×cols > 32766 (SQLite 変数上限) に達するとエラー。現状の使用 (N≤500) では安全だが、将来 N=3000+ の UPSERT を扱うなら CHUNK_SIZE=500 のループ化が必要。
- 2026-04-25 Phase A で消費した項目:
  - `TargetRepository.bulk_add` returning 化 (commit `6660231`) — 事前 SELECT 排除 + intra-batch dup の正確カウント
  - `AppState.dispose` 並列化 (commit `6420ca5`) — `asyncio.gather(return_exceptions=True)` で 4 op 同時実行、例外は warning ログ

---

## 参照

- 安全網の spec: [../specs/2026-04-18-test-coverage-strengthening-design.md](../specs/2026-04-18-test-coverage-strengthening-design.md)
- 旧 refactoring spec (完了済み): [../specs/2026-03-29-maintainability-refactoring-design.md](../specs/2026-03-29-maintainability-refactoring-design.md)
