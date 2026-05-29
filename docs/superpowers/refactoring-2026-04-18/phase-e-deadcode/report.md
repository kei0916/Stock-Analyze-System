# Phase E: デッドコード削除 — 実施記録

**Status**: ✅ Done (2026-04-24)

各 Task 完了時に追記。記録項目: 変更ファイル / commit hash / 削除対象 / 備考。

---

## Task 記録

### Task 1: Repo layer dead code deletion — ✅ Done (2026-04-24)

- 変更:
  - `src/stock_analyze_system/repositories/filing.py` (`find_by_accession`, `find_by_doc_id` 削除)
  - `src/stock_analyze_system/repositories/watchlist.py` (`list_items` 削除)
  - `src/stock_analyze_system/repositories/company.py` (`list_by_market` 削除)
  - 対応テスト 4 本削除 + `test_deletes_item` を `find_item` 利用に書き換え。
- すべて Phase D で `find_existing_*` / `get_with_items` / `find_item` に置換済みの旧 API。
- 結果: 62 → 57 passed (-5 削除分)、95 行削減。
- commit: `d407238`

### Task 2: Service layer dead code deletion — ✅ Done (2026-04-24)

- 変更:
  - `src/stock_analyze_system/services/financial.py`
    (`build_chart_data` + `_CHART_KEYS` / `_PCT_KEYS` / `_to_pct` 削除)
  - `src/stock_analyze_system/services/valuation.py` (`build_chart_data` 削除)
  - `src/stock_analyze_system/services/rag_service.py` (`ask_questions` 削除)
  - `src/stock_analyze_system/services/metrics.py` (`peg_ratio`, `cagr` 削除)
  - `src/stock_analyze_system/services/job.py` (Step 2.12 follow-up: 未使用 `Any` import 削除)
  - 対応テスト 8 本削除。
- Web 層は metrics dict を直接 render しており chart adapter は採用されず。
  自由質問 API は `ask_question` (単数) を全箇所で利用済み。
- 結果: 223 → 215 passed (-8 削除分)、144 行削減。
- commit: `91b9871`

### Task 3: Shared layer dead code deletion — ✅ Done (2026-04-24)

- 変更:
  - `src/stock_analyze_system/shared/formatters.py` (`fmt_pct`, `fmt_ratio` 削除)
  - `tests/unit/test_shared_formatters.py` (`TestFmtPct`, `TestFmtRatio` 削除)
- `fmt_number` / `fmt_large` は CLI/Web で継続利用するため温存。
- 結果: 21 → 12 passed (-9 削除分)、38 行削減。
- commit: `bc56878`

### Task 4: Docs update — ✅ Done (2026-04-24)

- 変更:
  - `docs/superpowers/refactoring-2026-04-18/master.md`
    (Phase E を ✅ Done に更新、Backlog を消費済み項目へ書き換え)
  - 本ファイル `report.md` 新規作成。

---

## サマリー

| 指標 | Before (master) | After (Phase E) | 差分 |
|---|---|---|---|
| 削除した public method/function 数 | — | 11 | — |
| 全 unit tests 件数 | 787 (推定) | 773 | -14 (削除テスト分) |
| 全 unit tests 結果 | green | green | — |
| ruff (touched layer) | clean | clean | — |

## 削除した API 一覧

### repo (4 個 / commit `d407238`)
- `FilingRepository.find_by_accession` → `find_existing_accessions` に統合
- `FilingRepository.find_by_doc_id` → `find_existing_doc_ids` に統合
- `WatchlistRepository.list_items` → `find_item` / `get_with_items` に置換
- `CompanyRepository.list_by_market` → 未採用機能 (caller 0)

### service (5 method + 3 ヘルパー / commit `91b9871`)
- `FinancialService.build_chart_data` (+ `_CHART_KEYS`, `_PCT_KEYS`, `_to_pct`)
- `ValuationService.build_chart_data`
- `RagService.ask_questions` (複数質問版)
- `metrics.peg_ratio`
- `metrics.cagr`

### shared (2 個 / commit `bc56878`)
- `formatters.fmt_pct`
- `formatters.fmt_ratio`

---

## 温存した「死んでそうで生きてる」API

design.md で精査し、削除対象外と判定した 5 件は変更なし:
- `FilingRepository.list_by_company` (Web detail で使用中)
- `WatchlistService.add_to_watchlist` の例外伝播経路
- `metrics.dividend_payout_ratio` の `dps`/`eps` フォールバック分岐
- `metrics.per` の `market_cap`/`net_income` フォールバック分岐
- `valuation.compute_per_range` (CLI summary で使用中)

---

## 備考

- 全 commit は master rule §4 例外条項 (Phase D で新 API 置換済み旧 method の削除可)
  に基づく。
- 削除前の baseline → 削除後 final まで delete-mode TDD パターンを徹底
  (test → mid green → impl → grep verify → final green → ruff)。
- 削除した行数合計: 277 行 (95 + 144 + 38)。

---

## Phase E 完了 (2026-04-24)

- Task 1〜4 すべて完了
- 全 unit tests 773 PASS (前回 787 - 削除テスト 14)
- ruff clean (Phase E 範囲で新規 error 0)
- 削除した dead code: 11 public API + 3 module-private helpers + 1 stale import
- 次 Phase: B (可読性・命名)
