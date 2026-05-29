# 定型分析ジョブ運用ランブック

`stock-analyze worker` を運用し、定型分析失敗を最短で原因特定するための手順。

**重要**: ADR-004 (`docs/adr/004-sec-filing-section-extractor.md`) 適用後、定型分析 4 種 (`business_summary` / `risk_factors` / `mda` / `competitors`) は **`FilingSectionExtractor` (LLM 非依存の固定セクション抽出)** + 各 analysis_type 1 回の LLM 呼び出し (step 3) で動く。**PageIndex 経路は `ask_question` (自由質問) のみで使われる**。

| 経路 | 章抽出 | step 3 LLM | 失敗時の error_details key |
|---|---|---|---|
| 定型分析 4 種 | `FilingSectionExtractor` (deterministic, LLM ゼロ) | あり (4 回/build) | preflight / extractor 失敗 → `extraction_error`; 特定 type の step-3 LLM 失敗 → `failed_types`; legacy `index_build_error` は emit しない (§2.1 表参照) |
| `ask_question` (自由質問) | PageIndex (LLM 多数回) | PageIndex.query 内で完結 | フル稼働 (思考トークン暴走時の診断はここで活きる) |

本文書は `docs/analysis-failures-root-cause.md` の修正コミット 1-6 で導入した観測性基盤を前提とする。**ADR-004 適用後は本ランブックの §3.2 (`<think>` 暴走系) は ask_question 経路のトラブルでのみ参照する。**

## 1. ワーカーと LLM サーバの起動

```bash
# 端末1: Web サーバ
scripts/infisical-run uv run stock-analyze serve

# 端末2: 分析ワーカー (5/15 まで stdout が失われていたが、
# fe0b153 以降は data/logs/stock_analyze.log へ FileHandler 出力される)
scripts/infisical-run uv run stock-analyze worker

# 端末3: LLM バックエンド (llama-server)
# 重要: enable_thinking=false を chat template に効かせるため --jinja が必須.
# Qwen3.6 / Qwen3.5 の chat template は jinja 評価器なしでは
# `enable_thinking` パラメータを無視するため、思考トークン暴走の温床になる.
~/llama.cpp/build/bin/llama-server \
  --model ~/models/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  --jinja \
  --ctx-size 131072 \
  --n-gpu-layers 99 \
  --parallel 1 \
  --reasoning off \
  > data/logs/llama-server.log 2>&1
```

`--parallel N` は `--ctx-size` を slot 数で分割するため、ADR-004 step 3 の `risk_factors` (RXRX で ~58K prompt tokens) を 1 slot に収めるには `--parallel 1` (= slot ctx 131072) が必須。より小さい ctx-size や多い parallel slot に下げると実 10-K セクションが context overflow するため、ADR-004 検証済み構成 (`docs/adr/004-sec-filing-section-extractor.md` Known limitations 参照) から外れる設定にしないこと。

`--jinja` を付けない場合、`extra_body.chat_template_kwargs.enable_thinking=false` を送っても効かず、Qwen3 系は `<think>...` を出力する。これが PageIndex 経路で TOC 抽出が空応答になる既知経路。**ADR-004 適用後の定型分析では section 抽出に LLM を呼ばないためこの経路は発火しないが、`ask_question` 経路では引き続き発火するため `--jinja` は必須**。

## 2. ジョブが失敗したときの調査手順

### 2.1 DB の `error_details` を見る

```bash
uv run python - <<'PY'
import sqlite3
c = sqlite3.connect('data/stock_analyze.db').cursor()
for r in c.execute("""SELECT id, company_id, status, error_details
                      FROM analysis_jobs ORDER BY id DESC LIMIT 5"""):
    print(r)
PY
```

`error_details` の形で原因層が判別できる (ADR-004 以後):

