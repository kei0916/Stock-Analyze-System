# 定型分析失敗 (`Processing failed` 連発) 多角的根本原因レポート

調査日: 2026-05-15
ブランチ: `fix/analysis-failures-root-cause`
対象: 銘柄ごとの定型分析ジョブが 0/4 進捗・`error_details = {"failed_types":[{"type":null,"message":"Processing failed"}]}` で連続失敗する事象 (例: US_RXRX FY2024 10-K, US_TEM 10-K/10-Q, US_GRRR 6-K)。

---

## 1. 観測された事実 (Phase 1)

`data/stock_analyze.db` の `analysis_jobs` テーブル (直近16件):

| Job | Date | ticker / filing | status | progress | error_details |
|---|---|---|---|---|---|
| #4 | 2026-05-13 11:38 | US_MU 10-Q | completed | 4/4 | — |
| **#5** | 2026-05-13 12:05 | US_TSM 20-F | **failed** | 4/4 | `litellm.InternalServerError: OpenAIException - Connection error.` (3 types) |
| **#6-12** | 2026-05-13 | US_TEM 10-Q/10-K | **failed** | **0/4** | `{"type": null, "message": "Processing failed"}` |
| **#13-15** | 2026-05-14〜15 | US_GRRR 6-K | failed | 0/4 | 同上 |
| **#16** | 2026-05-15 14:06-14:28 | **US_RXRX 10-K** | failed | 0/4 | 同上 |

`logs/converted.pdf_2026*.json` の失敗時ログは全件 ~332 バイトで完全に同型:

```json
[
  {"toc_content": null, "toc_page_list": [], "page_index_given_in_toc": "no"},
  {"message": "len(group_texts): N"},
  {"message": "generate_toc: []"},
  {"message": "convert_physical_index_to_int: []"},
  {"mode": "process_no_toc", "accuracy": 0, "incorrect_results": []}
]
```

成功時(対照 `logs/converted.pdf_20260513_203857.json`, `logs/converted.pdf_20260507_090858.json`)は `generate_toc` に数百項目の TOC が記録される。

---

## 2. 「Processing failed」の発生点 (確定)

PageIndex ライブラリ `<pageindex-repo>/pageindex/page_index.py:1132`

```python
# meta_processor 内, mode == 'process_no_toc' の最終分岐
raise Exception('Processing failed')
```

発火条件: `accuracy == 0` かつ `len(toc_with_page_number) == 0` (page_index.py:1127〜1132)。

`Stock_Analyze` 側の通り道:
- `rag_service.py:163` — `tree = await self._pageindex.get_or_create_index(filing)` → except に落ちる
- `rag_service.py:166` — `yield {"event": "error", "analysis_type": None, "message": str(exc)}`
- `analysis_worker.py:210-213` — そのまま `failed_types.append({"type": None, "message": "Processing failed"})` で DB に保存

---

## 3. 多角的根本原因(5層)

### 【A層】 LLM 振る舞い — 最有力仮説 (未確定 / 要再現)

> **重要**: 本層は現時点で **仮説** であり確定していない。`finish_reason` / `completion_tokens` / raw 応答が一切永続化されておらず、PageIndex 内部 print 出力(`utils.py:76`)も `infisical-run` 経由で stdout が捕捉されていないため、Phase 1 の証拠単独では裏付けられない。第6節の再現テストで確定する。

**仮説**: `Qwen3.6-27B-Q4_K_M` が `enable_thinking=false` を遵守せず、`<think>...` に全 32768 トークンを消費している。

仮説の根拠(状況証拠):

1. `generate_toc_init` (page_index.py:594-636) は `llm_completion(... max_tokens=32768)` を呼ぶ
2. `finish_reason == 'max_output_reached'` (length) で 3 回リトライ。各回 `extract_json` を試みるが、`</think>` タグが応答末尾に出ないと `extract_json` は JSON を切り出せず `{}` を返す (utils.py:285)
3. `result = result['items']` が走らず、salvage 判定 `isinstance(result, list) and len(result) > 0` も False
4. 3 回失敗で `return []` (page_index.py:635-636)
5. `process_no_toc` → `meta_processor` → `Exception('Processing failed')`

