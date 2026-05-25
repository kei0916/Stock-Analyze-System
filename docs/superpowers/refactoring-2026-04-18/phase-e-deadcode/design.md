# Phase E: デッドコード削除 — Design

**Status**: Draft (2026-04-24)

**前提**: Phase D (性能) / Phase C (DRY) 完了後、branch `codex-refactoring-followups-20260419` に load 済み。全 805 tests PASS、coverage 96% 維持。本 Phase は master.md Phase 進捗表の §3 順位 (E — デッドコード削除)。

---

## Goal

master.md Backlog で明示された Phase E 候補 (A) と、/simplify による caller 検証で確定した (B) public method を src/ から削除する。保持する (C) / (D) 候補は Backlog に「intentionally kept」として理由付きで再分類し、将来の /simplify や audit で再発見しても即「Phase E で検討済」と判断できるようにする。

**成功条件:**

1. 削除対象 11 項目が src/ から消え、`grep -rn <symbol>` で src/ tests/ とも 0 件になる
2. 削除対象を caller にしていた test 群も同一 commit 内で削除/書換される
3. 全テスト PASS (現 805 → 削除後は 805 - N 程度、N = 削除 test 数)
4. coverage 大幅低下なし (dead code のみの削除で分母も縮むため比率は維持)
5. ruff clean (Phase E 新規 0 errors)
6. master.md が Phase E ✅ Done、Backlog の (C) / (D) が「intentionally kept」として再分類済

---

## Non-Goals

- **(C) / (D) 候補の削除**: 次節「Non-goals 扱いの候補」で個別に保持理由を明示。Phase E スコープから除外。
- 新 API 追加・既存 API の挙動変更: 削除のみ、追加 / 置換なし。
- 巨大ファイル分割: Phase A 範囲。
- 命名・docstring 精査: Phase B 範囲。

---

## Non-goals 扱いの候補 (Backlog に理由付きで残す)

Phase E で **削除しない** が、/simplify で候補に挙がった項目。将来の判断材料として master.md Backlog に理由付きで記録し直す。

| 保持対象 | 保持理由 | 将来の削除トリガー |
|---|---|---|
| `exceptions.RateLimitError` / `ParsingError` / `LlmConnectionError` / `LlmResponseError` | ingestion / LLM 層で `except Exception` の broad catch に拾われている可能性。catch 側が明示的に拾っていないだけ。broad catch の精査なしに消すと、例外が正しく分類されないリスク | Phase B (可読性) で broad catch を絞り込む段階で再評価 |
| `config.daily_limit` / `config.batch_size` | SEC 429 対応 / batch ingestion の将来拡張枠。YAML 例 (`config/settings.yaml.example`) にも載っており、削除すると例との不整合 | YAML 例削除 + run_daily_update の rate-limit 設計が固まったときに再評価 |
| `config.lm_studio_base_url` | LM Studio サポートの名残。Qwen3.6 + llama.cpp 完全移行後は不要の可能性が高いが、2026-04-23 snapshot で Ollama / LM Studio / llama.cpp 3 ルートを検証中 | Qwen3.6 + llama.cpp 単一ルート確定後に削除 (Phase E-2 候補) |
| `models/competitor_group.py` (`CompetitorGroup` / `CompetitorGroupMember`) | 未実装機能 (競合銘柄分析) のスキーマ予約。Alembic migration に含まれている可能性があり、削除は migration rollback まで含む大工事 | 競合銘柄機能の実装 or 正式 scrap 判断時に別 Phase で対応 |
| ingestion client の未使用 method 群 (`fmp.*`, `sec_edgar.*`, `yahoo_finance.*` 計 11 個) | SDK 完全性のため保持。将来の screening / RAG 拡張で使用予定。削っても他のパッケージが提供している機能ではなく、ingestion 層の一貫性を維持する価値 | 明示的に「この SDK から特定 method を切る」設計判断が出たとき |

---

## Master rule 例外 (Phase C から継続適用)

Phase C で設定した例外 (「旧 API に置換済で全 caller 移行済みなら Phase C で削除可」) を Phase E でも同様に適用。Phase E 削除対象は本 spec §Scope 表で網羅する。

---

## Scope — 削除対象 11 項目

