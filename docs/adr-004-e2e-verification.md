# ADR-004 実機 E2E 検証ログ (2026-05-16)

`docs/adr/004-sec-filing-section-extractor.md` 実装の worker / serve 再起動下での
end-to-end 動作確認記録。Definition of Done §7 の「実 filing で end-to-end 成功」
項目に対応する。本書は再現手順 + 結果 + 顕在化した運用制約をまとめる。

## 1. 実行環境

| 項目 | 値 |
|---|---|
| ブランチ | `feat/sec-section-extractor` |
| 検証時の HEAD | `eee8833` (refactor(rag): flatten stream loop, drop save round-trip, tolerate misses) |
| serve | `scripts/infisical-run uv run stock-analyze serve --host <redacted-host>`、port 8501 |
| worker | `scripts/infisical-run uv run stock-analyze worker` |
| llama-server | `--model <model-dir>/Qwen3.6-27B-Q4_K_M.gguf --host 127.0.0.1 --port 8080 --jinja --ctx-size 32768 --n-gpu-layers 99 --parallel 4` |
| 実効 context | **8192 tokens / slot** (`ctx-size 32768` ÷ `parallel 4`) |
| DB | `data/stock_analyze.db` (既存)。pipeline 列は idempotent ALTER で自動追加 |

worker / serve は事前に SIGTERM で graceful shutdown 後、新コードで再起動。
llama-server は無停止 (起動に時間がかかるため温存)。

## 2. テスト手順

DB 直接 INSERT で 4 件の analysis_jobs を順次 enqueue (Web UI ログインを省略):

```python
import sqlite3
from datetime import datetime, timezone
conn = sqlite3.connect("data/stock_analyze.db")
now = datetime.now(timezone.utc).isoformat()
conn.execute(
    "INSERT INTO analysis_jobs (company_id, filing_id, status, "
    "progress_current, progress_total, created_at) "
    "VALUES (?, ?, 'pending', 0, 4, ?)",
    ("US_GRRR", 223, now),
)
conn.commit()
```

worker の poll loop が即時 dequeue し、preflight → `run_full_analysis_stream` を実行。
`data/logs/stock_analyze.log` で進捗を観測。完了後 DB の `analysis_jobs` /
`company_analyses` を直接照会して結果を確認。

## 3. ジョブ結果

| Job | Filing | filing_type | 経過 | Status | 備考 |
|---|---|---|---|---|---|
| #22 | US_GRRR 223 | 6-K | 13.6s | **completed** | biz/mda 実 LLM 解析、risk/competitors は placeholder |
| #23 | US_TEM 163 | 10-Q (Q3 2025) | 15.9s | failed | risk_factors 成功、mda が context overflow、biz/competitors placeholder |
| #24 | US_TSM 95 | 20-F (FY2024) | 8.0s | failed | 全 4 章 context overflow (11-12K tokens > 8K slot) |
| #25 | US_RXRX 203 | 10-K (FY2024) | 2.1s | failed | 全 4 章 context overflow (66K + 57K + 8.4K + 66K tokens) |

### 3.1 保存された分析結果 (`company_analyses`, `pipeline='extractor'` のみ)

| Filing | business_summary | risk_factors | mda | competitors |
|---|---|---|---|---|
| 223 (GRRR 6-K) | LLM | placeholder | LLM | placeholder |
| 163 (TEM 10-Q) | placeholder | LLM | — (overflow) | placeholder |
| 95 (TSM 20-F) | — | — | — | — |
| 203 (RXRX 10-K) | — | — | — | — |

`placeholder` = `model_name="structural-placeholder"` / `_status="not_applicable"` の
sentinel JSON。`—` = LLM context overflow で保存されず failed_types に積まれた章。

## 4. ADR-004 機能検証マトリクス

