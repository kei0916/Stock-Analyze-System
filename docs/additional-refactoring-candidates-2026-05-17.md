# `feat/sec-section-extractor` 追加リファクタリング / 修正候補 (2026-05-17)

`docs/refactoring-candidates-2026-05-17.md` 作成後に、同ドキュメントの
**A-K / Skip 推奨項目のスコープ外**として追加で見つかった候補を記録する。

本ファイルは文体改善ではなく、merge 前に修正・判断した方がよい
correctness / security / operations / UI lifecycle / data integrity のみを扱う。

## 0. 調査前提

| 項目 | 値 |
|---|---|
| ブランチ | `feat/sec-section-extractor` |
| ベース | `master` (merge-base `9cd384f`) |
| 調査時 HEAD | `dd98f64` |
| 除外対象 | `docs/refactoring-candidates-2026-05-17.md` の A-K と Skip 推奨項目 |
| 未コミット差分 | `analysis_queue.py` / `shared/time_utils.py` / `test_time_utils.py` 等は既存候補 E (`now_utc`) として除外 |

サブエージェントを 4 領域に分けて並列レビューした:

- backend queue / worker / repository / model / CLI worker
- web API / frontend analysis-job UI
- SEC extractor / RagService / PageIndex diagnostics / analysis cache
- packaging / config / CLI docs consistency

確認済み:

- `git diff --check 9cd384f..dd98f64` clean (sub-agent)
- `uv lock --check` pass (sub-agent)
- `npm test` pass (sub-agent)
- `uv run stock-analyze screening run --desc` は argparse error を再現
- `uv run stock-analyze --json rag health` は human text を出力することを再現

未実施:

- full `pytest`
- E2E worker run

---

## 1. P0 / Security

### A1. ダッシュボード分析キューの stored XSS リスク

- **場所**:
  - `src/stock_analyze_system/web/static/app.js:1721-1740`
  - `src/stock_analyze_system/web/static/app.js:1766`
- **症状**: `renderQueueRow(job)` が `job.company_id`,
  `job.current_analysis_type`, `job.status` を template string で HTML 化し、
  `listEl.innerHTML = jobs.map(renderQueueRow).join("")` へ流している。
- **なぜ問題か**: `company_id` は現状サービス経由なら概ね `US_...` / `JP_...`
  だが、DB 値・手動投入・将来の ingest 経路が汚染されると dashboard poll 時に
  script 実行され得る。`current_analysis_type` も DB persisted value なので
  HTML として扱う理由がない。
- **なぜ既存ドキュメント外か**: A-K は RAG streaming / worker / repo hygiene
  中心で、frontend DOM injection は含まれていない。
- **修正案**:
  - `renderQueueRow` を string 返却から DOM node 生成へ変更し、
    表示値は `textContent` で入れる。
  - href の `company_id` は `encodeURIComponent(job.company_id)` を使う。
  - `data-job-id` も DOM API (`button.dataset.jobId = String(job.job_id)`) で設定。
- **検証**:
  - `tests/js/analysis_status.test.mjs` とは別に `renderQueueRow` 相当の DOM test を追加。
  - `company_id='<img src=x onerror=...>'` 相当の fixture で HTML として解釈されないこと。

---

## 2. P1 / Correctness

### A2. API/UI が `annual_report` を分析候補に出すが extractor は SEC HTML 専用

- **場所**:
  - `src/stock_analyze_system/web/routes/api.py:23-31`
  - `src/stock_analyze_system/web/routes/api.py:314-349`
  - `src/stock_analyze_system/web/routes/analysis_jobs.py:64-91`
  - `src/stock_analyze_system/services/filing_section_extractor.py:29-82`
  - `src/stock_analyze_system/services/filing_content.py:181-194`
- **症状**: `ANALYSIS_FILING_TYPES` は `annual_report` を含む一方、
  extractor の mapping は `10-K` / `10-Q` / `20-F` / `6-K` 用。
  EDINET `annual_report` は `converted.pdf` のみ保存され、extractor は
  `raw/*.htm` を探すため全 section が空になる。
- **なぜ問題か**: 日本企業の年次報告が UI の対象決算に出て、`決算分析`
  から enqueue できる。しかし worker では SEC HTML 固定章抽出が成立せず、
  全 analysis_type が失敗または空扱いになる。ユーザー視点では操作可能なのに
  確実に失敗する。
