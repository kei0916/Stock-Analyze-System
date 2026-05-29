# `feat/sec-section-extractor` リファクタリング候補一覧 (2026-05-17)

ブランチ全体を 3 視点 (reuse / quality / efficiency) で並列レビューした結果を
集約したもの。他エージェント / 後日の自分がコンテキストを再構築できるよう、
**何を直すべきか / なぜか / どう直すか / どこまで安全か / 検証手順** を残す。

## 0. ブランチ概要

| 項目 | 値 |
|---|---|
| ブランチ | `feat/sec-section-extractor` |
| ベース | `master` (merge-base `9cd384f`) |
| 規模 | 78 files / +13,773 / -433 / 75 commits |
| 主要テーマ | (1) AnalysisWorker 分離 + (2) ADR-004 SEC SectionExtractor 導入 |
| Production 行 | 22 .py / +1,888 / -205 |
| 直近 HEAD | `29ab118 docs(adr): drop trailing blank line at EOF in step-3 runaway log` |
| 検証済み構成 | llama-server `--ctx-size 131072 --parallel 1 --jinja --n-gpu-layers 99` (`docs/step3-reasoning-runaway-verification.md` 参照) |

レビュー対象から外したもの:
- テストコード (DRY 違反指摘もあったが production 優先)
- ドキュメントの文体 / 表現

---

## 1. Round 1 — 正しさ / 死コード (最優先・低リスク)

### A. `_iteration_events` が list を return しており真の streaming でない

- **場所**: `src/stock_analyze_system/services/rag_service.py:284-348`
- **症状**: `run_full_analysis_stream` は外見上 streaming イベントを yield するが、
  `_iteration_events(...)` が `list[dict]` を組み立ててから `for event in await ...:
  yield event` で一括出力するため、worker `update_progress` がバースト書きに
  なり live UI 進捗が崩れる。
- **修正案**: `_iteration_events` を `async def ... -> AsyncIterator[dict]:`
  に変更し、各 event を直接 `yield`。呼び出し側は
  `async for event in self._iteration_events(...): yield event` に。
- **影響範囲**: `rag_service.py` のみ。worker 側は変更不要 (既に
  `async for event in stream` で消費)。
- **検証**: `tests/unit/services/test_rag_service.py` の stream 系テスト
  (placeholder / cached / 成功 / 失敗) が全 pass を維持。さらに
  `test_nonstream_skips_unexpected_empty_section_rather_than_raising` 等が
  影響を受けないこと。
- **依存**: なし (単独で fix 可能)

### B. worker 内 `IndexBuildError` ハンドラが extractor pivot 後デッド

- **場所**: `src/stock_analyze_system/services/analysis_worker.py:167-178`
  + `import IndexBuildError` (line 17 付近)
- **症状**: ADR-004 で `run_full_analysis_stream` は PageIndex を呼ばなくなった
  (`c4b3f03` で `preflight` も pageindex 経由を停止)。`_run_job` が
  `RagService.run_full_analysis_stream` だけを呼ぶなら、PageIndex の
  `IndexBuildError` が伝播する経路は理論上存在しない。
- **修正案**: ハンドラ branch + 不要 import を削除。
- **⚠ 事前必須**: §3 (本ドキュメント) の全パターン検証で
  「extractor / RagService から `IndexBuildError` が漏れる経路がない」ことを
  確定してから着手。
- **依存**: §3 検証の完了

### C. `PageIndexService.preflight` が unused

- **場所**: `src/stock_analyze_system/services/pageindex/service.py:394-456`
  + 該当 unit tests in `tests/unit/services/test_pageindex_service.py`
- **症状**: commit `c4b3f03` で `RagService.preflight` が `LlmClient.completion`
  ベースに切り替わり、PageIndex 版 preflight は live caller が消滅。
  テストだけが alive にしている状態。
- **修正案**: 関数本体 + テストクラスを削除。
- **⚠ 事前確認**: `ask_question` 系統 / CLI / diag endpoint からの呼び出しが
  本当に無いか `grep -rn "pageindex.*preflight\|_pageindex.preflight"` で
  二重確認。
