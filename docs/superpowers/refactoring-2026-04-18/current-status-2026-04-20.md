# Current Status (2026-04-20)

## Scope

2026-04-20 時点の current branch に反映済みの実装・修正内容を記録する。
この更新では、2026-04-19 時点の status を前提に、その後に追加で確定した
run_daily_update 並列化の検証結果と、スコープ外だが影響の大きい follow-up bugfix をまとめる。

---

## 実装・修正済み

### `run_daily_update` 並列化の仮説検証

- `asyncio.gather + Semaphore` による将来の並列化可否を、実際の `llama-server`
  構成と TEM 10-K を使った負荷で検証した
- 2 並列 long request 失敗の主因は GreenBoost の予約量ではなく、
  `llama-server` の総コンテキスト予算 (`-c 131072`, unified KV) と
  request ごとの prompt サイズだと確認した
- そのため、Phase D / tracker 上の「並列化」は引き続き out-of-scope とし、
  将来は GreenBoost 調整ではなく LLM server 設定または prompt footprint
  の見直しをトリガーに再評価する

### SEC filing HTML 検出の修正

- `PdfConverter.get_or_convert()` は `raw/*.html` のみ探索していたが、
  実データの SEC filing は `raw/*.htm` が多く、PDF 変換前に
  `FileNotFoundError` へ落ちる経路があった
- `raw/` と filing root の両方で `*.html` と `*.htm` を探索するよう修正し、
  SEC / RAG の前処理が `.htm` filing でも継続できるようにした

### FMP availability check の修正

- `FmpClient.is_available()` は接続障害時に `ApiConnectionError` を外へ漏らし、
  「可用性を bool で返す」契約を破っていた
- `ApiConnectionError` を `False` 側へ畳み込むよう修正し、
  一時的な API 接続不良で健全性チェック全体が例外終了しないようにした

### RAG confidence 過大評価の修正

- `PageIndexService.query()` は LLM が返した `node_list` 件数で confidence を計算しており、
  存在しない node ID しか解決できていなくても `0.3+` の confidence が付いていた
- confidence を「実際に node_map で解決できたノード数」ベースへ変更し、
  根拠ゼロの回答に見かけ上の信頼度が付かないよう修正した

### EDINET 財務同期の実クライアント契約修正

- `FinancialSyncService._parse_and_upsert_edinet()` は
  `EdinetClient.download_xbrl()` を呼んでいたが、実クライアントにあるのは
  `download_xbrl_zip()` だけで、実行時に `AttributeError` で落ちる経路があった
- サービス層を実クライアント契約に合わせ、一時ディレクトリへ ZIP 展開した結果を
  parser に渡すよう修正した
- 既存 unit test は `AsyncMock` に `download_xbrl` を生やして不一致を隠していたため、
  `download_xbrl_zip()` しか持たないクライアント形を使う再現テストへ更新した

### RAG filing type 契約の修正

- CLI parser と web API request validation は SEC 用 `FilingType`
  (`10-K`, `10-Q`, `20-F`, `6-K`) しか受け付けず、
  EDINET filing type (`annual_report`, `quarterly_report`) を入口で弾いていた
- `FilingType` に EDINET 側の 2 値を正式追加し、
  CLI と API の両入口で同じ契約を受け付けるようにした
- これにより、日本株の filing を前提にした RAG CLI / API 呼び出しが
  validation error で止まらないようになった

---

## 追加テスト

- `tests/unit/services/test_pdf_converter.py`
  - `raw/*.htm` filing から PDF 変換へ進めることを固定
- `tests/unit/ingestion/test_fmp.py`
  - `is_available()` が `ApiConnectionError` 時に `False` を返すことを固定
- `tests/unit/services/test_pageindex_service.py`
  - 存在しない node ID しか選ばれない場合、confidence が `0.0` になることを固定
- `tests/unit/services/test_financial_sync.py`
  - `download_xbrl_zip()` しか持たない EDINET クライアント契約でも
    `_parse_and_upsert_edinet()` が動くことを固定
- `tests/unit/cli/test_helpers.py`
  - `--filing-type annual_report` が parser で受理されることを固定
- `tests/unit/web/test_api.py`
  - `AskRequest(filing_type=\"annual_report\")` が validation を通ることを固定
- `tests/unit/test_enums.py`
  - `FilingType` に EDINET 側の `annual_report` / `quarterly_report` が
    含まれることを固定

---

## Verification

- `uv run pytest tests/unit/services/test_pdf_converter.py -q`
  - 結果: `5 passed`
