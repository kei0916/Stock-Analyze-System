# vLLM Backend Migration Design

## Goal

LLMバックエンドをOllamaからvLLMに切り替え可能にし、AWQ量子化モデルによるパフォーマンス改善とUD量子化を含むモデル互換性の向上を実現する。

## Background

現在Ollama + qwen3.5:27b-q8_0（29GB）を使用しているが、2つの問題がある：

1. **パフォーマンス**: 29GBモデルが24GB VRAMに収まらず、半分がCPUオフロードされて1回のLLM呼び出しに7-8分かかる
2. **モデル互換性**: OllamaがunslothのUD量子化形式をサポートしていない（`unknown model architecture`エラー）

vLLMはPagedAttention、continuous batching等の最適化を持ち、AWQ量子化をネイティブサポートする。AWQ 4bit量子化のQwen3.5-27B（約17GB）は24GB VRAMに収まり、GPU最適化が効く。

## Architecture

LiteLLMを抽象化レイヤーとして活用し、`settings.yaml` のconfig変更のみでOllama/vLLMを切り替える。コード変更は最小限。

```
settings.yaml (backend: "ollama" | "vllm")
    ↓
LlmClient (llm_client.py) — base_urlプロパティ追加のみ
    ↓
litellm.acompletion(model=..., api_base=...)
    ↓
Ollama (ollama/model:tag)  OR  vLLM (openai/model-name)
```

## Tech Stack

- **vLLM**: OpenAI互換APIサーバーとしてローカル起動（`vllm serve`）
- **LiteLLM**: 既存の抽象化レイヤー（変更なし）
- **AWQ量子化**: `QuantTrio/Qwen3.5-27B-AWQ`（HuggingFace、21GB、4bit）
- **Python**: vllmパッケージをオプショナル依存として追加

## Design

### 1. 設定（Config）

`LlmConfig` のフィールドは変更なし。既存フィールドで対応可能：

| フィールド | Ollama時 | vLLM時 |
|---|---|---|
| `backend` | `"ollama"` | `"vllm"` |
| `base_url` | `http://localhost:11434` | `http://localhost:8000/v1` |
| `model` | `ollama/qwen3.5:27b-q8_0` | `openai/QuantTrio/Qwen3.5-27B-AWQ` |
| `model_quality` | （同上） | （同上） |
| `request_timeout` | `1200` | `600`（vLLMは高速） |

`backend` フィールドはログ/ヘルスチェックの表示に使用。LiteLLMはモデル名プレフィックス（`ollama/` / `openai/`）でプロバイダーを判定するため、`backend` による分岐ロジックは不要。

### 2. LlmClient（軽微な変更）

`llm_client.py` は `litellm.acompletion()` に `model` と `api_base` を渡すだけの薄いラッパー。LiteLLMがプロバイダー差を吸収するため、呼び出しロジックの変更は不要。

`resolve_model()` もそのまま動く（モデル名の形式が変わるだけ）。

**追加**: `base_url` のpublicプロパティを追加する。`pageindex_service.py` が `api_base` を取得するために使用。プライベート属性 `_config` への外部アクセスを避ける。

```python
@property
def base_url(self) -> str:
    return self._config.base_url
```

### 3. PageIndex外部ライブラリの対応

PageIndexは独自にLiteLLMを呼んでおり、`api_base` を渡していない。vLLM使用時は `openai/model-name` だけではOpenAI公式APIに接続してしまう。

**伝播戦略**: 2層のアプローチで対応する。

- **トップレベル**: `page_index()` 関数と `config.yaml` に `api_base` パラメータを追加。`opt` configオブジェクト（SimpleNamespace）に `opt.api_base` として保持。
- **中間関数**: `page_index.py` 内の22個の関数は `model=None` を直接パラメータとして受け取り、`llm_completion(model=model, ...)` のように渡している。これらすべてに `api_base=None` パラメータを追加し、同様に `llm_completion(model=model, api_base=api_base, ...)` として伝播させる。

**変更内容:**

#### 3a. `/tmp/PageIndex/pageindex/config.yaml`

`api_base` をデフォルト設定に追加：

```yaml
model: "gpt-4o-2024-11-20"
api_base: null    # 追加: None = LiteLLMのデフォルト動作
toc_check_page_num: 20
# ...
```

#### 3b. `/tmp/PageIndex/pageindex/utils.py`

`llm_completion` と `llm_acompletion` に `api_base` 引数を追加：

```python
def llm_completion(model, prompt, chat_history=None, return_finish_reason=False, api_base=None):
    response = litellm.completion(
        model=model, messages=messages, temperature=0,
        api_base=api_base,
    )

async def llm_acompletion(model, prompt, api_base=None):
    response = await litellm.acompletion(
        model=model, messages=messages, temperature=0,
        api_base=api_base,
    )
```