| # | Layer | File | Symbol | Rationale | 削除行数 (概算) |
|---|---|---|---|---|---|
| 1 | repo | `repositories/filing.py:47-51` | `FilingRepository.find_by_accession` | src/ caller 0、test のみ (Phase D /simplify 確認済、master.md Backlog で明示) | 6 |
| 2 | repo | `repositories/filing.py:53-57` | `FilingRepository.find_by_doc_id` | 同上 | 6 |
| 3 | repo | `repositories/watchlist.py:24-30` | `WatchlistRepository.list_items` | Phase C で `get_with_items` に置換済、CLI / Web / Service とも移行完了。残り caller は test のみ | 8 |
| 4 | repo | `repositories/company.py:50-?` | `CompanyRepository.list_by_market` | src/ caller 0、test のみ | 7 |
| 5 | service | `services/financial.py:135-?` | `FinancialService.build_chart_data` | src/ caller 0、test のみ (CLI/Web/API どこからも chart データ組立を service 経由で呼んでいない) | ~40 |
| 6 | service | `services/valuation.py:105-?` | `ValuationService.build_chart_data` | 同上 | ~40 |
| 7 | service | `services/rag_service.py:139-?` | `RagService.ask_questions` | src/ caller 0、test のみ (RAG API は `query()` 単一経路) | ~20 |
| 8 | service | `services/metrics.py:176-188` | `metrics.peg_ratio` (module-level function) | src/ caller 0、test のみ。ingestion の yahoo_finance で dict key として `"peg_ratio"` は出現するが同名別物 | ~13 |
| 9 | service | `services/metrics.py:190-208` | `metrics.cagr` (module-level function) | src/ caller 0、test のみ | ~19 |
| 10 | shared | `shared/formatters.py:11-14` | `fmt_pct` | src/ caller 0、test のみ。`fmt_number` / `fmt_large` は継続利用 | 4 |
| 11 | shared | `shared/formatters.py:29-32` | `fmt_ratio` | 同上 | 4 |

**合計**: src/ 削除 ~167 行 + 対応 test 削除。

---

## Architecture — 3 Task + 1 docs Task

Layer 単位で commit を切る (Phase C / D と同粒度)。Task 間に依存なし、順序変更可。

```
Task 1 (repo layer)        Task 2 (service layer)      Task 3 (shared layer)
  #1-4                       #5-9                          #10-11
  └─ filing.py               ├─ financial.py               └─ formatters.py
  └─ watchlist.py            ├─ valuation.py
  └─ company.py              ├─ rag_service.py
                             └─ metrics.py

           Task 4 (docs)
           ├─ master.md — Backlog 再分類 + Phase E ✅ Done
           └─ report.md — 新規作成
```

---

## Task 1: repo layer — 4 methods 削除

### 対象ファイル

- `src/stock_analyze_system/repositories/filing.py`
- `src/stock_analyze_system/repositories/watchlist.py`
- `src/stock_analyze_system/repositories/company.py`
- `tests/unit/repositories/test_filing_repo.py` (test 2 件削除)
- `tests/unit/repositories/test_watchlist_repo.py` (test 3 件書換)
- `tests/unit/repositories/test_company_repo.py` (test 1 件削除)

### 削除 + 書換内容

1. **`filing.py`**: `find_by_accession` (47-51) / `find_by_doc_id` (53-57) の 2 メソッドを削除。
2. **`watchlist.py`**: `list_items` (24-30) を削除。`get_with_items` は残す。
3. **`company.py`**: `list_by_market` を削除。
4. **test_filing_repo.py**: `test_find_by_accession` / `test_find_by_doc_id` を削除。
5. **test_watchlist_repo.py**: `list_items()` 呼び出し 3 箇所を `get_with_items(wl_id).items` に書換。例:
   ```python
   # before
   items = await watchlist_repo.list_items(sample_watchlist.id)
   # after
   wl = await watchlist_repo.get_with_items(sample_watchlist.id)
   items = wl.items
   ```
6. **test_company_repo.py**: `test_list_by_market` を削除。

### 受け入れ

- `grep -rn "find_by_accession\|find_by_doc_id\|list_by_market" src/ tests/` で 0 件
- `grep -rn "WatchlistRepository().*list_items\|watchlist_repo.list_items" src/` で 0 件 (tests は `get_with_items` 移行済なので 0 件)
- `uv run pytest tests/unit/repositories/ -v` で全 PASS

