# Current Status (2026-04-24)

## Scope

2026-04-24 時点の branch
`codex-refactoring-followups-20260419` に載っている follow-up 実装を、
2026-04-23 snapshot 以降の差分として追跡する。

この snapshot は大規模リファクタリング本体ではなく、Phase C 完了後の
review follow-up、Qwen3.6 切替後の安定化、security hardening 補完、
PageIndex / PDF / Web RAG UX 改善を対象とする。

---

## 実装・修正済み

### Qwen3.6 切替後の LLM / RAG 安定化

- `LlmConfig` に `enable_thinking` を追加し、既定値を `false` にした。
- `LlmClient.completion()` は `thinking=True` が渡されても、config で無効なら
  backend へ thinking を要求しない。
- `PageIndexService.query()` の tree search は常に `thinking=False` で実行する。
  JSON 抽出の安定性を優先し、answer 生成だけを optional thinking 対象とした。
- `scripts/rag_inference_test.py` は `enable_thinking` を config から引き継ぐ。
- public path として許可済みだった `/health` route を実装し、Web 再起動確認や
  reverse proxy health check を 404 にしないようにした。

対象ファイル:

- `src/stock_analyze_system/config.py`
- `src/stock_analyze_system/services/llm_client.py`
- `src/stock_analyze_system/services/pageindex_service.py`
- `src/stock_analyze_system/web/app.py`
- `config/settings.yaml.example`
- `scripts/rag_inference_test.py`
- `tests/unit/test_config.py`
- `tests/unit/services/test_llm_client.py`
- `tests/unit/services/test_pageindex_service.py`
- `tests/unit/web/test_app.py`

### Security hardening review follow-up

- `InMemoryRateLimiter` は current key だけ trim する実装をやめ、
  expiry heap + bucket version による global stale bucket GC を導入した。
  これで再訪しない client key の expired bucket も回収される。
- `PdfConverter` は relative path の解決基準 (`html_path.parent`) と、
  許可ルート (`allowed_root`) を分離した。
  `data:` を維持しつつ、relative local asset は HTML 配置ディレクトリ基準、
  path traversal は allowed root で遮断する。
- `PageIndexService` の async build / summary generation timeout は
  `llm.request_timeout` を authority として統一した。
  hard-coded `120s` をやめ、PageIndex だけ別 timeout で落ちる状態を解消した。

対象ファイル:

- `src/stock_analyze_system/web/auth.py`
- `src/stock_analyze_system/services/pdf_converter.py`
- `src/stock_analyze_system/services/pageindex_service.py`
- `tests/unit/web/test_auth.py`
- `tests/unit/services/test_pdf_converter.py`
- `tests/unit/services/test_pageindex_service.py`

### Warning cleanup / PageIndex runtime compatibility

- project runtime dependency は deprecated `PyPDF2` から `pypdf` へ切り替えた。
- `src/PyPDF2/__init__.py` を追加し、legacy `import PyPDF2` を `pypdf` へ
  互換的に forward する shim を導入した。
  これにより `pageindex_service` を経由しない direct `import pageindex` でも
  clean environment で動作する。
- `tests/unit/services/test_pageindex_service.py` の `llm_client` fixture は
  sync / async API を分離した double に置き換え、unawaited `AsyncMock`
  warning を解消した。

対象ファイル:

- `pyproject.toml`
- `src/PyPDF2/__init__.py`
- `src/stock_analyze_system/services/pageindex_service.py`
- `tests/unit/services/test_pageindex_service.py`
- `tests/unit/services/test_pypdf_compat.py`

### Web RAG UX 改善

- `rag/ask` と `rag/index` の heavy rate limit は、
  RAG availability check と latest filing existence check を通過した後にだけ
  消費するよう変更した。
- これにより、RAG 無効時の 503 や filing 未登録時の 404 を何度開いても、
  最初の有効リクエストが 429 で弾かれることはなくなった。

対象ファイル:

- `src/stock_analyze_system/web/routes/api.py`
- `tests/unit/web/test_api.py`

---

## RED-GREEN 記録