- **依存**: なし (B とは独立、grep 確認のみ)

### D. `_REGEX_FALLBACK` の `start + 10` skip がパターン長依存

- **場所**: `src/stock_analyze_system/services/filing_section_extractor.py:192-193`
- **症状**: 10-Q MD&A 抽出時、開始 match の自己再 match 回避のため
  `text.find(end_pat, start_match.end() + 10)` 風の `+10` マジック数を
  使っているが、将来パターン長が 10 chars 未満になると本文を食い潰す。
- **修正案**: `start + 10` → `start_match.end()` に置換。または
  `re.search(end_pat, text, pos=start_match.end())` を使う。
- **検証**: `tests/unit/services/test_filing_section_extractor.py` の
  TEM 10-Q U+2009 thin space rescue ケース、および任意の 10-Q HTML で
  従前と同じ section 範囲が抽出されること。
- **依存**: なし

---

## 2. Round 2 — DRY / 品質 (中価値)

### E. `now_utc()` が 3 ファイルに重複

- **場所**:
  - `src/stock_analyze_system/services/analysis_queue.py:13-15` (`now_utc`)
  - `src/stock_analyze_system/services/analysis_worker.py:26-27` (`_now_utc`)
  - `src/stock_analyze_system/repositories/analysis_job.py:91, 162, 182, 197`
    (inline `datetime.now(timezone.utc)` × 4)
- **修正案**: `src/stock_analyze_system/shared/time_utils.py` を新設し
  `now_utc()` を 1 つだけ定義。3 ファイルから import。
- **注意**: branch 外にもインライン書きが ~8 箇所あるが本ブランチでは触らない
  (scope creep 回避)。
- **検証**: `git grep "datetime.now(timezone.utc)" src/` の差分確認 + 全テスト pass

### F. `_execute_with_status` で session 再オープン 6 ブロックがほぼ同形

- **場所**: `src/stock_analyze_system/services/analysis_worker.py:138-196`
- **症状**: 各 except 内で `async with self._session_factory() as session:` +
  `repo = AnalysisJobRepository(session)` を再構築し `update_status` を呼ぶ
  4 行ブロックが 6 個並ぶ。
- **修正案**: `_finalize(job_id, status, *, completed_at=None,
  error_details=None)` (もしくは `_record_outcome(...)`) を private helper として抽出。
- **検証**: `tests/unit/services/test_analysis_worker.py` 全 pass。
  `test_analysis_worker_lifecycle.py` の各 error path が同じ assertion を維持。

### G. `update_progress` で `Ellipsis` sentinel を使った 3-state 引数

- **場所**: `src/stock_analyze_system/repositories/analysis_job.py:209,217`
- **症状**: `current_type: str | None = ...` で「unspecified / None / 文字列」の
  3 状態を表現。`Ellipsis` を sentinel に使うパターンは本リポジトリ内で他に
  ないため一貫性を欠く。
- **修正案** (どちらか):
  1. メソッドを 2 つに分割: `clear_current_type(job_id)` と
     `set_current_type(job_id, value)` (推奨)
  2. `_UNSET = object()` を module-level に置き、型注釈は `str | None | _UnsetT`
- **検証**: `tests/unit/repositories/test_analysis_job_repo.py` の
  `update_progress` 関連ケース全 pass。

### H. `progress_total: Mapped[int] = mapped_column(default=4)` のマジック値

- **場所**: `src/stock_analyze_system/models/analysis_job.py:31`
- **症状**: `4` は `len(ANALYSIS_TYPE_NAMES)` のハードコード。analysis_types を
  追加 / 削減した瞬間にズレる。
- **修正案** (どちらか):
  1. default を削除 (worker `started` イベントで実値が必ず入る)
  2. `default=len(ANALYSIS_TYPE_NAMES)` に変更し、循環 import 回避のため
     module 内で評価
- **検証**: AnalysisJob の直接 INSERT (テストや E2E) で値が想定通りであること
- **依存**: ALEMBIC migration 不要 (default は ORM 側、DB schema には影響なし)
  だが、既存行への影響有無を `PRAGMA table_info(analysis_jobs)` で確認

