# Step 3 `reasoning_content` runaway リスク 実機検証ログ (2026-05-16)

`docs/adr/004-sec-filing-section-extractor.md` §4.5 で「別 ADR で扱う」と
保留した **step 3 (`_analyze_section`) における Qwen3.6 の `reasoning_content`
暴走リスク**について、実際の llama-server 上で再現するか確認した記録。

> **結論先出し**: 現状の deployed 構成では runaway は再現しなかった。
> ただし **手前で別の重大問題 (per-slot context overflow)** が顕在化し、
> production の step 3 は実 10-K に対してそもそも LLM 応答段に到達できない。

## 1. 実行環境

| 項目 | 値 |
|---|---|
| ブランチ / HEAD | `feat/sec-section-extractor` @ `eee8833` |
| 検証スクリプト | `scripts/verify_step3_reasoning_runaway.py` |
| LLM サーバ | `llama-server --model Qwen3.6-27B-Q4_K_M.gguf --jinja --ctx-size 32768 --n-gpu-layers 99 --parallel 4` (`localhost:8080`) |
| **実効 ctx** | **8192 tokens / slot** (`--ctx-size 32768` ÷ `--parallel 4`) |
| litellm 呼び出し条件 | `_analyze_section` (= `LlmClient.completion(..., quality=True)`) と完全同一: `max_tokens=16384`, `temperature=0.1`, `timeout=600`, `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`, `response_format` なし |
| 対象 filing | `data/filings/SEC/US_RXRX/2025/annual/10-K/0001601830-26-000039` (ADR §Situation で PageIndex が落ちた filing の 1 つ) |
| 章抽出結果 (chars) | `business_summary=239,543` / `risk_factors=327,714` / `mda=37,272` / `competitors=239,543` |

スクリプトは production と同じ `FilingSectionExtractor.extract()` でセクション
テキストを取得した上で、`_analyze_section` の build する prompt 文字列を
完全再現し `litellm.acompletion(...)` を直接叩く。

## 2. 観測

### Phase A: production 条件 (truncate なし)

| analysis_type | section chars | prompt tokens | finish_reason | 結果 |
|---|---:|---:|---|---|
| `mda` | 37,272 | 9,136 | — | `litellm.BadRequestError` (ctx 8192 超過) |
| `competitors` | 239,543 | 48,465 | — | 同上 (5.9×) |
| `business_summary` | 239,543 | 48,476 | — | 同上 (5.9×) |
| `risk_factors` | 327,714 | 58,562 | — | 同上 (7.1×) |

**4/4 件が `BadRequestError`**。 `_is_empty_llm_response` の safety net は到達
しない。worker は `LlmClient.completion` の raise を受けて `analysis_error` を
記録するため、UI / DB から見るとリスク発現と切り分けが難しい。

### Phase B: ctx 内に収まる truncate

prompt が 8K slot に収まる範囲で、`enable_thinking=False` が honor され
runaway しないかを検証。

| analysis_type | section chars | prompt tokens | finish_reason | content chars | reasoning chars |
|---|---:|---:|---|---:|---:|
| `mda` | 17,000 | 4,497 | `stop` | 1,565 | **0** |
| `risk_factors` | 17,000 | 3,363 | `stop` | 1,896 | **0** |
| `risk_factors` | 27,000 (境界付近) | 5,144 | `stop` | 1,708 | **0** |

3/3 件で `reasoning_content` が空、`content` が prompts.py 仕様通りの JSON。
`finish_reason=stop` は budget 内に正常終了。境界付近 (slot ctx の 63%) でも
挙動が変わらない。

## 3. 含意

1. **ADR §4.5 の前提が今回の条件では成立しなかった**。
   `extra_body.chat_template_kwargs.enable_thinking=False` を経路に渡せば、
   Qwen3.6-27B-Q4_K_M (`--jinja` 経由) は step 3 形状の prompt に対して
   reasoning_content を完全に抑制する。
   PageIndex の step 1/2 で観測された runaway は **JSON-mode (`response_format`)
   や別の chat_template_kwargs との相互作用** が原因の可能性が高い (step 3 は
   `response_format` を渡さない / Jinja template が `enable_thinking` を直接読む)。
2. **真のブロッカーは per-slot ctx 不足**。実 10-K の章テキストが 9K〜60K
   tokens に達し、8K slot を全件で超える。`_analyze_section` の `BadRequestError`
   は ctx overflow であり、`_is_empty_llm_response` の guard とは別レイヤで
   起きる失敗である。
3. `_analyze_section` の空応答ガード (commit `f4094ad`) は引き続き正しい
   defense-in-depth として残すが、**現状 production の主要 failure mode は
   捕捉対象外**。

## 4. 推奨フォローアップ (未着手)