- Qwen3.6 thinking 回帰:
  - RED: `thinking=True` で llama.cpp / Qwen3.6 応答が空文字になる。
  - GREEN: config-gated thinking へ変更し、tree search を non-thinking 化。
- `/health` route 不整合:
  - RED: auth public path に含まれるのに 404。
  - GREEN: route を追加し `{"status":"ok"}` を返す。
- In-memory limiter stale bucket:
  - RED: 別 key の expired bucket が later acquire / release 後も残る。
  - GREEN: expiry heap で global GC。
- PageIndex timeout authority:
  - RED: `llm.request_timeout` を 321 / 654 に変えても async build は 120 固定。
  - GREEN: build / summaries とも `llm.request_timeout` を使用。
- PDF relative asset / sandbox:
  - RED: fetcher interface が relative resolution base と allowed root を分離できない。
  - GREEN: `fetch_base_dir` と `allowed_root` を明示分離。
- PageIndex direct import compatibility:
  - RED: `import pageindex.utils` が clean env + warning-as-error で失敗。
  - GREEN: `src/PyPDF2/__init__.py` shim により direct import が通る。
- Web RAG throttling UX:
  - RED: same company で 404 / 503 を 3 回踏むと最初の有効 request が 429 になる。
  - GREEN: quota 消費を expensive path 直前へ移動。

---

## Verification

すべて Infisical wrapper 経由で実行した。

- `scripts/infisical-run uv run pytest tests/unit/services/test_llm_client.py -q`
  - 結果: `19 passed`
- `scripts/infisical-run uv run pytest tests/unit/services/test_pageindex_service.py -q`
  - 結果: `35 passed`
- `scripts/infisical-run uv run pytest tests/unit/web/test_auth.py -q`
  - 結果: `27 passed`
- `scripts/infisical-run uv run pytest tests/unit/services/test_pdf_converter.py -q`
  - 結果: `13 passed`
- `scripts/infisical-run uv run pytest tests/unit/web/test_api.py -q`
  - 結果: `17 passed`
- `scripts/infisical-run uv run pytest tests/unit/services/test_pypdf_compat.py -q`
  - 結果: `1 passed`
- `scripts/infisical-run uv run ruff check src/stock_analyze_system/web/routes/api.py src/PyPDF2/__init__.py tests/unit/web/test_api.py tests/unit/services/test_pypdf_compat.py`
  - 結果: `All checks passed!`
- `scripts/infisical-run uv run pytest tests/unit/web/test_api.py tests/unit/services/test_pageindex_service.py tests/unit/services/test_pypdf_compat.py -q -W error::DeprecationWarning -W error::RuntimeWarning`
  - 結果: `54 passed`
- `scripts/infisical-run uv run pytest -q`
  - 結果: `805 passed, 4 deselected`
- `scripts/infisical-run uv run pytest -q -W error::DeprecationWarning -W error::RuntimeWarning`
  - 結果: `805 passed, 4 deselected`

warnings-as-errors で full suite が通ることを確認済み。

---

## 未対応 review / follow-up

2026-04-24 時点で、以下は未着手:

- `scripts/rag_inference_test.py` の cache key は `pdf_path|model` ベースのままで、
  PDF contents や PageIndex build options を十分に反映していない。
- Web RAG tab (`src/stock_analyze_system/web/static/app.js`) は request payload に
  filing type を明示せず、EDINET filing (`annual_report` / `quarterly_report`) の
  company では `10-K` fallback による 404 が残りうる。

今回の snapshot には含めず、次の follow-up 対象とする。

---

## GitHub 記録

2026-04-24 の記録対象:

- repository: `kei0916/Stock-Analyze-System`
- branch: `codex-refactoring-followups-20260419`
- remote: `origin`
- 内容:
  - Qwen3.6 切替後の LLM / RAG 安定化
  - stale bucket / PDF fetcher / PageIndex timeout の review follow-up
  - `pypdf` 移行と direct PageIndex import compatibility
  - Web RAG throttling の UX 改善

この snapshot 以降の GitHub 上の source of truth は、上記 branch に push された
commit とする。