`generate_node_summary` と `generate_doc_description` にも `api_base` 引数を追加し、内部の `llm_acompletion` / `llm_completion` に渡す。`generate_summaries_for_structure` も同様に `api_base` を受け取り `generate_node_summary` に渡す。

#### 3c. `/tmp/PageIndex/pageindex/page_index.py`

以下の22個の関数すべてに `api_base=None` パラメータを追加し、内部のLLM呼び出しに伝播：

**シグネチャ変更が必要な関数（`model=None` を受け取る全関数）:**
1. `check_title_appearance(item, page_list, start_index, model, api_base)`
2. `check_title_appearance_in_start(title, page_text, model, api_base, logger)`
3. `check_title_appearance_in_start_concurrent(structure, page_list, model, api_base, logger)`
4. `toc_detector_single_page(content, model, api_base)`
5. `check_if_toc_extraction_is_complete(content, toc, model, api_base)`
6. `check_if_toc_transformation_is_complete(content, toc, model, api_base)`
7. `extract_toc_content(content, model, api_base)`
8. `detect_page_index(toc_content, model, api_base)`
9. `toc_index_extractor(toc, content, model, api_base)`
10. `toc_transformer(toc_content, model, api_base)`
11. `add_page_number_to_toc(part, structure, model, api_base)`
12. `generate_toc_continue(toc_content, part, model, api_base)`
13. `generate_toc_init(part, model, api_base)`
14. `process_no_toc(page_list, start_index, model, api_base, logger)`
15. `process_toc_no_page_numbers(toc_content, toc_page_list, page_list, start_index, model, api_base, logger)`
16. `process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num, model, api_base, logger)`
17. `process_none_page_numbers(toc_items, page_list, start_index, model, api_base)`
18. `single_toc_item_index_fixer(section_title, content, model, api_base)`
19. `fix_incorrect_toc(toc_with_page_number, page_list, incorrect_results, start_index, model, api_base, logger)`
20. `fix_incorrect_toc_with_retries(toc_with_page_number, page_list, incorrect_results, start_index, max_attempts, model, api_base, logger)`
21. `verify_toc(page_list, list_result, start_index, N, model, api_base)`
22. `page_index(doc, model, api_base, toc_check_page_num, ...)` — エントリポイント

**呼び出し側の変更パターン（約25箇所）:**
各関数内で `llm_completion(model=model, ...)` → `llm_completion(model=model, api_base=api_base, ...)` に変更。
関数間の呼び出しも同様に `api_base=api_base` を追加。

`page_index_main()` は `opt` から値を取得:
```python
# opt.model と opt.api_base を中間関数に渡す
detected_result = toc_detector_single_page(page_list[i][0], model=opt.model, api_base=opt.api_base)
```

`generate_summaries_for_structure` と `generate_doc_description` の呼び出し（`page_index_main` 内）:
```python
await generate_summaries_for_structure(structure, model=opt.model, api_base=opt.api_base)
doc_description = generate_doc_description(clean_structure, model=opt.model, api_base=opt.api_base)
```

#### 3d. `pageindex_service.py`

`build_index()` から `page_index()` 呼び出し時に `api_base` を渡す。`page_index()` のシグネチャに `api_base` が追加されるため、直接渡せる：

```python
tree = page_index(
    pdf_path,
    model=model_name,
    api_base=self._llm_client.base_url,  # publicプロパティ経由
    ...
)
```

`query()` 内の `LlmClient.completion()` 呼び出しは既に `api_base` を使用しているため変更不要。

### 4. 環境変数の対応

**`OPENAI_API_KEY` の要件**: LiteLLMで `openai/` プレフィックスを使用する場合、`OPENAI_API_KEY` 環境変数が必要。ローカルvLLMサーバーでは認証不要だが、LiteLLMがキーの存在を検証する。

**対応**: `.env` ファイルにダミー値を設定：
```
OPENAI_API_KEY=dummy
```

`settings.yaml.example` とドキュメントにこの要件を記載する。

### 5. vLLMサーバー運用

**起動コマンド:**
```bash
vllm serve QuantTrio/Qwen3.5-27B-AWQ \
    --port 8000 \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.9 \
    --trust-remote-code
```

- `--max-model-len 32768`: KVキャッシュメモリを制限し24GB VRAMに収める
- `--gpu-memory-utilization 0.9`: VRAM使用率上限（デフォルト0.9）
- `--trust-remote-code`: HuggingFaceモデルのカスタムコード実行許可
- AWQ 4bit: 約21GB、24GB VRAMに収まる
- ポート8000: vLLMデフォルト
- 注: `--tensor-parallel-size` はGPU 1枚の場合不要（デフォルト1）

**モデルダウンロード（事前準備）:**
```python
from huggingface_hub import snapshot_download
snapshot_download('QuantTrio/Qwen3.5-27B-AWQ', cache_dir="models/")
```