### Commit

```
refactor(repo): drop dead methods (find_by_accession/doc_id, list_items, list_by_market)

- FilingRepository から find_by_accession / find_by_doc_id 削除 (src 内 caller 0)
- WatchlistRepository.list_items 削除 (Phase C で get_with_items に置換済)
- CompanyRepository.list_by_market 削除 (src 内 caller 0)
- 対応 test 削除 3 件 + test_watchlist_repo.py の 3 test を get_with_items に書換

Phase E Task 1.
```

---

## Task 2: service layer — 5 methods 削除

### 対象ファイル

- `src/stock_analyze_system/services/financial.py`
- `src/stock_analyze_system/services/valuation.py`
- `src/stock_analyze_system/services/rag_service.py`
- `src/stock_analyze_system/services/metrics.py`
- `tests/unit/services/test_financial_service.py`
- `tests/unit/services/test_valuation_service.py`
- `tests/unit/services/test_rag_service.py`
- `tests/unit/services/test_metrics.py`

### 削除内容

1. **`financial.py:135-?`**: `build_chart_data` method 削除。メソッド本体 + docstring + 内部ヘルパ (他で使われていない場合) を削除。
2. **`valuation.py:105-?`**: `build_chart_data` method 削除。
3. **`rag_service.py:139-?`**: `ask_questions` method 削除。RAG API は `query()` 単一経路で運用中 (PageIndex 経由)。
4. **`metrics.py:176-188`**: module-level `peg_ratio` 関数削除。
5. **`metrics.py:190-208`**: module-level `cagr` 関数削除。
6. **test 側**:
   - `test_financial_service.py`: `build_chart_data` を直接テストする関数を削除 (1 test)
   - `test_valuation_service.py`: 同上 (1 test)
   - `test_rag_service.py`: `ask_questions` を直接テストする関数を削除 (該当 1 test)
   - `test_metrics.py`:
     - `TestValuation` クラスから `test_peg_ratio` / `test_peg_ratio_zero_growth` / `test_peg_ratio_negative_growth` の 3 test を削除 (クラス自体は `test_per_*` / `test_pbr` / `test_ev_ebitda*` / `test_psr` を保持して残す)
     - `TestUtilities` クラスから `test_cagr` / `test_cagr_negative_begin` の 2 test を削除 (クラス自体は `test_is_anomaly_*` を保持して残す)
     - 合計 5 test 削除、クラスごと削除は **しない**

### 未使用 import の追随削除

削除後に `typing.Any` / 他 unused import が残る場合、同 commit 内で `ruff check --fix` 相当の手修正を入れる。

### 受け入れ

- `grep -rn "build_chart_data\|ask_questions\|metrics\.peg_ratio\|metrics\.cagr" src/ tests/` で 0 件
- `uv run pytest tests/unit/services/ -v` で全 PASS
- `uv run ruff check src/stock_analyze_system/services/` で 0 new errors

### Commit

```
refactor(service): drop dead methods (build_chart_data, ask_questions, peg_ratio, cagr)

- FinancialService.build_chart_data / ValuationService.build_chart_data 削除 (CLI/Web/API から未呼出)
- RagService.ask_questions 削除 (RAG API は query() 単一経路)
- metrics.peg_ratio / metrics.cagr (module-level) 削除 (src 内 caller 0)
- 対応 test 合計 8 件削除 (TestUtilities クラスごと削除可の場合は併せて削除)

Phase E Task 2.
```

---

## Task 3: shared layer — 2 functions 削除

### 対象ファイル

- `src/stock_analyze_system/shared/formatters.py` (32 → ~24 行)
- `tests/unit/test_shared_formatters.py` (2 parametrized test 削除)

### 削除内容

1. **`formatters.py:11-14`**: `fmt_pct` 削除。
2. **`formatters.py:29-32`**: `fmt_ratio` 削除。
3. **`test_shared_formatters.py:4`**: import から `fmt_pct` / `fmt_ratio` を削除。
4. **`test_shared_formatters.py:28-29` / `:53-54`**: `test_fmt_pct` / `test_fmt_ratio` 削除。parametrized なので `@pytest.mark.parametrize` ブロックごと削除。