- llama-server を `--ctx-size 65536 --parallel 1` 等に再構成し、Phase A の
  4 件が成功するか再検証する (運用負荷との trade-off: 同時走行が落ちる)。
- それでも収まらない章 (RXRX `risk_factors` で ~58K tokens) は、入力 chunking
  あるいは extractor 段で intra-Item subsection 分割 (10-K Item 1A の risk
  項目単位など) を検討。別 ADR の対象とする。
- ADR-004 §4.5 を更新: 「未確認」→「実機検証済み (本ログ参照)、reasoning_content
  runaway は再現せず。代わりに ctx overflow が主要失敗モード」と書き換える。

## 5. 再現手順

```bash
# llama-server が localhost:8080 で稼働している前提
OPENAI_API_KEY=dummy .venv/bin/python scripts/verify_step3_reasoning_runaway.py \
  2>&1 | tee /tmp/step3_runaway.log
# 結果は data/step3_runaway_verification.json に保存される
```

スクリプトは Phase A (4 セクション × full text) と Phase B (mda 17K /
risk_factors 17K / risk_factors 27K) を順に実行する。LLM サーバの ctx 設定
を変更したら、Phase A の BadRequestError が消えるかをまず確認すること。

## 6. 検証データ

raw レスポンスは `data/step3_runaway_verification.json` に永続化済み
(`results[*]` に prompt tokens / completion tokens / finish_reason /
content_head / reasoning_head を含む)。

---

# 再検証ラウンド: `--ctx-size 131072 --parallel 1` (2026-05-17)

§4 の推奨フォローアップに従い llama-server を再構成して再実行。

## R.1 サーバ構成変更

```
旧: --ctx-size 32768 --n-gpu-layers 99 --parallel 4   (slot ctx = 8192)
新: --ctx-size 131072 --n-gpu-layers 99 --parallel 1   (slot ctx = 131072)
```

| 項目 | 値 |
|---|---|
| nvidia-smi 起動後 | RTX 4090 24,564 MiB 中 **24,036 MiB 使用 / 37 MiB free** |
| /v1/props `n_ctx` | 131072 |
| 並列度 | 1 (worker 単独稼働前提) |
| llama-server PID | 183629 |
| ログ | `<log-dir>/llama-server.log` |

GPU メモリは紙一重 (37 MiB の残量) で確保できた。**ほぼ全量を KV cache
が占有**するため、同 GPU で他プロセス (uv run worker の埋め込みなど) を
動かす余裕は無いことに注意。

## R.2 観測結果

検証スクリプトは前回と同一 (`scripts/verify_step3_reasoning_runaway.py`)。

### Phase A — 本番条件 (truncate なし)

| analysis_type | section chars | prompt tokens | completion | finish | content chars | **reasoning chars** | elapsed |
|---|---:|---:|---:|---|---:|---:|---:|
| `mda` | 37,272 | 9,136 | 895 | `stop` | 1,643 | **0** | 23.0s |
| `competitors` | 239,543 | 48,465 | 1,066 | `stop` | 2,295 | **0** | 46.8s |
| `business_summary` | 239,543 | 48,476 | 653 | `stop` | 1,286 | **0** | 37.1s |
| `risk_factors` | 327,714 | 58,562 | 1,087 | `stop` | 2,327 | **0** | 53.9s |

→ **Phase A 全件成功**。旧構成で全件 `BadRequestError` だった失敗モードは
解消。最長 `risk_factors` (58,562 prompt tokens) でも 54 秒以内に完了し、
`reasoning_content` は終始 0 chars。

### Phase B — truncate 17K chars (control 比較)

| analysis_type | prompt tokens | completion | finish | content chars | reasoning chars | elapsed |
|---|---:|---:|---|---:|---:|---:|
| `mda` (17K) | 4,497 | 785 | `stop` | 1,437 | 0 | 19.7s |
| `risk_factors` (17K) | 3,363 | 813 | `stop` | 1,702 | 0 | 18.8s |

旧構成の Phase B 結果 (round 1) とほぼ同等。runaway の兆候なし。

## R.3 結論 (更新)

1. **ADR §4.5 のリスクは旧 / 新両構成で再現せず**。Qwen3.6-27B-Q4_K_M は
   `extra_body.chat_template_kwargs.enable_thinking=False` を確実に honor し、
   最大 58K prompt token 投入時も `reasoning_content` を出さない。
2. **旧構成の primary failure mode (ctx overflow) は新構成で解消**。
   実 10-K の最大 risk_factors (327K chars / 58K tokens) でも余裕。
3. **トレードオフ**:
   - GPU 24 GiB を実質ほぼ占有 (KV cache 全載せ)。他プロセスからの GPU
     使用は不可。
   - `--parallel 1` のため `analysis_jobs` の同時走行はできない。既に
     `MEMORY/project_sync_concurrency.md` で worker は直列化済みなので
     現状ワークロードでは問題なし。
   - 1 リクエスト 20〜55 秒 (prompt eval が支配的)。worker 全 4 analysis_type
     完了に 3〜4 分。
