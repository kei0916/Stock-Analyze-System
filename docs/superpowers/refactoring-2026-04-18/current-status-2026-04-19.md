# Current Status (2026-04-19)

> **Correction (2026-04-20):**
> この文書の「Phase C 本体の実装完了を前提に」という記述は、
> 2026-04-20 の再監査で誤りと判明した。
> 実コード基準の実態は Task 1 未着手 / Task 2 未着手 / Task 3 部分着手。
> 正式な補正文書は `phase-c-dry/report.md` と `master.md` を参照。

## Scope

2026-04-19 時点の refactoring / review follow-up 実装状況を記録する。  
この更新では、Phase C 本体の実装完了を前提に、current branch に反映済みの
review follow-up と RAG / PageIndex 周辺の correctness 問題の修正内容をまとめる。

---

## 実装・修正済み

### Phase C 実装

- `BaseRepository._bulk_upsert_by_natural_key` による Financial / Valuation UPSERT の共通化
- `FilingSource` / adapter / `FilingSyncService._sync()` による SEC / EDINET 同形処理の集約
- `watchlist show` の `get_with_items()` 移行と旧 service method の整理
- Phase C の public API 例外ルールを `master.md` に明記

### Review follow-up: current branch に反映済みの user-visible regression 修正

- `FilingService.list_filings()` の default limit を `None` に戻し、
  CLI / stocks detail page の全件表示挙動を回復
- `financials` / `metrics` は `PeriodType` による framework-level validation へ寄せ、
  invalid period では `422 Unprocessable Entity` を返す current 契約で統一

### RAG / PageIndex correctness follow-up

- `shared/json_utils.extract_json_object()` を追加し、
  markdown code block / prose 混在 / brace ノイズ混在から最初の decode 可能な
  JSON object を抽出できるよう改善
- `PageIndexService.query()` の tree search 結果 parsing を `extract_json_object()` ベースへ変更し、
  JSON 抽出失敗時のみ fallback するよう修正
- `PageIndexService.build_index()` に async builder 経路を追加し、
  大規模 PDF 処理時の PageIndex 側デッドロックを避ける構成へ更新
- `scripts/rag_inference_test.py` に `--use-cache` / `--skip-toc` を追加し、
  難易度別 question set・verification 出力・PDF/model ごとの cache 分離を反映

### CLI / Web follow-up

- `python -m stock_analyze_system` / setuptools script 用に `main_entry()` を追加
- `serve` command は `uvicorn.Server.serve()` を使う async 経路へ変更
- web routes は `render()` helper に寄せて重複を整理
- `rag analyze --json` では progress 文言を抑止し、JSON 出力を汚さないよう修正

---

## 追加テスト

- `tests/unit/services/test_filing_service.py`
  - `list_filings()` の default / explicit limit 委譲を固定
- `tests/unit/shared/test_json_utils.py`
  - code block / prose / brace ノイズ混在時の JSON object 抽出を固定
- `tests/unit/services/test_pageindex_service.py`
  - brace ノイズ付き tree search 応答でも不要な fallback に落ちないことを固定
- `tests/unit/test_rag_inference_test_script.py`
  - `rag_inference_test.py` の cache path が PDF/model ごとに分離されることを固定

---

## 既知ギャップ

### `run_daily_update` 並列化の仮説検証 (2026-04-19)

- 現行 `llama-server` 実行引数は
  `<llama-cpp-source>/build/bin/llama-server -m <model-dir>/Qwen3.5-27B-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -ngl 999 -c 131072 --cache-type-k q8_0 --cache-type-v q8_0`
- `/slots` では 4 slot が見える一方、`llama-server --help` より auto slot 時は unified KV が有効。実測でも「総コンテキスト予算」を共有している挙動だった
- TEM 10-K を使った実測:
  - 単発 long request (`prompt_tokens=67160`) は `32.1s` で成功
  - 同等 request の 2 並列は両方 `HTTP 500: Context size has been exceeded.` で失敗
  - 短め request (`prompt_tokens=29793`) は 2 並列・4 並列とも成功
- `/sys/class/greenboost/greenboost/pool_info` では上記負荷中も `T2 allocated = 0 MB`, `Active DMA-BUF objects = 0` のまま。`T2 available` は `6817 MB -> 4723 MB` まで低下したが、GreenBoost の「無駄な事前確保」が支配的という証拠は得られなかった
- 結論: 並列化の支配要因は GreenBoost 予約量より `llama-server` の context budget (`-c 131072`, unified KV) と request あたり prompt サイズ。`asyncio.gather + Semaphore` を再検討するなら、まず LLM サーバ構成または prompt footprint を下げる必要がある

- current branch の RAG API は `filing_type: FilingType` を受けるため、
  EDINET filing type (`annual_report`, `quarterly_report`) の互換はまだ戻していない
- そのため Phase C tracker は current branch 上では `Done` にせず `In Progress` として扱う

---

## Verification

- `uv run ruff check src/stock_analyze_system/services/filing.py src/stock_analyze_system/shared/json_utils.py scripts/rag_inference_test.py tests/unit/services/test_filing_service.py tests/unit/shared/test_json_utils.py tests/unit/services/test_pageindex_service.py tests/unit/test_rag_inference_test_script.py`
  - 結果: `All checks passed!`
- `uv run pytest tests/unit/services/test_filing_service.py tests/unit/shared/test_json_utils.py tests/unit/services/test_pageindex_service.py tests/unit/test_rag_inference_test_script.py tests/unit/cli/test_filings_cli.py tests/unit/web/test_stocks.py -q`
  - 結果: `70 passed`
- `uv run pytest`
  - 結果: `743 passed, 4 deselected, 7 warnings`

warnings は既存の `PyPDF2` deprecation と、一部 test の `AsyncMock` runtime warning が中心で、
failures は 0 件。