状況証拠:
- **小さなPDF (GRRR 6-K, 22KB) も失敗** — "コンテキスト超過"だけでは説明できず、入力サイズに非依存な原因 (思考トークン枯渇 / chat_template 不整合 / サーバ側 sampling 設定変動 等) を示唆
- **TSM Job #5 (5/13 12:05) の `Connection error` 直後から症状切替** — llama-server の挙動が境界
- `extract_json` (utils.py:213) は `'</think>' in content` だけで切り出すため、`<think>` が未閉だと content 末尾が思考のみで JSON が無い

代替仮説 (要排除):
- llamacpp サーバ側で `response_format={"type":"json_object"}` の grammar 制約が常に空配列に縛る状態
- 異なる model / quantization がロードされた
- `Connection error` が完全に解消しておらず単に retry 後の空応答化
- Qwen3.6 が JSON-mode で空 `{"items": []}` を返す挙動への遷移(thinking とは別)

これらは第6節の再現テストで `finish_reason` / `completion_tokens` / 応答 head を採取することで初めて区別できる。

### 【B層】 PageIndex ライブラリ設計 — 根本原因を増幅

| 問題 | 場所 | 影響 |
|---|---|---|
| 失敗を例外でなく空配列で握りつぶす | `page_index.py:635-636` | "LLM応答ゼロ" と "本当にTOCが無い" を区別不能 |
| `extract_json` が JSON 失敗時に `{}` を返す | `utils.py:285` | silent fail で上位に伝搬しない |
| `max_tokens=32768` がハードコード | `page_index.py:611` | アプリ側 `config/settings.yaml` の `max_tokens: 16384` が無視 |
| `accuracy==0` 経路が唯一のシグナル | `page_index.py:1127-1132` | 例外メッセージが「Processing failed」だけで診断情報ゼロ |

### 【C層】 Stock_Analyze ワーカー — エラー UX 欠陥

`src/stock_analyze_system/services/analysis_worker.py:206-213`

```python
elif etype == "error":
    if "index" in event:
        progress_index = event.get("index", progress_index) + 1
        await repo.update_progress(job.id, current=progress_index)
    failed_types.append({
        "type": event.get("analysis_type"),
        "message": event.get("message", ""),
    })
```

- **「indexing 失敗」と「analysis 失敗」が同じ `failed_types` バケットに混ざる** ため、`type: null` という曖昧な記録となり、UI で切り分け表示不可
- `event["event"] == "error"` でも `analysis_type is None` の場合は「PageIndex 段階で全分析が不可能」を意味するが、専用エラー型として扱われていない

### 【D層】 観測性インフラ — 根本原因に気付けない構造

| 問題 | 証拠 |
|---|---|
| `logs/worker.log` `logs/web-server.log` が infisical CLI の対話ログインエラーで上書きされ実体ログが残らない | 両ファイル 699 byte、内容は `Failed to automatically trigger login flow` 等 |
| PageIndex の `print(f'... finish={...}, prompt_tokens={...}, completion_tokens={...}')` (utils.py:76) が stdout キャプチャ抜け | `scripts/infisical-run uv run stock-analyze worker` で stdout がファイル化されない構成 |
| `LlmClient.health_check()` がジョブ実行前に呼ばれない | `analysis_worker.py:129` の `_execute_with_status` 冒頭にチェックなし |
| llama-server (バックエンド) のログが収集されていない | systemd unit 例にもログ設定なし |
| `error_details` に `str(exc)` しか入らない | finish_reason, prompt_tokens, completion_tokens, raw LLM response head が一切残らない |

### 【E層】 アーキテクチャ前提 — 過去の Root Cause が未着手で再発