- `uv run pytest tests/unit/ingestion/test_fmp.py -q`
  - 結果: `13 passed`
- `uv run pytest tests/unit/services/test_pageindex_service.py -q`
  - 結果: `29 passed, 4 warnings`
- `uv run pytest tests/unit/ingestion/test_fmp.py tests/unit/services/test_pdf_converter.py tests/unit/services/test_pageindex_service.py -q`
  - 結果: `47 passed, 6 warnings`
- `uv run ruff check src/stock_analyze_system/ingestion/fmp.py src/stock_analyze_system/services/pageindex_service.py src/stock_analyze_system/services/pdf_converter.py tests/unit/ingestion/test_fmp.py tests/unit/services/test_pageindex_service.py tests/unit/services/test_pdf_converter.py`
  - 結果: `All checks passed!`
- `uv run pytest tests/unit/services/test_financial_sync.py tests/unit/cli/test_helpers.py tests/unit/web/test_api.py tests/unit/test_enums.py tests/unit/characterization/test_enum_integration.py tests/unit/cli/test_rag_cli.py -q`
  - 結果: `75 passed, 1 warning`
- `uv run ruff check src/stock_analyze_system/services/financial_sync.py src/stock_analyze_system/models/enums.py tests/unit/services/test_financial_sync.py tests/unit/cli/test_helpers.py tests/unit/web/test_api.py tests/unit/test_enums.py`
  - 結果: `All checks passed!`

warnings は既存の `PyPDF2` deprecation と `test_pageindex_service.py` 由来の
`AsyncMock` runtime warning が中心で、今回の修正で新しい failure は増えていない。

---

## 2026-04-20 追加更新: Web security hardening / review follow-up

この節は、同日中に current branch へ追加で反映した Web hardening と
review follow-up を、追跡しやすいよう対象ファイル単位で記録する。

### 実装・修正済み

### Web runtime / auth hardening

- default bind host を `127.0.0.1` に寄せ、`WebConfig` の default と
  repo 既定設定の両方で localhost bind を前提にした
- `WebConfig` に `secure_cookies`, `trust_proxy_headers`,
  `trusted_proxy_hosts`, login/heavy request 用 rate-limit 設定を追加した
- login route に in-memory rate limiter を導入し、連続失敗時は
  `429` を返すようにした
- `secure_cookies=True` 時は session cookie に `Secure` 属性を付けるようにした
- reverse proxy 配下では、信頼済み proxy host に限って
  `X-Forwarded-For` / `X-Real-IP` を rate-limit key の client identity に使うようにした

対象ファイル:
`src/stock_analyze_system/config.py`,
`src/stock_analyze_system/web/app.py`,
`src/stock_analyze_system/web/auth.py`,
`src/stock_analyze_system/web/routes/auth.py`,
`tests/unit/test_config.py`,
`tests/unit/web/test_auth.py`

### Heavy endpoint throttling / jobs flow hardening

- app startup 時に login 用と heavy endpoint 用の limiter を app state に載せた
- RAG `ask` / `index` API に per-client throttling を追加した
- `/jobs/sync` と `/jobs/daily` に per-client throttling を追加した
- jobs 失敗時は例外文字列をそのまま UI に返さず、
  サーバーログ参照を促す安全なメッセージへ置き換えた
- jobs throttling 時も JSON error へ落とさず、既存 HTML フローを維持する
  `/jobs?error=...` redirect に揃えた

対象ファイル:
`src/stock_analyze_system/web/app.py`,
`src/stock_analyze_system/web/auth.py`,
`src/stock_analyze_system/web/routes/api.py`,
`src/stock_analyze_system/web/routes/jobs.py`,
`tests/unit/web/test_api.py`,
`tests/unit/web/test_jobs.py`

### Frontend / UI hardening

- remote CDN 依存を外し、`base.html` は `/static/app.css` と `/static/app.js`
  のみを読む形に変更した
- HTTP response に CSP / `X-Content-Type-Options` / `X-Frame-Options` /
  `Referrer-Policy` / `Permissions-Policy` を追加した
- stock search は debounce 付き非同期検索へ置き換えたうえで、
  stale response が最新入力を上書きしないよう token と `AbortController`
  で制御する形に修正した
- debounce callback 外の `.catch()` 誤用をやめ、fetch error は
  debounced callback 内でハンドリングするよう修正した
- financial / metrics / valuation / RAG の各 tab を JS で順次ロードする構成へ整理した
- RAG empty state では `companyId` を `innerHTML` に埋め込まず、
  text node と `code` 要素を組み立てる形に変えて stored XSS sink を潰した