- **なぜ既存ドキュメント外か**: 既存の known limitation は 10-K competition
  subsection 等であり、EDINET/PDF を分析対象として露出する API/UI mismatch は
  含まれていない。
- **修正案**:
  - 方針 1: ADR-004 の対象を SEC のみに固定し、`ANALYSIS_FILING_TYPES` から
    `annual_report` を外す。`POST /api/analysis-jobs` でも
    `filing.source == "SEC"` かつ supported filing_type のみ許可する。
  - 方針 2: EDINET/PDF 用 extractor を別途実装する。ただし ADR-004 とは別件。
  - `6-K` を UI 候補に含めるかどうかも方針を明示する
    (extractor には `_FULL_TEXT_FALLBACK` があるが現 API 候補には無い)。
- **検証**:
  - `annual_report` filing を seed し、`rag/filing_options` に出ない、または
    create job が 400/422 で拒否されること。
  - SEC `10-K` / `10-Q` / `20-F` は従来どおり候補に出ること。

### A3. `pageindex.enabled=false` で定型分析ワーカーまで無効化される

- **場所**:
  - `src/stock_analyze_system/cli/container.py:147-176`
  - `src/stock_analyze_system/services/analysis_worker.py:197-199`
  - `src/stock_analyze_system/shared/clients.py:57-61`
- **症状**: `RagService` は `config.pageindex.enabled` が true のときだけ構築される。
  worker は `rag_service is None` なら dequeue 済み job を failed にする。
- **なぜ問題か**: ADR-004 後の定型分析は extractor + `LlmClient.completion`
  であり、章抽出には PageIndex が不要。`pageindex.enabled=false` は自由質問 /
  index 機能だけを無効化する設定に見えるが、実際には分析ジョブ全体を失敗させる。
  `config/settings.yaml.example` では `pageindex.enabled: false` なので、新規利用者ほど
  失敗しやすい。
- **なぜ既存ドキュメント外か**: A/B/C は PageIndex preflight / dead code の話であり、
  RagService 構築条件による worker job failure は扱っていない。
- **修正案**:
  - `RagService` は PageIndex 無効でも構築する。
  - `ask_question` / `build_index` / `get_index_status` だけ PageIndex disabled を
    503/明示 error にする。
  - `ClientBundle` も定型分析に必要な `LlmClient` は PageIndex と独立して構築する。
- **検証**:
  - `pageindex.enabled=false` で `run_full_analysis_stream` が動く unit/integration test。
  - 同設定で `rag ask` / `rag index` が明示的に disabled error を返す test。
  - 既存 `test_worker_fails_when_rag_disabled` 相当は期待値を見直す。

### A4. runbook の llama-server 起動例が ADR-004 の必須構成と矛盾

- **場所**:
  - `docs/analysis-jobs-runbook.md:28-35`
  - `docs/adr/004-sec-filing-section-extractor.md:37-43`
  - `docs/adr/004-sec-filing-section-extractor.md:94-100`
  - `docs/adr/004-sec-filing-section-extractor.md:124-128`
- **症状**: runbook は `--ctx-size 32768 --parallel 4` を案内しているが、
  ADR-004 は step 3 検証済み構成として
  `--ctx-size 131072 --parallel 1 --jinja --n-gpu-layers 99` を前提にしている。
- **なぜ問題か**: 旧構成は slot ctx が 8192 相当になり、実 10-K の `mda` /
  `risk_factors` section が context overflow する。運用手順に従うと再現性のある
  failure を招く。
- **なぜ既存ドキュメント外か**: 既存 K はコメント hygiene であり、運用コマンドの
  correctness mismatch ではない。
- **修正案**:
  - runbook の llama-server 起動例を ADR-004 検証済み構成へ更新。
  - `--parallel` と effective slot ctx の関係を 1 行で明記。
- **検証**:
  - docs の該当コマンドと `docs/step3-reasoning-runaway-verification.md` の構成が一致。

### A5. 非 stream `run_full_analysis()` が全件抽出不能でも成功扱いになり得る

- **場所**:
  - `src/stock_analyze_system/services/filing_section_extractor.py:114-120`
  - `src/stock_analyze_system/services/rag_service.py:368-377`
  - `src/stock_analyze_system/services/rag_service.py:422-446`