| 形 | 意味 | 次の手 |
|---|---|---|
| `{"extraction_error": {"message": "preflight failed (error): ...", "diagnostic": null}}` | step-3 LLM probe が失敗 (`rag.preflight()` が exception を捕捉)。`diagnostic` は現行 ADR-004 では常に `null` (§2.2 参照) | llama-server 状態確認、§3.1。詳細は `message` 末尾の exception 文字列と `data/logs/stock_analyze.log` の `RagService preflight failed` warning |
| `{"extraction_error": {"message": "preflight failed (error): LLM returned empty content (possible reasoning_content runaway — see ADR-004 §4.5)", "diagnostic": null}}` | step-3 LLM probe が空文字列で返った (worker は `status` を `error` として包む。`reason` 文字列で空応答ケースを判別) | chat template / `--jinja` 確認、§3.2 |
| `{"extraction_error": {"message": "..."}}` (diagnostic 無し or `null`) | `FilingSectionExtractor` が parse 例外を投げた (HTML 破損 / 解凍失敗 等) | `data/logs/stock_analyze.log` の `section extraction failed for filing N` を grep、`<storage_path>/raw/` を確認 |
| `{"failed_types": [{"type": "mda", "message": "..."}]}` | extractor は成功、特定タイプの step-3 LLM 呼び出し失敗 | §3.3 |
| `{"failed_types": [{"type": "mda", "message": "ファイリングから章テキストを抽出できませんでした"}]}` | 構造上は存在するはずの章を extractor が取りこぼした (例: 10-K の `mda`、20-F の `business_summary`)。**`is_structurally_empty` で除外される 10-Q `business_summary`/`competitors`、6-K `risk_factors`/`competitors` などはここに出ない** (§3.4 参照) | §3.4 抽出器デバッグ |
| `{"index_build_error": {...}}` | **legacy (ADR-004 以前)** PageIndex 経路で失敗したジョブ。現在の worker は emit しない | 再 enqueue すれば新形式 (`extraction_error` または `failed_types`) で再記録される |
| `{"reason": "..."}` (旧 unexpected) | worker の `except Exception` 経路。スタックトレースは `data/logs/stock_analyze.log` を確認 | log を grep |

**構造上の章不存在は `error_details` に出ない (正常仕様)**: 10-Q `business_summary`/`competitors`、6-K `risk_factors`/`competitors` 等、filing 種別の構造上空の章は `RagService._process_one` (`rag_service.py`) で `is_structurally_empty()` を通り、`_status="not_applicable"` の placeholder として `analyses` テーブルに保存される (`_save_placeholder` → `_PLACEHOLDER_MODEL`)。stream は `{"event": "skipped", "reason": "structurally_absent"}` を emit し、worker はこれを成功進捗としてカウントするため、ジョブは `COMPLETED` で終わり `error_details` は `null`。UI 側ではキャッシュヒットとして `_status="not_applicable"` を読み「適用外」表示する (web/static/app.js)。**運用者は「`failed_types` に該当章が見当たらない」「分析画面で『適用外』表示」を観測した場合、これは正常仕様であって障害ではない**。

### 2.2 `diagnostic` フィールドの読み方

`extraction_error.diagnostic` は **current ADR-004 ジョブでは原則 `null`**。詳細 diagnostic は legacy PageIndex 経路でのみ埋まる (発生源を以下に整理):

| 発生源 | 取得経路 | 現行 ADR-004 での挙動 |
|---|---|---|
| **current**: `RagService.preflight()` (`rag_service.py:246-271`) | `analysis_worker._run_job` の preflight 失敗時に `preflight.get("diagnostic")` を保存 | **常に `null`**。`preflight()` は `status` / `model` / `reason` / `response_head` だけを返し、`diagnostic` キーを返さない |
| **current**: `RagService.run_full_analysis_stream` 中の章抽出失敗 | stream の `{"event": "error", "analysis_type": null, "message": ...}` から worker が `event.get("diagnostic")` を保存 | **常に `null`**。`_section_extractor.extract()` の例外は `message` (= `str(exc)`) のみを emit |
| **legacy**: PageIndex 経路の TOC 生成失敗 (`PageIndexService.query` 内ラッパー) | ADR-004 以前は `pageindex/service.py` 系で `kind/model/finish_reason/content_head/prompt_head/...` を埋めていた | ADR-004 以後の定型分析経路では発火しない。`ask_question` 経路に類似の診断が出る場合は legacy ドキュメントを参照 |

**運用判断: current ADR-004 ジョブの `extraction_error` を調べるときの順序**

1. `extraction_error.message` を最初に見る:
   - `preflight failed (error): <reason>` → llama-server 状態を確認 (§3.1 / §3.2)
   - それ以外 (extractor が投げた例外文字列) → §3.4 抽出器デバッグへ