4. **保留中の `_is_empty_llm_response` 防御は引き続き残す**。本検証では
   発火しなかったが、Qwen3.6 ビルド差異 / 他 filing / chat template 更新時
   の保険として有用。

## R.4 推奨される次のアクション (未着手 / 指示待ち)

- ADR-004 §4.5 を「実機検証済み、reasoning_content runaway は再現せず。
  代わりに ctx 不足が主要 failure。新運用 `--ctx-size 131072 --parallel 1`
  で解消」と書き換える。
- 旧 `--ctx-size 32768 --parallel 4` 構成へ戻すかどうかの判断:
  - 戻す: GPU を他用途に解放できる / `analysis_jobs` を直列化前提の運用
    継続なら parallel=4 の意味はない
  - 維持: 本検証成果を活かす / 唯一の常駐 LLM 用途であれば 131k 維持が安全
- worker / serve をこの構成で実 filing 1 件回し、UI 経路でも end-to-end で
  reasoning_content 暴走 / 空応答が発生しないか確認 (本ログは直叩き probe
  のみで `_analyze_section` を介していない)。

## R.5 検証データ

- `data/step3_runaway_verification.json` — 直近 (round 2) の結果
- `data/step3_runaway_verification_round2_ctx131k.json` — round 2 固定スナップショット
- `/tmp/step3_runaway_round2.log` — round 2 標準出力ログ
- `<log-dir>/llama-server.log` — 新サーバの起動ログ (slot 構成、cache, chat template)

## R.6 worker / UI 経路 E2E (2026-05-17 02:48-02:50 JST)

直叩き probe (R.2) ではなく `_analyze_section` を介した経路で確認するため、
analysis_jobs を 1 件 enqueue して serve / worker / llama-server 経由で 1 ジョブ完走。

### 手順

```python
import sqlite3
from datetime import datetime, timezone
conn = sqlite3.connect("data/stock_analyze.db")
now = datetime.now(timezone.utc).isoformat()
conn.execute(
    "INSERT INTO analysis_jobs (company_id, filing_id, status, "
    "progress_current, progress_total, created_at) "
    "VALUES (?, ?, 'pending', 0, 4, ?)",
    ("US_RXRX", 199, now),
); conn.commit()
# → job id = 26
```

### 結果

| 項目 | 値 |
|---|---|
| Job | #26 (RXRX 2025 10-K / filing 199) |
| Status | **completed** |
| 進捗 | 4 / 4 |
| 所要時間 | 2 min 14 sec (17:48:28 → 17:50:43 UTC) |
| `error_details` | None |
| `company_analyses` | 4 件すべて `pipeline='extractor'` として保存 (PageIndex 時代 `NULL` 行とは別 row) |

### result_json キー (UI API `/api/stocks/US_RXRX/rag/analyses?filing_id=199` 経由)

| analysis_type | 返却キー | prompts.py 仕様一致 |
|---|---|---|
| `business_summary` | company_name, industry, business_segments, key_products, geographic_presence, employees, summary | ✓ |
| `risk_factors` | risks, top_risks_summary | ✓ |
| `mda` | revenue_analysis, profitability, cash_flow, capital_allocation, outlook, key_metrics, summary | ✓ |
| `competitors` | competitive_position, market_share, competitors, competitive_advantages, competitive_risks, summary | ✓ |

`raw_answer` fallback (JSON parse 失敗時の sentinel) は 1 件も発生せず。
内容も Recursion Pharmaceuticals の事業実態と整合 (REC-617 / Recursion OS /
Roche-Sanofi-Bayer-Merck KGaA partnerships / 21 億ドル累積赤字 / FY2025 売上
74.68M USD など実 10-K 由来の固有名詞が正確に拾えている)。

### 観測された UX ノート (バグではないが共有)

`company_analyses.created_at` は同じ `pipeline='extractor'` 自然キーへの再 upsert では
旧値が保持される。PageIndex 時代の `pipeline IS NULL` 行とは別 row になるため、
legacy 行の `created_at` が extractor 結果の分析日時として見えることはない。UI 上で
再分析日時を厳密に管理したい場合は別途 `updated_at` 列を追加するか、upsert で
created_at もリフレッシュする必要がある (本 ADR スコープ外)。

### 結論

新 llama-server 構成 (`--ctx-size 131072 --parallel 1`) + ADR-004 実装で、
**direct probe → `_analyze_section` 経由 → UI API まで一貫して全 4 章を実 LLM
で生成 → 期待 JSON 構造で serve できることを確認**。reasoning_content 暴走 /
空応答は本 E2E でも発生せず。
