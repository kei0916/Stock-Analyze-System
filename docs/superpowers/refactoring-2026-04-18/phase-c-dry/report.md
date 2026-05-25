# Phase C: DRY / 重複排除 — 実施記録

**Status**: 実装完了 (2026-04-20, re-audit 後に再実装)

2026-04-20 の再監査で、元の report が「実装完了」と断定していた内容と
現行コード / テスト / git 履歴が一致していないことを確認した。
その後、tracker / report を実態に合わせて補正し、Task 1 → Task 2 →
Task 3 の順に TDD で再実装した。

---

## Task 記録

### Task 1: `BaseRepository._bulk_upsert_by_natural_key` 導入 — 完了

- `BaseRepository` に `_bulk_upsert_by_natural_key(records, natural_key_cols, *, scope_key, scope_value)` を追加
- `FinancialRepository.bulk_upsert` / `ValuationRepository.bulk_upsert` を helper delegate に縮小
- `tests/unit/repositories/test_base_repo.py` に 4 test を追加し、
  scope 有/無・空入力・`update_columns=[]` の委譲を固定

### Task 2: `FilingSource` + `FilingSourceAdapter` + `FilingSyncService._sync()` — 完了

- `models/enums.py` に `FilingSource(StrEnum)` を追加
- `FilingRepository.bulk_upsert(source=...)` を enum 受け取りへ変更
- `FilingSyncService.update_from_sec` / `update_from_edinet` を
  `FilingSourceAdapter` + `_sync()` に集約
- `tests/unit/services/test_filing_sync.py` に `_sync()` 直接テスト 5 件を追加し、
  happy path・empty・all-existing・fetch 例外・map 回数を固定
- `tests/unit/test_enums.py` に `FilingSource` の値確認を追加

### Task 3: Watchlist API 整理 — 完了

- CLI `watchlist show` を `get_with_items()` 経由へ移行
- `tests/unit/cli/test_watchlist_cli.py` と
  `tests/integration/test_service_assembly.py` を新契約へ更新
- `WatchlistService.get_watchlist` / `list_items` を削除

---

## 補正と再実装の要点

- 元の report は docs 先行で、実コードは Task 1 未着手 / Task 2 未着手 /
  Task 3 部分着手だった。
- まず tracker / report / current-status 注記を補正し、その後にコード側を実装した。
- Phase D で追加済みだった `_bulk_upsert_native` と `get_with_items()` を土台に、
  Phase C 固有の DRY 化と API 整理だけを追加した。

---

## Verification

- `uv run pytest tests/unit/repositories/test_base_repo.py -q`
  - 結果: `19 passed`
- `uv run pytest tests/unit/repositories/ -q`
  - 結果: `62 passed`
- `uv run pytest tests/unit/test_enums.py tests/unit/repositories/test_filing_repo.py tests/unit/services/test_filing_sync.py -q`
  - 結果: `29 passed`
- `uv run pytest tests/unit/cli/test_watchlist_cli.py tests/integration/test_service_assembly.py -q`
  - 結果: `21 passed`
- `uv run pytest tests/unit/services/test_watchlist_service.py tests/unit/cli/test_watchlist_cli.py tests/integration/test_service_assembly.py -q`
  - 結果: `27 passed`
- `uv run pytest -q`
  - 結果: `783 passed, 4 deselected, 8 warnings`
- `uv run ruff check src/stock_analyze_system/repositories/ tests/unit/repositories/`
  - 結果: `All checks passed!`
- `uv run ruff check src/stock_analyze_system/models/enums.py src/stock_analyze_system/repositories/filing.py src/stock_analyze_system/services/filing_sync.py tests/unit/test_enums.py tests/unit/repositories/test_filing_repo.py`
  - 結果: `All checks passed!`
- `uv run ruff check src/stock_analyze_system/services/filing_sync.py tests/unit/services/test_filing_sync.py`
  - 結果: `All checks passed!`
- `uv run ruff check src/stock_analyze_system/services/watchlist.py src/stock_analyze_system/cli/watchlist.py tests/unit/cli/test_watchlist_cli.py tests/integration/test_service_assembly.py tests/unit/services/test_watchlist_service.py`
  - 結果: `All checks passed!`

---

## 効果

- `FinancialRepository.bulk_upsert` / `ValuationRepository.bulk_upsert` の
  重複ロジックを helper に集約
- `FilingSyncService` の SEC / EDINET 同形処理を `_sync()` 1 箇所へ統合
- CLI / Web の watchlist 詳細取得契約を `get_with_items()` に統一
- 追加テストは 10 件:
  `test_base_repo.py` 4 件、`test_filing_sync.py` 5 件、`test_enums.py` 1 件