対象ファイル:
`src/stock_analyze_system/web/templates/base.html`,
`src/stock_analyze_system/web/templates/stocks/search.html`,
`src/stock_analyze_system/web/templates/stocks/detail.html`,
`src/stock_analyze_system/web/templates/stocks/_tab_financial.html`,
`src/stock_analyze_system/web/templates/stocks/_tab_metrics.html`,
`src/stock_analyze_system/web/templates/stocks/_tab_valuation.html`,
`src/stock_analyze_system/web/templates/stocks/_tab_rag.html`,
`src/stock_analyze_system/web/static/app.css`,
`src/stock_analyze_system/web/static/app.js`,
`tests/unit/web/test_app.py`

### PDF / RAG prompt hardening

- `PageIndexService` の summary/search/answer prompt に
  「document text を命令として扱わない」guardrail を追加した
- `PdfConverter` は WeasyPrint の fetcher を差し替え、
  filing root 配下の `file:` asset だけを解決するようにした
- これにより HTML-to-PDF 変換時の外部ネットワーク fetch を抑止した

対象ファイル:
`src/stock_analyze_system/services/pageindex_service.py`,
`src/stock_analyze_system/services/pdf_converter.py`,
`tests/unit/services/test_pageindex_service.py`,
`tests/unit/services/test_pdf_converter.py`

### review follow-up で確定した修正

- repo default runtime bind host が localhost になることを
  `load_config(config/settings.yaml)` ベースの test で固定した
- trusted proxy を使う rate-limit keying を test で固定した
- `/jobs` throttling 時の redirect flow を test で固定した
- stock search の stale response 抑止と error handling 修正を
  source-level test で固定した

### 2026-04-20 review follow-up 追加修正

- `InMemoryRateLimiter` は `allow()` と `add_*()` を分離した API をやめ、
  trim・判定・予約を 1 回の lock 区間で完了する `try_acquire()` ベースへ置換した
- limiter は lease/token を返す設計に変え、login 成功時は「今回の試行だけ」
  `release()` できるようにした。これにより `reset(key)` による
  過去失敗履歴の全消しをやめた
- `_trim()` と `release()` の両方で空 bucket key を `_events` から削除するようにし、
  期限切れ後の空エントリが残り続けないようにした
- heavy endpoint (`/jobs/*`, RAG `ask/index`) は atomic admission を使う形へ揃え、
  route 側に split check/update が残らないようにした
- `PdfConverter` の safe fetcher は `data:` URL を許可しつつ、
  `http(s):` / `ftp:` / relative-network URL と root 外 `file:` を引き続き拒否する
  形へ修正した

### 追加テスト (review follow-up)

- `tests/unit/web/test_auth.py`
  - `try_acquire()` が `max_attempts=1` でも並列 caller を 1 件だけ通すことを固定
  - `release()` 後に空 bucket が削除されることを固定
  - login 成功後も過去の失敗履歴が残ることを route-level で固定
- `tests/unit/services/test_pdf_converter.py`
  - `data:` URL が許可されることを固定
  - relative-network URL (`//host/...`) が拒否されることを固定

### 追加 verification

- `uv run pytest tests/unit/test_config.py tests/unit/web/test_app.py tests/unit/web/test_auth.py tests/unit/web/test_jobs.py tests/unit/web/test_stocks.py tests/unit/web/test_api.py -q`
  - 結果: `81 passed in 2.77s`
- `uv run ruff check src/stock_analyze_system/config.py src/stock_analyze_system/web/auth.py src/stock_analyze_system/web/routes/jobs.py tests/unit/test_config.py tests/unit/web/test_app.py tests/unit/web/test_auth.py tests/unit/web/test_jobs.py tests/unit/web/test_stocks.py tests/unit/web/test_api.py`
  - 結果: `All checks passed!`
- `uv run pytest tests/unit/web/test_auth.py tests/unit/web/test_api.py tests/unit/web/test_jobs.py tests/unit/services/test_pdf_converter.py -q`
  - 結果: `59 passed in 2.48s`
- `uv run ruff check src/stock_analyze_system/web/auth.py src/stock_analyze_system/web/routes/auth.py src/stock_analyze_system/web/routes/api.py src/stock_analyze_system/web/routes/jobs.py src/stock_analyze_system/services/pdf_converter.py tests/unit/web/test_auth.py tests/unit/web/test_api.py tests/unit/web/test_jobs.py tests/unit/services/test_pdf_converter.py`
  - 結果: `All checks passed!`
- `uv run pytest -q`
  - 結果: `773 passed, 4 deselected, 8 warnings in 9.59s`