2. `extraction_error.diagnostic` は **`null` が正常** (ADR-004 では埋められない)。`null` であることが障害サインではない
3. `model` / `response_head` は **job row に残らない**。`preflight()` の戻り値には乗るが、`analysis_worker._run_job` (`analysis_worker.py:208-211`) は `reason` だけを `ExtractionFailedError` の message に埋めて捨てている。`RagService preflight failed: %s` warning も exception 経路 (`rag_service.py:261`) でしか出ず、empty 応答経路 (`rag_service.py:265-270`) はログを残さない
4. LLM 側の実機状態は次のいずれかで確認する:
   - `curl -s http://localhost:8080/v1/models` でロード中モデル名を取得
   - `data/logs/llama-server.log` の最新行
   - REPL で `await RagService(...).preflight()` を手動再現し戻り値の `model` / `response_head` を直接見る

(備考) 現状 `preflight()` の戻り値を `diagnostic` フィールドに集約する実装は持っていない。将来 worker 側でこれらを保存する場合、本表 "legacy" 行の key 体系に揃え、§2.2 の本注記を撤回すること。

## 3. 復旧手順

### 3.1 LLM 接続不能 / Connection error

```bash
curl -s http://localhost:8080/v1/models | jq
# 何も返らない → llama-server を再起動
# 別モデルが返る → 設定 config/settings.yaml の model と一致しているか確認
```

### 3.2 `<think>` 暴走 (`finish_reason=max_output_reached` + `content_head="<think>"`)

1. llama-server を `--jinja` 付きで再起動
2. JSON-mode が独立して効くか手動確認:

   ```bash
   curl -s http://localhost:8080/v1/chat/completions \
     -H 'Content-Type: application/json' -d '{
       "model": "openai/Qwen3.6-27B-Q4_K_M.gguf",
       "messages": [{"role":"user","content":"Return JSON: {\"ok\": 1}"}],
       "response_format": {"type":"json_object"},
       "max_tokens": 256,
       "extra_body": {"chat_template_kwargs": {"enable_thinking": false}}
     }' | jq '.choices[0]'
   ```

   `finish_reason: "stop"` かつ content に `<think>` を含まないなら復旧。なお続く場合は、`config/settings.yaml` の `max_tokens` を縮めるとクランプ (commit fcc0960) が `generate_toc_init` の 32768 を上書きする。

   **本手順の有効範囲**: 本節 (§3.2) は **`ask_question` (自由質問) 経路専用** である (ADR-004 適用後)。定型分析 4 種は extractor 経由で LLM ゼロで章を取るため `<think>` 暴走は起こり得ない。定型分析側で章が空になった場合は §3.4 へ。

### 3.3 特定の analysis_type だけ失敗

`failed_types[].message` を読む。`OpenAIException - Connection error.` なら LLM 側、`JSONDecodeError` なら `services/prompts.py` の prompt と spec のミスマッチを疑う。

**ADR-004 §4.5 のリスク**: `risk_factors` / `mda` の章テキストは数千〜数万文字 (RXRX 10-K Item 1A は ~32 万字)。**定型分析の章抽出自体は LLM 非依存 (extractor が HTML から決め打ちで取る) だが、step 3 (`RagService._analyze_section`) は抽出済み章本文を `LlmClient.completion` に prompt として連結して LLM に渡す**。ADR-004 検証済み構成 (`--ctx-size 131072 --parallel 1 --jinja`、`docs/step3-reasoning-runaway-verification.md` 参照) では `reasoning_content` 暴走は再現せず、`_is_empty_llm_response` ガード (`RagService._analyze_section` 内) が空応答を `ValueError` に変換して `failed_types[].message` に出すため fail を隠さない。`ask_question` 経路は `response_format` を渡さない + PageIndex-selected context (tree search で選ばれたノード群、`PageIndexService.query` の `selected_nodes`) を context に積む構造で、章丸ごとではないものの選定ノード次第で同等のトークン規模に膨らみ得るため同じ症状が出やすい。

`failed_types[].message` に `JSONDecodeError` や空応答が頻発したら:
- **定型分析の per-type 失敗**: §1 の llama-server 起動コマンドが `--ctx-size 131072 --parallel 1 --jinja` 構成と一致しているか確認 (ctx を絞ったり parallel slot を増やすと章 + prompt が overflow して空応答 / `BadRequestError` になる)。一致していれば `services/prompts.py` の prompt と spec のミスマッチを疑う
- **`ask_question` 経路の失敗**: §3.2 の jinja / chat template 手順を踏む。ADR-004 適用後も `ask_question` は LLM 経路を残しているため §3.2 の有効範囲内

