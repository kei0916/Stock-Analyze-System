# Current Status (2026-04-23)

## Scope

2026-04-23 時点の branch
`codex-refactoring-followups-20260419` に載っている、直近の review
follow-up、運用ルール補正、スコープ外バグ修正を追跡する snapshot。

この snapshot は大規模リファクタリング Phase C 完了後の follow-up であり、
Phase E/B/A の本実装には着手していない。

---

## 実装・修正済み

### PageIndex fallback / metadata follow-up

- `pageindex` public API (`page_index`) と optional async helper import を分離した。
  helper が欠ける PageIndex version でも public `page_index()` fallback を維持する。
- PageIndex が未導入の場合は `None` callable ではなく `IndexBuildError` で明示的に失敗する。
- PageIndex option 生成を `_pageindex_options()` に集約し、async builder と public
  fallback の両方へ同じ config を渡すようにした。
- fallback path でも `toc_check_pages`, `max_pages_per_node`,
  `max_tokens_per_node`, `add_node_summary`, `add_node_text`, `max_tokens`,
  `api_base`, `model` を反映する。
- async builder は `len(page_list)` を `tree["page_count"]` として返す。
- persisted metadata の `page_count` は `tree["page_count"]` を優先し、存在しない場合だけ
  node page reference から推定する。

対象ファイル:

- `src/stock_analyze_system/services/pageindex_service.py`
- `tests/unit/services/test_pageindex_service.py`

### Web security headers follow-up

- security headers 付与処理を `_add_security_headers()` に集約した。
- middleware 登録順を修正し、`AuthMiddleware` が返す unauthenticated 303 redirect
  にも CSP / `X-Frame-Options` / `X-Content-Type-Options` /
  `Referrer-Policy` / `Permissions-Policy` が付くようにした。

対象ファイル:

- `src/stock_analyze_system/web/app.py`
- `tests/unit/web/test_app.py`

### External API rate limiter bugfix

- `AsyncRateLimiter.acquire()` で token 不足により `asyncio.sleep()` した後、
  `_last_check` を sleep 後の `time.monotonic()` に更新するよう修正した。
- 修正前は sleep 直後の次 caller が待機時間分を二重に補充し、連続リクエストが
  想定より早く通過する可能性があった。

対象ファイル:

- `src/stock_analyze_system/ingestion/base.py`
- `tests/unit/ingestion/test_base.py`

### Infisical command wrapper hardening

- `scripts/infisical-run` は呼び出し元環境の値に関係なく
  `STOCK_ANALYZE_LOAD_DOTENV=0` を強制する。
- repo root へ移動してから `infisical run --env=<env> --path=<path> -- <command>`
  を実行する動作を regression test で固定した。
- `infisical-local-commands.md` へ「default」ではなく「force」する運用として記録した。

対象ファイル:

- `scripts/infisical-run`
- `tests/unit/test_infisical_run_script.py`
- `docs/superpowers/refactoring-2026-04-18/infisical-local-commands.md`

### Ollama / Qwen3.6 local runtime follow-up

- `ollama` は system-wide `/usr/local/bin/ollama` の更新を試行したが、この実行環境では
  `sudo` が `no new privileges` 制約により使用できず、system-wide 更新は未完了。
- PATH は `<user-local>/bin` が `/usr/local/bin` より優先されるため、
  user-level install として `<user-local>/bin/ollama` と
  `<user-local>/lib/ollama/` を展開した。
- 実効 binary は `<user-local>/bin/ollama`、client/server ともに
  `0.21.1` であることを確認した。
- systemd service や `/usr/local/bin/ollama` を直接参照する運用では、依然として
  `0.18.2` が見える。system-wide 更新が必要な場合は、通常端末で
  `sudo sh /tmp/ollama-install.sh` 相当を実行する必要がある。
- `hf.co/unsloth/Qwen3.6-27B-GGUF:Q4_K_M` は Ollama に pull 済みで、
  `ollama show` では `architecture=qwen35`, `parameters=26.9B`,
  `context length=262144` と認識される。
- ただし Ollama `0.21.1` でも generation は
  `unknown model architecture: 'qwen35'` により失敗する。現時点の実用ルートは
  既存の `<llama-cpp-source>/build/bin/llama-server` 直接起動。
- `LlmConfig` default、`config/settings.yaml` の `llm.model` / `llm.model_quality`、
  RAG 手動検証 script、RAG timing fixture の既定モデルを
  `openai/Qwen3.6-27B-Q4_K_M.gguf` に更新した。
- 実行時の llama.cpp は `--reasoning off` を付けて起動する。Qwen3.6 は
  reasoning 有効のままだと `reasoning_content` に長く出力し、通常の
  `content` が空になりやすいため。

対象パス:

- `config/settings.yaml`
- `config/settings.yaml.example`
- `src/stock_analyze_system/config.py`
- `scripts/rag_inference_test.py`
- `tests/conftest.py`
- `tests/unit/test_config.py`
- `tests/unit/services/test_llm_client.py`
- `<user-local>/bin/ollama`
- `<user-local>/lib/ollama/`
- `<ollama-data-dir>/models/blobs/sha256-<model-blob>`

---

## Review / RED-GREEN 記録

- PageIndex fallback import 回帰:
  - RED: optional async helper 欠落時に public `page_index()` fallback が使えず失敗。
  - GREEN: public import と helper import を分離し、fallback を維持。
