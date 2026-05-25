# Qwen3.5-27B モデル移行設計仕様書

**日付**: 2026-04-07
**ステータス**: Approved (会話内で承認済み)

---

## 背景と動機

PageIndex推論RAGテストが動作しない根本原因は、推論モデル(gpt-oss-20b)の `<|channel|>analysis` チャネルシステムがllama.cppのreasoning budget機能と非互換であること。PageIndexの~150-400回のLLM呼び出しにおいて、per-call成功率が~50%のため、パイプライン完走確率が事実上ゼロ。

PageIndexのタスクは「指示追従(instruction following)」が主体であり、推論は不要。Qwen3.5-27BのHybrid DeltaNet + Full Attentionアーキテクチャと `/nothink` モード切替により、1モデルで構築(非推論)とクエリ(推論)を両立する。

## 選定モデル: Qwen3.5-27B Q4_K_M

### 選定根拠

| 指標 | Qwen3.5-27B Q4_K_M | gpt-oss-20b Q4_0 (現行) | Qwen2.5-32B Q4_K_M |
|------|--------------------|-----------------------|--------------------|
| ファイルサイズ | 15.6 GB | ~11 GB | 19.9 GB |
| IFEval (指示追従) | 87.8 | N/A | 79.5 |
| 128K KV cache (Q8) | **4.0 GB** | 不明 | 16.0 GB |
| 128K 総メモリ | **~23 GB (全VRAM)** | content=null問題 | ~39 GB (T2: 15GB) |
| Max Context | 262K (native) | 32K | 128K (YaRN) |
| Think/Nothink | 切替可能 | チャネル非互換 | 非推論のみ |
| `<think>` llama.cpp互換 | 完全互換 | **非互換** | N/A |

### アーキテクチャ特性

- 64層: 48層 DeltaNet線形注意(O(n)スケーリング) + 16層 Full Attention
- KVキャッシュは16層のみ → 128Kで4GB、262Kで8GB
- DeltaNet再帰状態は~72MB固定（シーケンス長非依存）

## 設計

### 2モード切替方式

```
PageIndex構築 (150-400 LLM calls):
  → enable_thinking=false
  → response_format={"type":"json_object"} + grammar制約
  → context: ~8-32K per call
  → 全VRAM動作、高速

RAGクエリ (2-3 LLM calls):
  → enable_thinking=true
  → reasoning-budget=2048
  → context: up to 128K
  → 全VRAM動作、推論品質 MMLU-Pro 86.1
```

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `config/settings.yaml` | llm.model → Qwen3.5-27B、thinking_mode設定追加 |
| `src/.../services/llm_client.py` | completion()にthinking制御パラメータ追加 |
| `src/.../services/pageindex_service.py` | build_index: nothink、query: think |
| `scripts/rag_inference_test.py` | モデル名・BASE_URL更新 |
| `/tmp/PageIndex/pageindex/utils.py` | litellm経由のthinking制御（extra_body） |

### config.yaml 変更

```yaml
llm:
  backend: llamacpp
  base_url: "http://localhost:8080/v1"
  model: "openai/Qwen3.5-27B-Q4_K_M.gguf"
  model_quality: "openai/Qwen3.5-27B-Q4_K_M.gguf"  # 同一モデル、thinkモード
  temperature: 0.1
  max_tokens: 131072
  request_timeout: 600
```

### LlmClient 変更

```python
async def completion(self, prompt, *, thinking: bool = False, ...):
    extra_body = {}
    if not thinking:
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}
    resp = await litellm.acompletion(..., extra_body=extra_body)
```

### PageIndexService 変更

- `build_index()`: PageIndex内部のLLM呼び出しはthinkingをグローバルに無効化
  - `llama-server` 起動時に `--chat-template-kwargs '{"enable_thinking":false}'` を指定
  - またはPageIndexの `llm_completion`/`llm_acompletion` にextra_bodyを追加
- `query()`: `thinking=True` で呼び出し

### インフラ要件

1. llama.cpp 最新ビルド（commit 5bb0985以降、enable_thinking修正含む）
2. Qwen3.5-27B Q4_K_M GGUFダウンロード（15.6 GB）
3. CUDA 13.0パッチ再適用（リビルド時）

### llama-server 起動コマンド

```bash
# PageIndex構築時（nothinkデフォルト）
llama-server \
  -m Qwen3.5-27B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -ngl 999 -c 32768 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --chat-template-kwargs '{"enable_thinking":false}'

# RAGクエリ時（think有効、コンテキスト拡大）
llama-server \
  -m Qwen3.5-27B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -ngl 999 -c 131072 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --reasoning-budget 2048
```

注: 同一サーバーインスタンスでAPIリクエストごとにthinking切替が可能であれば、サーバー再起動は不要。litellmの `extra_body` 経由で `chat_template_kwargs` をper-request指定できるか要検証。

## テスト計画

1. llama.cpp + Qwen3.5-27Bの基本動作確認（health check, JSON mode）
2. enable_thinking=false でのJSON出力検証
3. PageIndex Phase 1（インデックス構築）の完走確認
4. Phase 2（TOC精度検証）→ 目標: 80%以上
5. Phase 3（RAGクエリ）→ thinking=trueで回答品質確認
6. 精度検証データの保存（memory要件準拠）

## リスクと緩和策

| リスク | 緩和策 |
|-------|-------|
| llama.cpp Qwen3.5サポートの不安定性 | フォールバック: Qwen2.5-32B Q4_K_M |
| nothinkモードのJSON品質が不十分 | grammar制約でJSON構造を強制保証 |
| DeltaNetの長文品質が未知数 | 段階的にcontext長を拡大して検証 |
| per-request thinking切替が不可 | サーバー2インスタンス or 再起動方式 |