### I. `RagService` の stream / 非 stream で per-type ループが二重化

- **場所**:
  - stream: `src/stock_analyze_system/services/rag_service.py:284-348`
  - 非 stream: `src/stock_analyze_system/services/rag_service.py:361-402`
- **症状**: 「cache → placeholder → analyze → save → ハンドラ」のフローが両方に
  存在し、ハンドラだけが「event を積む vs warning ログ + skip」で異なる。
  ADR-004 では「両者で空セクションの扱いも同一にする」と明記されているが
  実装は drift しやすい。
- **修正案**: per-type 処理を `_process_one(filing, atype, sections) ->
  _PerTypeOutcome` のような 1 関数に抽出し、各エントリポイントは
  outcome → イベント or 結果 list の整形だけする。
  `_PerTypeOutcome` は `dataclass` で `kind: Literal["cached","done","skipped","error"]`
  + 関連フィールド。
- **検証**: 既存 stream / 非 stream テストすべて pass。`A` の async generator
  化と整合させる必要があるため、A と同一コミットで進めるのが安全。
- **依存**: A と同時に進めるのが望ましい

### J. `_persist_qa_history` が private 属性 `_session` に reach-in

- **場所**: `src/stock_analyze_system/services/rag_service.py:441`
- **症状**: `getattr(self._qa_history_repo, "_session", None)` で
  `RagQaHistoryRepository._session` の private 属性に依存。
- **修正案**: `RagQaHistoryRepository.session` を property として公開。
  もしくは savepoint 制御自体を repo 内 (`async def add_with_savepoint(...)`)
  に移す。
- **検証**: `tests/unit/services/test_rag_service.py` の Q&A 履歴系
  (`ask_question` 失敗時のセッション汚染防止) が pass を維持。

---

## 3. Round 3 — コメント / hygiene (低価値・任意)

### K. "narrating-the-change" コメントの削減

- **箇所候補**:
  - `rag_service.py:196-197` ("Empty content would otherwise round-trip…")
  - `rag_service.py:316-318` ("Cached placeholder rows keep skipped semantics…")
  - `rag_service.py:358` ("Skip the parse-then-reserialize round trip…")
  - `analysis_worker.py:219-220` ("Failing here is much cheaper than discovering…")
  - `pageindex/service.py:421-426` ("必ず wrapper を通す…")
- **方針**: 「**なぜ**」を残し「**何をしたか / どの commit から変更したか**」は削除。
  ただし `pageindex/service.py:421-426` は wrapper を経由する unsubstituted call
  が past bug を再発させる WHY なので、コメントを 1 行に圧縮するに留める。
- **検証**: なし (コメント変更のみ、テスト影響なし)

---

## 4. Skip 推奨 (debatable)

| 項目 | エビデンス | Skip 理由 |
|---|---|---|
| `POST /api/analysis-jobs` の 3 段 dedup を 1 段に集約 | `web/routes/analysis_jobs.py:65-83` + `analysis_queue.py:33-58` + repo | コミット `fd80a13` で意図的に追加した defense-in-depth。rate limit を dup POST で消費しないための pre-check が消える |
| `_enqueue_lock` 削除 | `analysis_queue.py:33` | `IntegrityError` fallback だけに依存するのはエラー経路でしか確認されないため運用リスク |
| `setup_services` を per-job 呼ばない | `analysis_worker.py:204-209` | LLM ~25-55s/call に対し ms 単位のオーバヘッド。最適化価値小 |
| `model_name == "structural-placeholder"` sentinel 廃止 | `rag_service.py:34, 317` | schema 変更 (e.g. `result_status` 列) が必要で本リファクタ範囲外 |
| 10-K `competitors` の `Item 1` 流用解消 | `filing_section_extractor.py:34-39` | ADR-004 §Known limitations で明示済み |
| `update_progress` per-event commit を batch 化 | `analysis_job.py:204-230` | SQLite + 10 commits/job は現スケールで無問題 |
| `UPDATE ... RETURNING` で 1 round-trip 化 | `analysis_job.py:73-113` | LLM コストに対し dwarf |
| `_job_to_dict` の ISO 変換重複解消 | `web/routes/analysis_jobs.py:27-49` | 既存 `api.py` でも同 pattern。本ブランチで横展開は scope creep |