- **症状**: raw HTML が無いと extractor は全キー空の dict を返す。
  `_process_one` は非構造的な空 section を `kind="error", cause=None` として返し、
  `run_full_analysis()` は cause None を warning + continue するため、最悪
  `[]` を成功返却する。
- **なぜ問題か**: CLI / 非 stream caller は「分析成功、結果ゼロ」に見える。
  content absence / extractor 全体失敗と「特定章だけ missing」を同じ扱いにしている。
- **なぜ既存ドキュメント外か**: A/I は stream / non-stream 共通化の話だが、
  whole-filing extraction failure が successful empty result になる問題は別。
- **修正案**:
  - extractor が raw HTML 欠落を明示的な例外または metadata 付き outcome として返す。
  - 少なくとも `run_full_analysis()` で全 analysis_type が non-structural missing の場合は
    raise する。
  - stream 側も extraction-level error と per-type missing を区別する。
- **検証**:
  - storage_path に `converted.pdf` のみ、または raw HTML 無しの fixture で
    `run_full_analysis()` が失敗すること。
  - 10-Q `business_summary` / `competitors` の structural empty は従来どおり
    placeholder/skipped になること。

### A6. `enqueue()` の過去 failed/cancelled dismiss が新規作成と非 atomic

- **場所**:
  - `src/stock_analyze_system/services/analysis_queue.py:38-53`
  - `src/stock_analyze_system/repositories/analysis_job.py:167-186`
- **症状**: `enqueue()` は過去 failed/cancelled を dismiss してから新規 job を作る。
  しかし `dismiss_past_for_filing()` は内部で commit するため、その後の create /
  commit が失敗すると過去の失敗記録だけが非表示になる。
- **なぜ問題か**: 新しい job が存在しないのに、直前の failure history が UI から消える。
  調査可能性と retry UX が悪化する。
- **なぜ既存ドキュメント外か**: Skip の 3 段 dedup / rate-limit は意図的設計だが、
  dismiss と create の transaction atomicity は扱っていない。
- **修正案**:
  - repo method の内部 commit をやめ、service の 1 transaction で
    dismiss + create + commit する。
  - 既存 repo API の commit 責務を揃えるなら、queue 専用 transactional helper を追加。
- **検証**:
  - `repo.create` / `session.commit` を失敗させ、過去 job の `dismissed_at` が
    rollback される unit test。
  - happy path で過去 failed/cancelled が dismiss され、新 job が pending になること。

### A7. worker が `job.company_id` と `filing.company_id` の整合性を確認しない

- **場所**:
  - `src/stock_analyze_system/models/analysis_job.py:25-26`
  - `src/stock_analyze_system/repositories/analysis_job.py:18-25`
  - `src/stock_analyze_system/services/analysis_worker.py:200-204`
- **症状**: `AnalysisJob` は `company_id` と `filing_id` を独立 FK として持つ。
  worker は `filing_id` で filing を取得するだけで、`filing.company_id == job.company_id`
  を検証しない。
- **なぜ問題か**: API 境界では ownership check が入っているが、DB 手動投入 /
  内部 caller / 将来の import 経路で不整合 job が作られると、UI 上は会社 A の job
  なのに会社 B の filing を分析できる。
- **なぜ既存ドキュメント外か**: A-K には queue/worker の data integrity invariant は無い。
- **修正案**:
  - worker 側で filing 取得後に company_id を検証し、不一致なら failed にする。
  - 可能なら repository create も filing ownership を受け取って検証する。
  - DB レベル制約は composite FK が必要で影響範囲が大きいため別判断。
- **検証**:
  - mismatch job を seed し、worker が analysis を実行せず failed にする test。

---

## 3. P2 / UI Lifecycle

### A8. 分析タブの initial in-progress detection が早すぎる

- **場所**:
  - `src/stock_analyze_system/web/templates/stocks/_tab_analysis.html:7`
  - `src/stock_analyze_system/web/static/app.js:850-872`
  - `src/stock_analyze_system/web/static/app.js:1218-1247`