### 受け入れ

- `grep -rn "fmt_pct\|fmt_ratio" src/ tests/` で 0 件
- `uv run pytest tests/unit/test_shared_formatters.py -v` で全 PASS (`test_fmt_number` / `test_fmt_large` 2 test が残存)

### Commit

```
refactor(shared): drop unused formatters (fmt_pct, fmt_ratio)

- shared/formatters.py から fmt_pct / fmt_ratio 削除 (src 内 caller 0)
- test_shared_formatters.py から対応 parametrized test 削除
- fmt_number / fmt_large は CLI/Web の大量箇所で利用中、継続保持

Phase E Task 3.
```

---

## Task 4: docs — Backlog 再分類 + `report.md`

### 4-1. `master.md` Backlog 更新

以下の書き換えを master.md に反映:

#### 削除セクション (消費済み Phase E 候補)

旧 §Backlog の **Phase E (デッドコード) 候補:** ブロックを削除し、下記「Phase E で消費済」リストに移動 (Phase C と同形)。

```markdown
**Phase E (デッドコード):**
- 2026-04-XX に消費。Task 1 (repo 4 method) + Task 2 (service 5 method) + Task 3 (shared 2 function) = 11 項目削除。
- 消費した項目: `FilingRepository.find_by_accession`, `FilingRepository.find_by_doc_id`,
  `WatchlistRepository.list_items`, `CompanyRepository.list_by_market`,
  `FinancialService.build_chart_data`, `ValuationService.build_chart_data`,
  `RagService.ask_questions`, `metrics.peg_ratio`, `metrics.cagr`,
  `formatters.fmt_pct`, `formatters.fmt_ratio`
```

#### 追加セクション (Intentionally kept)

新セクションとして「Intentionally kept (Phase E で検討し保持決定)」を追加。本 spec §Non-goals 扱いの候補の表をそのまま写す (5 項目、各 rationale 付き)。

#### Phase 進捗表

§Phase 進捗表の Phase E 行を `⚪ Pending` → `✅ **Done**`、Spec/Plan/Report リンクを埋める。

### 4-2. `report.md` を新規作成

`docs/superpowers/refactoring-2026-04-18/phase-e-deadcode/report.md` を Phase C report と同形で作成。内容:

- 成果物テーブル (Task → commit SHA → 内容)
- 削除統計 (src 行数 / test 数 / 影響ファイル数)
- 消費した Backlog 項目 (11 項目チェック)
- 保持決定した Non-goals (5 項目、理由付き)
- Verification (pytest / ruff / grep 結果)

### Commit

```
docs(refactor): Phase E done — dead code removal

- repo/service/shared 3 layer で計 11 項目削除 (~167 src 行 + 対応 test)
- master.md Backlog を「消費済」と「Intentionally kept」に再分類
- Phase E ✅ Done

Phase E completion. Backlog の Phase E 候補 3 項目 + /simplify 確認済 (B) 群 8 項目を消費。
```

---

## テスト & 受け入れ (Phase 全体)

- **全 unit tests PASS**: 現 805 → Task 1-3 で test 削除 10-15 件 → **790-795 PASS 見込み**
- **全 integration tests PASS**: 無変更
- **benchmark**: 変更なし
- **coverage**: 96% 維持 (削除対象は test だけが覆っていた dead code、母数も縮む)
- **ruff clean**: Phase E 新規 0 errors
- **未使用 import**: 削除の副作用で `typing.Any` 等が残る場合、同 commit 内で除去

## 作業順序 (推奨)

1. **Task 1** (repo layer) — 最小リスク、test 書換だけ注意
2. **Task 2** (service layer) — 削除行数最大、import cleanup 忘れずに
3. **Task 3** (shared layer) — 最小、parametrized test 削除のみ
4. **Task 4** (docs) — 最終化

各 Task commit 直後に `uv run pytest` 全緑を確認してから次 Task へ。全 Task 終了後、`/simplify` は Phase E では **不要** (削除のみで新規コードなし、重複発生の余地がない)。

---

## 参照

- Phase D design/report: `../phase-d-performance/` (同 layer パターン参考)
- Phase C design/report: `../phase-c-dry/` (Backlog 更新・rule 例外の先例)
- master tracker: `../master.md`