- PageIndex fallback config 回帰:
  - RED: fallback `page_index()` に `toc_check_page_num`,
    `max_page_num_each_node`, `max_token_num_each_node`,
    `if_add_node_summary`, `if_add_node_text` が渡らない。
  - GREEN: `_pageindex_options()` を両 path で共有。
- PageIndex persisted metadata 回帰:
  - RED: `tree["page_count"] == 42` でも persisted `page_count` が node max page `5`
    になる。
  - GREEN: explicit `tree["page_count"]` を優先。
- Security headers 回帰:
  - RED: unauthenticated `GET /` の 303 redirect に security headers が付かない。
  - GREEN: headers middleware を auth redirect より外側に配置。
- External API rate limiter:
  - RED: rate=2/sec で 3 回目が 0.5s 待機した直後、4 回目が待機なしで通過。
  - GREEN: sleep 後に `_last_check` を更新し、4 回目も次 token まで待機。
- Ollama / Qwen3.6 runtime:
  - 確認: `ollama` 実効 binary を `0.18.2` から user-level `0.21.1` へ更新。
  - 未解決: Qwen3.6 27B GGUF は Ollama `0.21.1` でも `qwen35` architecture
    未対応により generation 不可。モデル自体は llama.cpp 直接起動で load / completion 済み。
  - 設定変更: `LlmConfig` default、現在の既定 LLM model/model_quality、
    RAG 検証定数を
    `openai/Qwen3.6-27B-Q4_K_M.gguf` に切替。

---

## Verification

すべて Infisical wrapper 経由で実行した。

- `scripts/infisical-run uv run pytest tests/unit/services/test_pageindex_service.py tests/unit/web/test_app.py tests/unit/web/test_auth.py -q`
  - 結果: `72 passed, 6 warnings`
- `scripts/infisical-run uv run pytest tests/unit/ingestion/test_base.py -q`
  - 結果: `11 passed`
- `scripts/infisical-run uv run ruff check src/stock_analyze_system/ingestion/base.py tests/unit/ingestion/test_base.py`
  - 結果: `All checks passed!`
- `scripts/infisical-run uv run ruff check src/stock_analyze_system/services/pageindex_service.py src/stock_analyze_system/web/app.py tests/unit/services/test_pageindex_service.py tests/unit/web/test_app.py`
  - 結果: `All checks passed!`
- `scripts/infisical-run uv run pytest -q`
  - 結果: `792 passed, 4 deselected, 7 warnings`
- `<user-local>/bin/ollama --version`
  - 結果: `client version is 0.21.1`
- 一時起動した `ollama serve` に対する `GET /api/version`
  - 結果: `{"version":"0.21.1"}`
- `ollama show hf.co/unsloth/Qwen3.6-27B-GGUF:Q4_K_M`
  - 結果: `architecture=qwen35`, `parameters=26.9B`,
    `context length=262144`
- `POST /api/generate` with
  `hf.co/unsloth/Qwen3.6-27B-GGUF:Q4_K_M`
  - 結果: HTTP 500,
    `unknown model architecture: 'qwen35'`
- llama.cpp `llama-server` with Qwen3.6 27B Q4_K_M:
  - 起動条件: `-ngl 999 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off`
  - 結果: `65/65 layers` GPU offload, `GET /health` => `{"status":"ok"}`
  - `POST /v1/chat/completions` => `QWEN36_OK`
  - 日本語応答 => HTTP 200, 約 `44 tok/s`
- `scripts/infisical-run uv run ruff check src/stock_analyze_system/config.py scripts/rag_inference_test.py tests/conftest.py tests/unit/test_config.py tests/unit/services/test_llm_client.py`
  - 結果: `All checks passed!`
- `scripts/infisical-run uv run python -c "... LlmClient ..."`
  - 結果: `model == openai/Qwen3.6-27B-Q4_K_M.gguf`,
    `health.status == ok`, `completion == QWEN36_CONFIG_OK`
- `scripts/infisical-run uv run pytest tests/unit/test_config.py tests/unit/services/test_llm_client.py -q`
  - 結果: `37 passed`
- `scripts/infisical-run uv run pytest tests/integration/test_llamacpp_server.py -q -s`
  - 結果: `5 passed`

warnings は既存の `PyPDF2` deprecation と一部 `AsyncMock` runtime warning。
今回の変更による test failure はない。

---

## GitHub 記録

2026-04-23 の記録対象:

- repository: `kei0916/Stock-Analyze-System`
- branch: `codex-refactoring-followups-20260419`
- remote: `origin`
- 内容:
  - PageIndex fallback / metadata の review follow-up
  - security headers の unauthenticated redirect 適用
  - external API `AsyncRateLimiter` の schedule drift 修正
  - Infisical wrapper の dotenv fallback 強制無効化
  - Ollama `0.21.1` user-level 更新と Qwen3.6 27B GGUF の現行制約
  - `LlmConfig` default と既定 LLM model/model_quality の
    Qwen3.6 27B Q4_K_M への切替

この snapshot 以降の GitHub 上の source of truth は、上記 branch に push された
commit とする。

---

## 関連記録

- [current-status-2026-04-21.md](current-status-2026-04-21.md)
  - Phase C 完了、Web hardening、Infisical wrapper 導入時点の snapshot
- [infisical-local-commands.md](infisical-local-commands.md)
  - Infisical 経由の local command 標準
- [phase-c-dry/report.md](phase-c-dry/report.md)
  - Phase C 再監査と再実装の詳細
- [master.md](master.md)
  - project-wide tracker
