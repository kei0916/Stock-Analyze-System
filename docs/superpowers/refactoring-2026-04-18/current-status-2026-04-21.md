# Current Status (2026-04-21)

## Scope

2026-04-21 時点の current branch
`codex-refactoring-followups-20260419` に載っている実装・修正・記録更新を、
追跡しやすい snapshot としてまとめる。

この更新では、2026-04-20 に反映した Web security hardening /
review follow-up と、同日中に再監査のうえ再実装した Phase C
(DRY / 重複排除) を、最終的な branch 状態として統合して記録する。

---

## 実装・修正済み

### Web security hardening / review follow-up

- `InMemoryRateLimiter` を `try_acquire()` / `release()` ベースへ置換し、
  判定と予約を 1 回の lock 区間にまとめた
- login route と heavy endpoint (`/jobs/*`, RAG `ask/index`) を
  atomic admission へ揃え、split check/update を解消した
- limiter の空 bucket は `_trim()` / `release()` の両方で削除する形へ修正し、
  期限切れ後の per-client state が残り続けないようにした
- `PdfConverter` の safe fetcher は `data:` URL を許可しつつ、
  `http(s):` / `ftp:` / relative-network URL と root 外 `file:` を拒否する形へ修正した

対象ファイル:
`src/stock_analyze_system/web/auth.py`,
`src/stock_analyze_system/web/routes/auth.py`,
`src/stock_analyze_system/web/routes/api.py`,
`src/stock_analyze_system/web/routes/jobs.py`,
`src/stock_analyze_system/services/pdf_converter.py`,
`tests/unit/web/test_auth.py`,
`tests/unit/services/test_pdf_converter.py`

### Phase C: DRY / 重複排除

- `BaseRepository._bulk_upsert_by_natural_key()` を追加し、
  `FinancialRepository.bulk_upsert` /
  `ValuationRepository.bulk_upsert` を 1 行 delegate に縮小した
- `FilingSource(StrEnum)`、`FilingSourceAdapter`、
  `FilingSyncService._sync()` を導入し、SEC / EDINET の同形 sync 処理を共通化した
- CLI `watchlist show` を `get_with_items()` に移行し、
  `WatchlistService.get_watchlist` / `list_items` を削除した

対象ファイル:
`src/stock_analyze_system/repositories/base.py`,
`src/stock_analyze_system/repositories/financial.py`,
`src/stock_analyze_system/repositories/valuation.py`,
`src/stock_analyze_system/models/enums.py`,
`src/stock_analyze_system/repositories/filing.py`,
`src/stock_analyze_system/services/filing_sync.py`,
`src/stock_analyze_system/cli/watchlist.py`,
`src/stock_analyze_system/services/watchlist.py`,
`tests/unit/repositories/test_base_repo.py`,
`tests/unit/repositories/test_filing_repo.py`,
`tests/unit/services/test_filing_sync.py`,
`tests/unit/test_enums.py`,
`tests/unit/cli/test_watchlist_cli.py`,
`tests/integration/test_service_assembly.py`

### 記録整合性の補正

- `current-status-2026-04-19.md` に Phase C 実装完了前提の誤記を補正する注記を追加した
- `phase-c-dry/report.md` を再監査結果と再実装後の完了状態に合わせて更新した
- `master.md` の Phase tracker を Phase C `✅ Done` に更新し、
  `2026-04-21` snapshot を最新更新へ追加した

### Secret management / Infisical 実行ルール

- repo-local `.env` は後方互換 fallback として残すが、通常の project command は
  Infisical 経由で実行する運用へ切り替えた
- 通常コマンドは必ず `STOCK_ANALYZE_LOAD_DOTENV=0` を指定し、
  `.env` fallback を無効化したうえで Infisical secrets を注入する
- 標準コマンド形式:
  `env STOCK_ANALYZE_LOAD_DOTENV=0 infisical run --env=dev --path=/ -- <command>`
- `load_config()` は既存利用者向けに `.env` fallback を維持しつつ、
  `STOCK_ANALYZE_LOAD_DOTENV=0` で明示的に無効化できるようにした
- `.infisical.json` を repo root に追加した。内容は Infisical project mapping
  (`workspaceId`) のみで、secret value は含まない
- 長い Infisical prefix を手打ちしないため、`scripts/infisical-run` を標準 wrapper
  として追加した。通常は
  `scripts/infisical-run <command>` を使う
- wrapper の利用手順は
  [infisical-local-commands.md](infisical-local-commands.md) に記録した

---

## Verification

- `env STOCK_ANALYZE_LOAD_DOTENV=0 infisical run --env=dev --path=/ -- uv run pytest -q`
  - 結果: `787 passed, 4 deselected, 5 warnings in 9.61s`
- `scripts/infisical-run uv run pytest -q`
  - 結果: `787 passed, 4 deselected, 5 warnings in 9.33s`
- `scripts/infisical-run uv run ruff check src/stock_analyze_system/config.py src/stock_analyze_system/web/app.py tests/unit/test_config.py tests/unit/web/test_app.py`
  - 結果: `All checks passed!`
- `uv run pytest -q`
  - 結果: `783 passed, 4 deselected, 5 warnings in 9.30s`
- `uv run ruff check src/stock_analyze_system/repositories/base.py src/stock_analyze_system/repositories/financial.py src/stock_analyze_system/repositories/valuation.py src/stock_analyze_system/models/enums.py src/stock_analyze_system/repositories/filing.py src/stock_analyze_system/services/filing_sync.py src/stock_analyze_system/cli/watchlist.py src/stock_analyze_system/services/watchlist.py tests/unit/repositories/test_base_repo.py tests/unit/repositories/test_filing_repo.py tests/unit/services/test_filing_sync.py tests/unit/test_enums.py tests/unit/cli/test_watchlist_cli.py tests/integration/test_service_assembly.py`
  - 結果: `All checks passed!`
- `rg -n "watchlist_service\\.get_watchlist|watchlist_service\\.list_items" src tests`
  - 結果: ヒット 0 件

warnings は既存の `PyPDF2` deprecation と一部 `AsyncMock` runtime warning が中心で、
今回の変更で新しい failure は追加していない。

---

## Review 状態

- merge base 基準の review では、今回の refactor / hardening 差分について
  blocking issue や follow-up review comment は見つからなかった

---

## GitHub 記録

2026-04-21 の追加記録対象:

- repository: `kei0916/Stock-Analyze-System`
- branch: `codex-refactoring-followups-20260419`
- remote: `origin`
- Infisical 実行設定:
  - `9387757 Add Infisical execution config`
  - `.infisical.json`、`.env` fallback opt-out、設定エラーメッセージ、
    regression tests、refactoring docs 記録
- Infisical local command wrapper:
  - `88db32f Add Infisical local command wrapper`
  - `scripts/infisical-run`、`infisical-local-commands.md`、
    tracker/current-status 追記

この snapshot 以降の GitHub 上の source of truth は、上記 branch の pushed
commits とする。

---

## 関連記録

- [current-status-2026-04-20.md](current-status-2026-04-20.md)
  - 2026-04-20 時点の hardening / follow-up 詳細
- [phase-c-dry/report.md](phase-c-dry/report.md)
  - Phase C 再監査と再実装の詳細
- [master.md](master.md)
  - project-wide tracker