- **症状**: filing select は初期表示で空の「読み込み中...」option を持つ。
  実際の filing options は非同期 fetch 後に設定されるが、in-progress job 検出は
  `queueMicrotask()` で即時実行されるため、多くの場合まだ空 value を見て終了する。
- **なぜ問題か**: active job がある状態で分析タブを開いても、進行中 job に自動接続されず、
  ユーザーが selector を変えるか再実行を押すまで進捗が見えない。
- **なぜ既存ドキュメント外か**: backend streaming 改善 A とは別で、frontend 初期化順序の問題。
- **修正案**:
  - filing options fetch 完了後、`filingSelect.value` を設定した直後に
    `detectInProgress(filingSelect.value)` を呼ぶ。
  - 初期 microtask は削除。
- **検証**:
  - active job fixture で tab init 後に `/api/analysis-jobs?...pending,running...`
    が呼ばれる JS test。

### A9. 古い polling interval が現在選択中の filing 結果を上書きし得る

- **場所**:
  - `src/stock_analyze_system/web/static/app.js:1119-1150`
  - `src/stock_analyze_system/web/static/app.js:1135-1139`
  - `src/stock_analyze_system/web/static/app.js:1206-1215`
- **症状**: `pollJob(jobId, filingIdForReload)` は開始時の filing id を保持し、
  interval を cancel しない。ユーザーが別 filing を選択した後、古い job が完了すると
  `loadAnalyses(oldFilingId)` が走り、現在表示中の結果を上書きする。
- **なぜ問題か**: UI select と表示結果がズレる。分析完了タイミングで発生するため再現時に
  直感的に分かりにくい。
- **なぜ既存ドキュメント外か**: frontend state lifecycle の問題。
- **修正案**:
  - panel 単位で active poll token / AbortController 相当を持つ。
  - 完了時に `filingSelect.value === filingIdForReload` を確認してから reload。
  - selector change で旧 interval を clear する。
- **検証**:
  - job A polling 中に selector を B へ変更し、A 完了時に B の表示が上書きされない test。

### A10. persisted progress が status polling UI に反映されない

- **場所**:
  - `src/stock_analyze_system/web/static/app.js:1005-1058`
  - `src/stock_analyze_system/web/static/app.js:1063-1079`
- **症状**: `jobToEvents()` は running job の `progress_current` を `phase.index`
  として渡すが、`phase` handler は `state.completed` や progress bar width を更新しない。
  width 更新は `done/cached/skipped` event のみ。
- **なぜ問題か**: status polling だけで復元した場合、DB には progress があるのに UI は
  `0 / total` 付近に見え、terminal status で急に 100% へ飛ぶ。
- **なぜ既存ドキュメント外か**: A は backend stream が真に streaming でない問題。
  こちらは persisted job status を frontend event へ変換する問題。
- **修正案**:
  - `phase` handler で `state.completed = evt.index` を反映し、bar width /
    count を更新する。
  - running job で `current_analysis_type` が null でも `progress_current` /
    `progress_total` を表示する event を作る。
- **検証**:
  - running job `{progress_current: 2, progress_total: 4}` を feed し、
    UI が `2 / 4` と 50% を表示する JS test。

---

## 4. P2 / Diagnostics and Read Models

### A11. PageIndex diagnostic wrapper が例外時に記録せず stale になり得る

- **場所**:
  - `src/stock_analyze_system/services/pageindex/diagnostics.py:138-163`
  - `src/stock_analyze_system/services/pageindex/diagnostics.py:177-196`
  - `src/stock_analyze_system/services/pageindex/service.py:322-331`
- **症状**: `wrapped_llm_completion` / `wrapped_llm_acompletion` は委譲先 LLM 呼び出しが
  成功した後だけ `_record(diag)` する。LLM 呼び出し自体が timeout / connection error
  で raise すると診断が残らない。
- **なぜ問題か**: `PageIndexService._build_index_async` は例外時に
  `get_last_diagnostic()` を `IndexBuildError.diagnostic` へ載せるため、初回失敗では
  `None`、後続失敗では前回成功の stale diagnostic になり得る。
- **なぜ既存ドキュメント外か**: C は unused preflight の削除、K は comment hygiene。
  diagnostic correctness は別問題。
- **修正案**:
  - wrapper 内で try/except し、例外時にも `error_type`, `error_message`,
    `prompt_head`, `model`, `max_tokens`, `max_tokens_effective` を記録してから再 raise。
  - `reset_diagnostic()` の呼び出し境界を維持し、stale を防ぐ。