**要件**: vllm>=0.16.0, transformers>=5.3.0, CUDA 12.8

**モデル戦略:**
- speed/quality 2モデル戦略は構造として維持
- 24GB VRAMで同一サーバーに複数モデルは困難なため、初期実装では `model` と `model_quality` に同一モデルを設定

### 6. 依存関係

`pyproject.toml` にオプショナル依存として追加：

```toml
[project.optional-dependencies]
vllm = ["vllm"]
```

インストール: `pip install .[vllm]`

vLLMはサーバーとして別プロセスで動くため、アプリケーション自体にvllmパッケージは不要。ただし `vllm serve` コマンド実行のために同じ環境にインストールする想定。

### 7. 設定例（settings.yaml.example）

新規作成。Ollama/vLLM両方の設定例をコメント付きで記載：

```yaml
llm:
  ## Ollama backend
  # backend: ollama
  # base_url: http://localhost:11434
  # model: ollama/qwen3.5:27b-q8_0
  # model_quality: ollama/qwen3.5:27b-q8_0
  # request_timeout: 1200

  ## vLLM backend (AWQ quantization)
  ## Requires: OPENAI_API_KEY=dummy in .env
  ## Start server: vllm serve QuantTrio/Qwen3.5-27B-AWQ --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.9 --trust-remote-code
  backend: vllm
  base_url: http://localhost:8000/v1
  model: openai/QuantTrio/Qwen3.5-27B-AWQ
  model_quality: openai/QuantTrio/Qwen3.5-27B-AWQ
  temperature: 0.1
  max_tokens: 32768
  request_timeout: 600
```

## Design Note: asyncio.run() in PageIndex

`page_index.py` の `page_index_main()` は内部で `asyncio.run()` を呼ぶ。`pageindex_service.py` は `asyncio.to_thread()` 経由でこれを実行する。`to_thread` は別スレッドで実行するため、そのスレッドには既存のイベントループがなく `asyncio.run()` が正常に動作する。この非自明なスレッド/async相互作用は今回の変更では影響しないが、将来のメンテナンスのために記録しておく。

## Testing

### ユニットテスト

**`tests/unit/services/test_llm_client.py`** に追加：
- vLLM設定時の `resolve_model` がOpenAI形式のモデル名を正しく返すこと
- `health_check()` がvLLM backendで正しい情報を返すこと
- `base_url` プロパティが正しい値を返すこと

**`tests/unit/services/test_pageindex_service.py`** に追加：
- `build_index` が `api_base` パラメータをPageIndexの `page_index()` に正しく渡すこと

既存テストはLiteLLMをモックしているため影響なし。

### 手動検証（実データ）

1. `vllm serve QuantTrio/Qwen3.5-27B-AWQ --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.9 --trust-remote-code`
2. `python -m stock_analyze_system rag health` — ヘルスチェック
3. `python -m stock_analyze_system rag index US_AAPL` — PageIndex構築（速度比較）
4. `python -m stock_analyze_system rag ask US_AAPL "What is Apple's revenue?"` — クエリ

## Files Changed

| ファイル | 変更種別 | 内容 |
|---|---|---|
| `src/.../services/llm_client.py` | 修正 | `base_url` publicプロパティ追加 |
| `/tmp/PageIndex/pageindex/config.yaml` | 修正 | `api_base: null` デフォルト追加 |
| `/tmp/PageIndex/pageindex/utils.py` | 修正 | `llm_completion`/`llm_acompletion`/`generate_node_summary`/`generate_doc_description` に `api_base` 引数追加 |
| `/tmp/PageIndex/pageindex/page_index.py` | 修正 | 約25箇所のLLM呼び出しに `api_base=opt.api_base` 追加 |
| `src/.../services/pageindex_service.py` | 修正 | `api_base` をPageIndexに渡す |
| `config/settings.yaml.example` | 新規作成 | Ollama/vLLM両方の設定例 |
| `pyproject.toml` | 修正 | vllmオプショナル依存追加 |
| `tests/unit/services/test_llm_client.py` | 修正 | vLLM設定テスト追加 |
| `tests/unit/services/test_pageindex_service.py` | 修正 | `api_base` 伝播テスト追加 |

## Files NOT Changed

| ファイル | 理由 |
|---|---|
| `config.py` | 既存フィールドで対応可能 |
| `rag_service.py` | LlmClient経由のため影響なし |
| `cli/helpers.py` | サービス初期化ロジック変更不要 |
| CLI層全体 | config値変更のみで切り替わる |

## Out of Scope

- vLLMサーバーの自動起動/管理（手動で `vllm serve` を実行する前提）
- 複数モデル同時ロード（VRAMの制約上、初期実装では非対応）
- LlmConfig への `api_key` フィールド追加（vLLMデフォルトではキー不要）
- Ollamaの削除（切り替え可能を維持）