### 3.4 定型分析で章が空 (ADR-004 後の新パターン)

`error_details` 形と UI 表示で 2 系統に分けて判定する:

| 観測 | 意味 | 対応 |
|---|---|---|
| ジョブが **`COMPLETED`** + `error_details=null` + UI で対象 type が **「適用外」表示** | `is_structurally_empty()` で除外された構造上空の章 (10-Q `business_summary`/`competitors`、6-K `risk_factors`/`competitors` 等)。placeholder (`_status="not_applicable"`) で保存された結果 | 対処不要 (正常仕様) |
| ジョブが **`FAILED`** + `error_details.failed_types[].message="ファイリングから章テキストを抽出できませんでした"` | 構造上存在するはずの章 (10-K 全 4 種 / 10-Q `mda`,`risk_factors` / 20-F 全 4 種 / 6-K `business_summary`,`mda`) を `FilingSectionExtractor` のフォールバック chain が取り切れなかった | 以下の抽出器切り分け手順を実行 |

抽出器の取りこぼしを切り分ける手順:

```bash
# 1. log で "filing N: %s recovered via regex fallback" の有無を確認
grep "recovered via regex" data/logs/stock_analyze.log

# 2. 当該 filing の HTML を直接 extractor に流す REPL
uv run python - <<'PY'
import asyncio
from dataclasses import dataclass
from stock_analyze_system.services.filing_section_extractor import (
    FilingSectionExtractor,
)

@dataclass
class F:
    id: int = 0
    filing_type: str = "10-K"   # 該当 filing の filing_type を指定
    storage_path: str = "/data/filings/SEC/...."  # 該当 filing の storage_path

print(asyncio.run(FilingSectionExtractor().extract(F())))
PY
```

各 fallback 段で結果が変わるため、`_SECTION_KEY_MAP` / `_FULL_TEXT_FALLBACK` / `_REGEX_FALLBACK` に該当 filing の章キーパターンを追加する PR を出す。

## 4. 既知の制約

- 修正コミット 1 (`fe0b153`) 以前の `data/logs/stock_analyze.log` は存在しない。`infisical-run` 起動時の stdout は `logs/worker.log` / `logs/web-server.log` (旧) ではなく、Python ロガー経由の `data/logs/stock_analyze.log` を見る
- 修正コミット 5 (`3c695e6`) 以前に失敗したジョブは `failed_types: [{type: null, ...}]` 形式で残っている。UI は両形式を表示できる (`web/static/app.js:1070-`) が、`diagnostic` フィールドは取れない
- A 層仮説 (思考トークン暴走) は 2026-05-16 にジョブ#21 + 手動 curl で確定済み。**ADR-004 (`docs/adr/004-sec-filing-section-extractor.md`) の固定セクション抽出で定型分析の章取得段から LLM を排除して解消**。ask_question 経路では引き続き発火し得る
- ADR-004 §4.5 のステップ 3 リスク (LLM が `risk_factors`/`mda` の大型 context で `reasoning_content` 暴走) は **ADR-004 検証済み構成 (`--ctx-size 131072 --parallel 1 --jinja`) では再現しない** (検証ログは `docs/step3-reasoning-runaway-verification.md`)。旧 ctx/parallel への rollback、モデル更新、chat template 変更で再発した場合は別 ADR で扱う。`_is_empty_llm_response` ガード (`rag_service._analyze_section`) が defense-in-depth で残り、空応答は `failed_types[].message` に出る

## 5. 関連ドキュメント

- `docs/adr/004-sec-filing-section-extractor.md` — **定型分析を PageIndex から SEC 専用固定セクション抽出に置き換えた決定 (実装済み)**
- `docs/analysis-failures-root-cause.md` — 多角的根本原因分析と修正計画
- `docs/RAGtest_debug.md` — RAG 個別動作のデバッグ手順
- `MEMORY/project_rag_rootcause.md` — 過去の根本原因 (2モデル構成計画 — ADR-004 で superseded)
- `MEMORY/project_section_extractor_pivot.md` — ADR-004 移行メモ
- `MEMORY/project_greenboost.md` — GreenBoost 関連の運用前提