- **検証**:
  - `pi_utils.llm_completion` / `llm_acompletion` が raise する unit test で
    diagnostic に error 情報が残ること。

### A12. `pipeline='extractor'` filter が recent/count 経路に未適用

- **場所**:
  - `src/stock_analyze_system/repositories/analysis.py:27-43`
  - `src/stock_analyze_system/repositories/analysis.py:47-53`
  - `src/stock_analyze_system/services/analysis.py:12-16`
  - `src/stock_analyze_system/web/routes/dashboard.py:100-110`
- **症状**: `get_by_type` / `get_analyses` は `pipeline == PIPELINE_EXTRACTOR`
  で filter するが、`list_recent()` と `count_all()` は legacy rows を含む。
- **なぜ問題か**: ADR-004 で PageIndex-era cache を extractor result として再利用しない
  方針にしたのに、dashboard の「分析件数」「最近の分析」には stale PageIndex-era rows が
  混ざる。
- **なぜ既存ドキュメント外か**: `model_name == structural-placeholder` sentinel や
  cache 識別の skip 項目とは別で、read model 側の filter 漏れ。
- **修正案**:
  - `AnalysisRepository.list_recent()` に `pipeline == PIPELINE_EXTRACTOR` を追加。
  - `AnalysisService.count_all()` も extractor only の count method にするか、
    名前を `count_extractor` 等に変更する。
  - legacy count を残すなら dashboard 表示名を分ける。
- **検証**:
  - `pipeline is NULL` と `pipeline='extractor'` の rows を seed し、
    dashboard/recent/count が extractor のみを見る test。

---

## 5. P3 / Low-Risk Hardening

### A13. `/api/analysis-jobs` の `limit` が無制限 / 負数許容

- **場所**:
  - `src/stock_analyze_system/web/routes/analysis_jobs.py:106-132`
  - `src/stock_analyze_system/repositories/analysis_job.py:49-71`
- **症状**: `limit: int = 20` を validation せず SQL `LIMIT` に渡している。
  SQLite では `LIMIT -1` が実質無制限になり得る。
- **なぜ問題か**: polling endpoint なので、悪意または誤操作で大量 rows を返しやすい。
- **なぜ既存ドキュメント外か**: POST dedup / rate-limit skip 項目とは別の query param validation。
- **修正案**:
  - FastAPI `Query(20, ge=1, le=100)` などで上限を明示。
  - repository 側にも defensive clamp を入れるかは方針次第。
- **検証**:
  - `limit=-1`, `limit=0`, `limit=100000` が 422/400 になる test。

### A14. failed / stale reset 時に `current_analysis_type` が残る

- **場所**:
  - `src/stock_analyze_system/services/analysis_worker.py:145-175`
  - `src/stock_analyze_system/services/analysis_worker.py:248-252`
  - `src/stock_analyze_system/repositories/analysis_job.py:188-201`
- **症状**: `current_analysis_type` は stream が正常に最後まで回った後だけ clear される。
  `phase` 後に unexpected failure した場合や、worker 起動時の
  `reset_running_to_failed()` では stale の active type が残る。
- **なぜ問題か**: failed job が UI 上で「今も特定タイプ実行中」のように見える。
  dashboard queue の表示にも stale value が出る。
- **なぜ既存ドキュメント外か**: F は `_execute_with_status` の重複 helper 抽出、
  G は `update_progress` sentinel の API 設計であり、失敗状態の正しさではない。
- **修正案**:
  - `update_status(..., status in terminal)` で `current_analysis_type=None` を
    option 指定できるようにする。
  - `reset_running_to_failed()` でも `current_analysis_type=None` を設定。
- **検証**:
  - `phase` 後に exception を投げる worker test で failed row の
    `current_analysis_type is None` を確認。
  - stale running reset test。

### A15. runbook の `index_build_error` 記述が現行 `extraction_error` と不一致

- **場所**:
  - `docs/analysis-jobs-runbook.md:54-63`
  - `src/stock_analyze_system/services/analysis_worker.py:154-165`
  - `src/stock_analyze_system/services/analysis_worker.py:208-214`