`MEMORY` の `project_rag_rootcause.md` に **「推論モデル→非推論モデルへの2モデル構成移行計画」** が記録されている。これは「Qwen3.6 を単一構成で運用すると PageIndex 経路で不安定」という過去の認識。移行未完で**単一 Qwen3.6 運用が根本不安定**という構造問題。

---

## 4. 反証された仮説

| 仮説 | 反証 |
|---|---|
| `raw/*.htm` (オリジナルHTML) 欠落 | RXRX/TEM/GRRR 全て raw/*.htm 存在 |
| PDF 変換失敗 | `converted.pdf` 全て存在し、PageIndex logger も `len(group_texts): N` まで進捗 |
| コード変更による回帰 | 5/13 11:48 成功と 12:05 失敗の間にコード変更なし(環境変化のみ) |
| コンテキスト長超過 | 22KB の GRRR 6-K も同一失敗パターン |
| llamacpp の `response_format={"type":"json_object"}` 非対応 | 4月までは同条件で成功していた(`logs/converted.pdf_20260507_090858.json` 等) |

---

## 5. 修復方針 — 1アクション1コミット (推奨順序)

> **指針**: 構造変更(2モデル化等)に進む前に、まず A 層を確定させる証拠採取基盤を入れる。`from .utils import *` (page_index.py:8) や `tree_parser` 例外による戻り値検証不能(service.py:282→300)など、設計を誤りやすい技術的境界があるため、各項目は実コードでの注入点を明記する。

### P0-1: 観測性 — worker stdout 永続化 + PageIndex LLM 診断の構造化保存

**コミット 1**: 二つの作業を1コミットで:

- `scripts/start-worker.sh` (新規) または `infisical-run` ラッパで、worker の stdout/stderr を `data/logs/worker-YYYYMMDD-HHMMSS.log` にローテート保存(`tee` + ロック)
- `services/pageindex/compat.py` で **PageIndex `page_index` モジュール名前空間の `llm_completion` / `llm_acompletion` を setattr で差し替え** (重要: `pageindex.utils.llm_completion` のみのパッチでは効かない — `page_index.py:8` の `from .utils import *` により `pageindex.page_index` 側で別バインドを保持しているため、`pageindex.page_index.llm_completion = <wrapper>` でなければ `generate_toc_init` 等の呼び出しを捕捉できない)。ラッパは最後の `finish_reason` / `prompt_tokens` / `completion_tokens` / 応答先頭200文字を thread-local に保存
- thread-local 診断は `_build_index_async` の `try: ... tree_parser(...) except Exception as exc: ...` でキャプチャし、`IndexBuildError(... , diagnostic=...)` として再raise

### P0-2: PageIndex 同等の JSON-mode preflight

**コミット 2**: `LlmClient.health_check()` ではなく、PageIndex 経路と同条件の preflight を別途追加:

- `services/pageindex/service.py` に `async def preflight() -> dict` を新設し、`response_format={"type":"json_object"}` + `max_tokens=512` + `extra_body.chat_template_kwargs.enable_thinking=<config値>` で `Return JSON: {"ok": 1}` を投げて検証
- `analysis_worker._execute_with_status` 冒頭で実行。失敗時は `error_details = {"phase": "preflight", "diagnostic": {...}}` で即 fail
- `LlmClient.health_check()` (llm_client.py:80) は接続確認用として残し、phaseを分けて両方を順に走らせる

### P1: エラー分類の正常化 (UIまで含む)

**コミット 3**: indexing 失敗を専用キーに分離:

- `analysis_worker.py:206-213`: `etype == "error"` かつ `event.get("analysis_type") is None` (= indexing 段階) のとき、`failed_types.append(...)` ではなく `index_build_error = {"message": ..., "diagnostic": ...}` を別変数に蓄積。最終的に `error_details = {"index_build_error": ..., "failed_types": [...]}` の構造で保存
- `web/routes/analysis_jobs.py`: レスポンス整形側で新キーを透過
- **`web/static/app.js:1070-1080`**: 現状 `failed_types` と `reason` のみ参照しているため、`error_details.index_build_error` を最優先で 1つの error イベントとして push。テンプレート/バッジ側のメッセージも対応
- APIテスト/UIテストで `index_build_error` 経路の表示を固定

### P1: max_tokens / LLM ラッパーの効きをテストで固定

**コミット 4**: PageIndex 内部での実バインド対象を pytest で検証:

- `generate_toc_init` のハードコード `max_tokens=32768` (page_index.py:611) を、コミット1で差し替えた wrapper 経由でクランプ(例: `min(requested, _CLAMP)`)
- `pageindex.page_index.llm_completion` への setattr が `generate_toc_init` の呼び出し時に効いていることを assert するテストを `tests/unit/services/test_pageindex_service.py` に追加(モンキーパッチが効かなくなる回帰を検知)
- 値はコミット1で採取できた `completion_tokens` の実測を見てから決定

### P2: 2モデル構成 (A層が確定してから)

**コミット 5**: コミット1〜2で採取した診断で A 層(thinking 暴走 等)が確定した場合のみ:

- `config.LlmConfig` に `model_tree_search` を追加
- PageIndex の TOC 抽出のみを別モデルに分離するには、`_build_index_async` 内の `opt.model` 差し替えは **PageIndex build 全体に効く** ため不十分。`pageindex.page_index.llm_completion` の wrapper で「呼び出し元が `generate_toc_init` / `generate_toc_continue` か」をスタック/フラグで判別し、その場合のみ別 model + base_url に振り分ける(または PageIndex を fork して明示的注入点を作る)
- どちらの方針を採るかは P0-1 の wrapper 実装後に評価

### P2: 環境ハードニング

**コミット 6**: `scripts/start-llama-server.sh` (新規) と運用ランブック:

- chat_template の `enable_thinking=false` を確実に効かせる llama-server 起動引数(`--jinja` 等)を明示
- 失敗時に必要な情報(`server.log`, `worker-*.log`, DB `error_details`) の参照手順

---

## 6. 検証コマンド (修正前ベースライン取得用)

```bash
# (a) llama-server 起動状態
curl -s http://localhost:8080/v1/models | jq

# (b) JSON-mode + thinking の最小再現テスト
curl -s http://localhost:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "openai/Qwen3.6-27B-Q4_K_M.gguf",
  "messages":[{"role":"user","content":"Return JSON: {\"ok\": true}"}],
  "response_format":{"type":"json_object"},
  "max_tokens":256,
  "extra_body":{"chat_template_kwargs":{"enable_thinking":false}}
}' | jq '.choices[0]'
# 期待: finish_reason="stop", content='{"ok": true}'
# 実害確認: finish_reason="length" や content に <think> が含まれれば A 層確定

# (c) ワーカーを stdout キャプチャ付きで再実行
scripts/infisical-run uv run stock-analyze worker > /tmp/worker_full.log 2>&1 &
# Web から RXRX 10-K を再 enqueue → 失敗後 /tmp/worker_full.log に PageIndex の
# print 出力 (finish=length, prompt_tokens=..., completion_tokens=...) を確認

# (d) DB の最新失敗ジョブ
uv run python -c "
import sqlite3
c = sqlite3.connect('data/stock_analyze.db').cursor()
for r in c.execute(\"SELECT id, company_id, status, current_analysis_type, error_details, progress_current, progress_total, started_at, completed_at FROM analysis_jobs ORDER BY id DESC LIMIT 5\"):
    print(r)
"
```

---

## 7. 関連メモ / 既知の制約

- `MEMORY/project_sync_concurrency.md`: `sync_company / run_daily_update` は直列化済(LLM デッドロック回避) — 並列化禁止
- `MEMORY/feedback_litellm_security.md`: LiteLLM v1.82.7/v1.82.8 はマルウェア — アップグレード禁止
- `MEMORY/project_greenboost.md`: GreenBoost 必須対策との整合確認 (P2 のモデル分離時に再評価)
- 本ブランチ作成時の未コミット WIP: `src/stock_analyze_system/web/routes/analysis_jobs.py`, `tests/unit/web/test_analysis_jobs.py` (background-analysis-queue 系で別件) — 本根本原因修正とは独立

---

## 8. 進捗トラッカー (1アクション1コミット)

- [x] コミット 0: 本レポート作成 (`1bb5b40`) → レビュー反映で更新 (`c80902e`)
- [x] **コミット 1a (P0)**: `cli/app.py` で `setup_logging` 配線、worker/serve から `data/logs/stock_analyze.log` に出力 (`fe0b153`)
- [x] **コミット 1b (P0)**: `services/pageindex/diagnostics.py` で `pageindex.page_index` 名前空間への wrapper 差し替えと contextvars-backed 診断バッファ (`987d5fc`)
- [x] **コミット 1c (P0)**: `IndexBuildError(diagnostic=...)` 拡張、`_build_index_async` の try/except 化、rag_service / analysis_worker への diagnostic 配線 (`ef728f3`)
- [x] **コミット 2 (P0)**: PageIndex 同等の JSON-mode preflight を `PageIndexService.preflight()` に追加し、`AnalysisWorker._run_job` 冒頭から呼んで fail-fast 化 (`6d63653`)
- [x] **コミット 3 (P1)**: `error_details["index_build_error"]` キー新設、`analysis_worker.py` で indexing 失敗を `failed_types` から分離、`web/static/app.js:1070-` を新キー優先で更新 (`3c695e6`)
- [x] **コミット 4 (P1)**: `configure_max_tokens_clamp` を diagnostics モジュールに追加し、`_build_index_async` から `opt.max_tokens` で wrapper をクランプ (`fcc0960`)
- [x] **コミット 5 (P2)**: 運用ランブック (`docs/analysis-jobs-runbook.md`) と llama-server 起動フラグ (`--jinja` 等) の文書化
- [x] **コミット 6 (バグ修正)**: `pageindex.__init__.py` の `from .page_index import *` で submodule が同名関数で隠蔽される問題を解決 (`sys.modules["pageindex.page_index"]` 経由で setattr) (`025aa92`)
- [x] **A 層仮説の検証**: ジョブ#21 で wrapper が正しく動作し、`Task: Add physical page indices ...` 呼び出しで `content_len: 0` を捕捉。手動 curl で Qwen3.6 が `enable_thinking=false` 越しでも `reasoning_content` に思考を出すことを確認。A 層 (思考トークン暴走) 確定
- [~] **コミット 7 (元 P2 / 2モデル構成案)**: **ADR-004 で supersede**。`docs/adr/004-sec-filing-section-extractor.md` の固定セクション抽出方針に移行。本コミットは着手しない

## 9. 方針転換 (2026-05-16)

A 層確定後に「PageIndex 内 TOC 抽出を non-reasoning モデルへ分離する」案を再評価した結果、**`docs/adr/004-sec-filing-section-extractor.md` (SEC 専用固定セクション抽出) に方針転換** した。理由:

- SEC 提出書類は Regulation S-K で章立てが法的に固定されており、iXBRL `*TextBlock` ファクト・HTML 構造・正規表現で **LLM を呼ばずに deterministic に章抽出できる**
- 2モデル構成は 2台目 llama-server 運用が必要で SPOF 構造自体は残る
- 既に投入済みのコミット 1-6 の観測性 / 診断インフラは `ask_question` 用 PageIndex 経路にそのまま生かせるため無駄にならない

定型分析 4 種は **章テキスト取得段** のみ ADR-004 の `FilingSectionExtractor` 経由に置き換え、その後の構造化 JSON 生成 (`services/prompts.py` 経由の LLM 呼び出し) は維持する。`RagService.run_full_analysis_stream` (stream 版) と `RagService.run_full_analysis` (非 stream 版、CLI `rag analyze` から呼ばれる) の両方が対象。自由質問 (`ask_question`) は PageIndex を維持する 2 経路構成へ。実装は別ブランチ `feat/sec-section-extractor` (作成済) で着手。