---

## 5. 検証要件 (各 fix 共通)

- 必須テストセット:
  ```bash
  scripts/infisical-run uv run pytest \
    tests/unit/services/test_rag_service.py \
    tests/unit/services/test_filing_section_extractor.py \
    tests/unit/services/test_analysis_worker.py \
    tests/unit/services/test_analysis_queue.py \
    tests/unit/repositories/test_analysis_job_repo.py \
    tests/unit/web/test_analysis_jobs.py \
    -q
  ```
- E2E (1 件): `analysis_jobs` を 1 件 enqueue → 完走 → `pipeline='extractor'` 上書き
  確認 (`docs/step3-reasoning-runaway-verification.md` §R.6 と同手順)
- whitespace: `git diff --check $BASE..HEAD` が exit=0

---

## 6. 推奨コミット分割

| コミット | 含めるもの | type |
|---|---|---|
| 1 | A + I (stream 真化 + per-type 共通化) | `refactor(rag):` |
| 2 | B + C (死コード削除) | `refactor:` |
| 3 | D (regex skip) | `fix(extractor):` |
| 4 | E (`now_utc` 集約) | `refactor:` |
| 5 | F + G + H (worker / repo 整理) | `refactor:` |
| 6 | J (`_session` 漏れ) | `refactor(rag):` |
| 7 | K (コメント整理) | `chore:` |

---

## 7. 進行ステータス

- [x] 0. 候補一覧化 (本ファイル)
- [x] 1. §3 全パターン検証 (B の前提) — `extractor-pattern-verification-2026-05-17.md`
- [x] 2. B 修正可否を判断 — 安全と確定
- [x] 3. Round 1 (A / B / C / D) + I 実装 (2026-05-17)
  - Commit 1 `a9b254a`: A (`_iteration_events` AsyncIterator 化) + I (`_process_one` / `_PerTypeOutcome` 共通化)
  - Commit 2 `bf26d6a`: B (worker `IndexBuildError` ハンドラ削除) + C (`PageIndexService.preflight` 削除)
  - Commit 3 `1af786f`: D (`_regex_extract` の `start + 10` → `start_match.end()`)
  - Fix-up `dd98f64`: review 指摘の cached JSON decode 漏れ + `run_full_analysis` の runtime error swallow 回帰修正
  - 検証: §5 必須 unit 119 pass / `git diff --check` clean /
    E2E filing 203 (US_RXRX 2024 10-K, no cache) で 4/4 completed,
    `pipeline='extractor'`, `raw_answer` fallback 0 件 (3 min 9 sec)
- [x] 4. Round 2 (E / F / G / H / J) 実装 (2026-05-17)
  - Commit 4 `017f635`: E (`now_utc` を `shared/time_utils.py` に集約、3 ファイル統合)
  - Commit 5 `1b0c6b5`: F (worker `_finalize` 抽出) + G (`update_progress` から
    `current_type` を `set_current_type` / `clear_current_type` に分離) +
    H (`progress_total` default を `len(ANALYSIS_TYPE_NAMES)` 派生に)
  - Commit 6 `bb6e0cb`: J (`BaseRepository.session` property 公開、
    `rag_service` の `_session` reach-in 解消)
  - 検証: §5 + 周辺 unit 149 pass / `git diff --check` clean /
    E2E filing 2 (US_AAPL 2025 10-K, no cache) で 4/4 completed,
    `pipeline='extractor'`, `raw_answer` fallback 0 件 (72 sec)
- [ ] 5. Round 3 (K) 実装

---

## 8. 関連参照

- ADR: `docs/adr/004-sec-filing-section-extractor.md`
- 検証ログ: `docs/step3-reasoning-runaway-verification.md`
- E2E 検証: `docs/adr-004-e2e-verification.md`
- メモリ: `feedback_typeddict_placement.md` (TypedDict は関数より前に置く)、
  `project_sync_concurrency.md` (sync_company は意図的に直列化)