- **症状**: runbook は ADR-004 後の preflight / extractor failure を
  `error_details.index_build_error` として案内しているが、worker は
  `error_details.extraction_error` に保存する。
- **なぜ問題か**: 障害調査時に operator が誤った key を探す。
- **なぜ既存ドキュメント外か**: B は dead handler 削除であり、運用 runbook の
  debug contract mismatch ではない。
- **修正案**:
  - runbook の表を `extraction_error` / `failed_types` / legacy `index_build_error`
    に分ける。
  - preflight failure は step 3 LLM probe failure と明記。
- **検証**:
  - docs only。可能なら worker error_details fixture と runbook の key 名を static check。

### A16. `HOW_TO_USE.md` が存在しない `screening run --desc` を記載

- **場所**:
  - `HOW_TO_USE.md:134-137`
  - `src/stock_analyze_system/cli/screening.py:45-48`
- **症状**: docs は `--asc / --desc` と記載しているが、parser は `--asc`
  のみ定義し、default が descending。
- **なぜ問題か**: 記載どおり `stock-analyze screening run --desc` を実行すると
  argparse の unrecognized arguments になる。
- **なぜ既存ドキュメント外か**: 既存レビューは docs 文体を対象外にしているが、
  これは壊れたコマンド例。
- **修正案**:
  - docs を `--asc (省略時は降順)` に直す、または parser に `--desc` を追加する。
  - UX 的には explicit `--desc` を受ける方が自然。
- **検証**:
  - parser test に `--desc` を追加する、または docs のみ修正なら `--desc` 記載が消えたこと。

### A17. global `--json` が `rag` subcommand では上書きされる

- **場所**:
  - `src/stock_analyze_system/cli/app.py:20`
  - `src/stock_analyze_system/cli/rag.py:20-22`
  - `HOW_TO_USE.md:41-47`
- **症状**: root parser が global `--json` を持つ一方、`rag` parser も同じ
  destination `json` を定義している。`stock-analyze --json rag health` は
  subparser 側 default に上書きされ、human text を出力する。
- **なぜ問題か**: 「グローバルオプション」としての契約が破れている。
  automation から JSON を期待した場合に壊れる。
- **なぜ既存ドキュメント外か**: CLI app / docs consistency で、A-K には含まれない。
- **修正案**:
  - `rag` 側の `--json` default を `None` にして root の値を尊重する。
  - または root `--json` を廃止し、各 subcommand local option として docs を更新する。
  - 推奨は root option を尊重しつつ、`stock-analyze rag --json ...` も許容。
- **検証**:
  - parser test:
    - `stock-analyze --json rag health` => `args.json is True`
    - `stock-analyze rag --json health` => `args.json is True`
    - `stock-analyze rag health` => `args.json is False`

---

## 6. 推奨対応順

| 優先 | 候補 | 理由 |
|---|---|---|
| 1 | A1 | security。小さく閉じられる |
| 2 | A2 / A3 / A4 | ADR-004 の運用・対象範囲と実装のズレ。失敗率に直結 |
| 3 | A5 / A6 / A7 | backend correctness / data integrity |
| 4 | A8 / A9 / A10 | UI の信頼性。UX 劣化だが data loss ではない |
| 5 | A11 / A12 | diagnostics / dashboard read model の精度 |
| 6 | A13-A17 | low-risk hardening と docs/CLI consistency |

## 7. 最小検証セット案

修正する候補に応じて個別 test を追加したうえで、最低限以下を実行する:

```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_rag_service.py \
  tests/unit/services/test_filing_section_extractor.py \
  tests/unit/services/test_analysis_worker.py \
  tests/unit/services/test_analysis_queue.py \
  tests/unit/repositories/test_analysis_job_repo.py \
  tests/unit/repositories/test_other_repos.py \
  tests/unit/web/test_analysis_jobs.py \
  tests/unit/cli/test_app.py \
  tests/unit/cli/test_worker_cli.py \
  tests/unit/cli/test_stooq_cli.py \
  -q

npm test
git diff --check
```

UI lifecycle 修正 (A8-A10) を入れる場合は、可能なら JS unit test を増やす。
worker/config 修正 (A2-A7) を入れる場合は、少なくとも 1 件の
analysis job enqueue -> worker completion/failure integration test を追加する。
