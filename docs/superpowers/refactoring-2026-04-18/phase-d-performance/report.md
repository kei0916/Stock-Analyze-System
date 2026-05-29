# Phase D: パフォーマンス改善 — 実施記録

**Status**: 未着手 (plan.md 作成待ち)

各 Task 完了時に追記。記録項目: 変更ファイル / commit hash / (該当すれば) ベンチ数値 / 備考。

---

## Task 記録

### Task 1: モデル unique index 棚卸し — ✅ Done (2026-04-19)

- 変更: `tests/unit/models/test_natural_key_constraints.py` (新規, 6 tests)
- 既存制約のみで要件を満たすことを確認。スキーマ変更なし。
- commit: a4344e5

### Task 2: BaseRepository._bulk_upsert_native 追加 — ✅ Done (2026-04-19)

- 変更: `src/stock_analyze_system/repositories/base.py`, `tests/unit/repositories/test_base_repo.py`
- 4 ケース (insert / update / 空入力 / update_columns 空) を TDD で固定。
- commit: 6d65d9a

### Task 3: FinancialRepository.bulk_upsert 差し替え — ✅ Done (2026-04-19)

- 変更: `src/stock_analyze_system/repositories/financial.py`
- N+1 loop を _bulk_upsert_native 呼び出しに置換。public API 無変更。
- 既存 4 tests 無変更で PASS。service/integration tests 206 PASS、全 unit tests 718 PASS。
- commit: d133739

### Task 4: ValuationRepository.bulk_upsert 差し替え — ✅ Done (2026-04-19)

- 変更: `src/stock_analyze_system/repositories/valuation.py`
- Task 3 と同パターンで _bulk_upsert_native に置換。
- 既存 3 tests 無変更で PASS。service/integration tests 209 PASS、全 unit tests 718 PASS。
- commit: 4142cd9

### Task 5: TargetRepository.bulk_add 差し替え — ✅ Done (2026-04-19)

- 変更: `src/stock_analyze_system/repositories/target.py`
- 既存 company_id を 1 クエリで検出 → 新規分のみ `on_conflict_do_nothing` で一括 INSERT。
- 重複スキップ挙動維持。戻り値 (追加件数 int) 意味不変。
- 既存 2 target tests 無変更で PASS。全 unit/integration tests 728 PASS。
- commit: dd653b9

### Task 6: Filing bulk_upsert + FilingSyncService 一括化 — ✅ Done (2026-04-19)

- 変更: `repositories/filing.py`, `services/filing_sync.py`, 対応テスト 2 本
- `find_existing_accessions` / `find_existing_doc_ids` / `bulk_upsert(source=...)` 追加。
- `update_from_sec` / `update_from_edinet` を「list → 既存検出 → 新規一括 INSERT」の 3 クエリ構成に再構築。
- 既存「重複は skip」挙動維持。
- commit: 02cbe86

### Task 7: ClientBundle + AppState singleton 化 — ✅ Done (2026-04-19)

- 変更: `web/dependencies.py`, `cli/container.py`, `tests/unit/web/test_singleton_clients.py`
- `AppState.clients: ClientBundle` を追加、Web get_services が setup_services に pass-through。
- `setup_services(session, config)` 2 引数呼び出しの CLI / 既存テスト互換維持。
- `AppState.dispose()` で httpx ベースクライアント (sec/edinet/fmp) の close を呼ぶ。Yahoo は close 不要。
- commit: b914a0c

### Task 8: Watchlist selectinload — ✅ Done (2026-04-19)

- 変更: `repositories/watchlist.py`, `services/watchlist.py`, `web/routes/watchlists.py`, `tests/unit/repositories/test_watchlist_repo.py`
- `get_with_items(watchlist_id)` を追加 (selectinload)。`detail_page` で get_watchlist + list_items の 2 await を 1 await に集約。
- 既存 `get_watchlist`/`list_items` は他用途のため維持。新規テスト 3 本追加。
- 全 unit tests 727 PASS (前回 724 + 新規 3 tests)。
- commit: e21474a

### Task 9: ベンチマーク測定 & report.md 記録 — ✅ Done (2026-04-19)

- 変更: `pyproject.toml`, `tests/benchmarks/` (3 新規), `report.md`
- benchmark marker + default 除外 addopts を導入。`-m benchmark` で明示実行時のみ動作。
- after のみ計測 (before は N+1 loop の差し戻しが高コストのため割愛)
- commit: 46832a3

---

## ベンチマーク結果

### FinancialRepository.bulk_upsert

| N | After (ms) | 計測日 |
|---|---|---|
| 50 | 3.3 | 2026-04-19 |
| 500 | 41.3 | 2026-04-19 |

### ValuationRepository.bulk_upsert

| N | After (ms) | 計測日 |
|---|---|---|
| 50 | 2.1 | 2026-04-19 |

### FilingSyncService.update_from_sec

| N | After (ms) | 計測日 |
|---|---|---|
| 100 | 7.2 | 2026-04-19 |

---

## 備考

- 計測は `pytest -m benchmark tests/benchmarks/ -s` で手動実行
- SQLite in-memory 環境、実ディスク I/O は未反映 (本番はさらに効く想定)

---

## Phase D 完了 (2026-04-19)

- Task 1〜10 すべて完了
- 全テスト PASS (737 tests, benchmark 4 件 deselected)
- カバレッジ 96%
- ruff clean (Phase D 範囲で新規 error 0)
- `run_daily_update` 直列実行を維持 (LLM+SEC filings デッドロック回避)
- bulk_upsert / filing_sync / Web route の I/O 削減 (ベンチ表参照)
- 次 Phase: C (DRY / 重複排除)