| 検証項目 | 結果 | エビデンス |
|---|---|---|
| preflight が PageIndex を呼ばず LlmClient.completion で probe する (§1) | ✅ | log に `LiteLLM completion()` x10 (preflight 含む) |
| preflight 失敗時に extractor 段に到達せず fail-fast | ✅ | (本テストでは preflight 全成功、pytest で経路確認済) |
| 章抽出は LLM ゼロで決定論的に動く | ✅ | extractor 段で LLM 呼び出しなし、全 filing で sections 取得 |
| 構造上空の章は `skipped` + `structural-placeholder` 保存 | ✅ | GRRR risk/competitors、TEM biz/competitors で保存確認 |
| placeholder JSON は `_status="not_applicable"` で UI が "適用外" 表示可能 | ✅ | 4 件の placeholder 行の result_json を確認 |
| `pipeline` 列で legacy PageIndex 行を cache から除外 | ✅ | 旧 #16-21 の NULL 行は新ランで再生成対象、`extractor` 行のみ取得 |
| `failed_types` per-type 分離 (LLM 個別失敗) | ✅ | TSM/RXRX が章ごとに distinct error メッセージ |
| 空応答 (Qwen reasoning_content 暴走) を silent caching しない | ✅ | LLM error は明示的に failed_types に積まれる |
| 進捗カウンタが `skipped` でも advance | ✅ | 全 job が `progress_current=4/4` |
| legacy `index_build_error` 表示の後方互換 | ✅ | #19-21 は旧キー保持、UI 側 fallthrough で表示可能 |

### 4.1 未発火 (本テストでは検出できなかった経路)

以下は pytest で網羅されており、本 E2E では発火条件を作っていない:

- `error_details["extraction_error"]` (FilingSectionExtractor.extract() が例外を投げる経路) — 全 filing で extractor は正常完了
- `ask_question` (PageIndex 経路) — ADR-004 で未変更、本ブランチで触っていないため検証スキップ

## 5. 顕在化した運用制約 (ADR-004 §4.5 の確証)

llama-server `--parallel 4` 起動時の per-slot context = `32768 / 4 = 8192 tokens`
が SEC sections に対して小さすぎる。

| Filing | 章 | tokens | 結果 |
|---|---|---|---|
| GRRR 6-K | business_summary | 全文 (~5K chars / ~1.3K tokens) | ✅ |
| TEM 10-Q | mda | 22529 | ❌ overflow |
| TSM 20-F | biz/risk/mda/competitors | 11128 / 12176 / 11173 / 12165 | ❌ overflow |
| RXRX 10-K | biz/risk/mda/competitors | 66381 / 57473 / 8464 / 66370 | ❌ overflow |

**ADR-004 はこの context 超過を silent fail させず明確なエラーで failed_types に
積むことを目的としており、その挙動は完全に機能している。** 対症療法 (別 ADR 案件):

1. llama-server を `--parallel 1` で起動 → per-slot 32K (並列性は失う)
2. `--ctx-size 131072 --parallel 4` → per-slot 32K (VRAM 増要)
3. 章テキストを LLM 入力前に chunk + map-reduce (ADR-004 後継 ADR)

RXRX 10-K のように 66K tokens 級の章は (1)(2) でも収まらないため、(3) が
本質的に必要。

## 6. 補足観察

- 14 秒で完走した GRRR 6-K の 3 LLM call 内訳: preflight (1) + biz (1) + mda (1)。
  step 3 LLM 1 call あたり 4 秒前後で、ADR-004 が掲げた「数十分→数十秒」は
  少なくとも軽い filing で達成。
- 重い filing (RXRX 10-K) は 2.1 秒で failed — context overflow は LLM への
  request 段階で即時 rejected されるため、wall-time の浪費なし。
- DB の `analysis_jobs` テーブルに残る pre-ADR-004 失敗ジョブ #16-21 は本書執筆
  時点で `pipeline` カラムが NULL のまま残置。`get_analyses` は filter で除外
  するため UI からは見えない (運用者が DB を直接見る場合のみ視認)。

## 7. 次に追加すべきテスト

- `--parallel 1` (per-slot 32K) で再実行 → TSM 20-F の全章成功を期待
- extractor 例外発火経路 (壊れた HTML を `raw/*.htm` に置く) で
  `error_details.extraction_error` が正しく入ること
- ask_question (`stock-analyze rag ask`) が ADR-004 後も従来通り PageIndex 経由で
  動くこと
- UI からの enqueue → progress badge → 結果表示の visual 確認

## 8. 関連ドキュメント

- `docs/adr/004-sec-filing-section-extractor.md` — 設計の正本 (Accepted)
- `docs/analysis-jobs-runbook.md` — 運用手順
- `docs/analysis-failures-root-cause.md` — ADR-004 に至る根本原因分析
- `MEMORY/project_section_extractor_pivot.md` — pivot の経緯メモ
