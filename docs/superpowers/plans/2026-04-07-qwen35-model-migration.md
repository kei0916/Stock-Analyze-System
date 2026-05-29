# Qwen3.5-27B モデル移行 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PageIndex RAGパイプラインのLLMモデルをgpt-oss-20b(推論モデル/チャネル非互換)からQwen3.5-27B(think/nothink切替)に移行し、インデックス構築が完走できるようにする。

**Architecture:** PageIndex構築はQwen3.5-27Bの`enable_thinking=false`モードで信頼性の高いJSON出力を確保（IFEval 87.8）。RAGクエリは`enable_thinking=true`で推論品質を最大化（MMLU-Pro 86.1）。Hybrid DeltaNetアーキテクチャにより128Kコンテキストが全VRAM(~23GB)に収まる。

**Tech Stack:** llama.cpp (latest build), Qwen3.5-27B Q4_K_M GGUF (15.6GB), litellm, PageIndex

**Spec:** `docs/superpowers/specs/2026-04-07-qwen35-model-migration-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `/tmp/PageIndex/pageindex/utils.py` | thinking制御グローバル設定 + llm呼び出しへの`extra_body`注入 | Modify |
| `config/settings.yaml` | llm/pageindex セクションのモデル名・backend更新 | Modify |
| `src/stock_analyze_system/services/llm_client.py` | `thinking`パラメータ追加、`extra_body`経由でthinking制御 | Modify |
| `src/stock_analyze_system/services/pageindex_service.py` | build_index: thinking無効化、query: thinking有効化 | Modify |
| `scripts/rag_inference_test.py` | モデル名・BASE_URL・Phase 0 設定更新 | Modify |
| `tests/conftest.py` | RAG_TEST_MODEL 更新 | Modify |
| `tests/unit/services/test_llm_client.py` | thinking パラメータのテスト追加 | Create |
| `tests/unit/services/test_pageindex_service.py` | thinking 制御のテスト追加 | Modify |

---

## Task 1: llama.cpp リビルド (enable_thinking 修正含む)

**Files:**
- Modify: `<llama-cpp-source>/` (git pull + rebuild)

- [ ] **Step 1: llama.cpp の最新コミットを取得**

```bash
cd <llama-cpp-source> && git fetch origin && git log --oneline -5 origin/master
```

commit 5bb0985 以降であることを確認（enable_thinking修正）。

- [ ] **Step 2: CUDA 13.0 パッチの必要性を確認**

```bash
cd <llama-cpp-source> && grep -n "cudaSetDevice" ggml/src/ggml-cuda/ggml-cuda.cu | head -5
```

パッチ済み（`ggml_backend_cuda_device_get_memory` で `cudaSetDevice` を常に呼ぶ）であればそのまま。未適用なら `docs/RAGtest_debug.md` Issue 7 の修正を再適用。

- [ ] **Step 3: リビルド**

```bash
cd <llama-cpp-source> && git pull origin master
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 2>&1 | tail -5
cmake --build build --config Release -j$(nproc) 2>&1 | tail -10
```

Expected: `llama-server` バイナリが更新される。

- [ ] **Step 4: 動作確認**

```bash
<llama-cpp-source>/build/bin/llama-server --version
```

Expected: ビルド日時が最新。

---

## Task 2: Qwen3.5-27B Q4_K_M GGUF ダウンロード

**Files:**
- Download: `~/models/Qwen3.5-27B-Q4_K_M.gguf` (15.6 GB)

- [ ] **Step 1: モデルディレクトリ作成**

```bash
mkdir -p ~/models
```

- [ ] **Step 2: GGUF ダウンロード**

```bash
# huggingface-cli が利用可能な場合:
huggingface-cli download unsloth/Qwen3.5-27B-GGUF Qwen3.5-27B-Q4_K_M.gguf --local-dir ~/models

# または wget:
# wget -O ~/models/Qwen3.5-27B-Q4_K_M.gguf "https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/resolve/main/Qwen3.5-27B-Q4_K_M.gguf"
```

Expected: `~/models/Qwen3.5-27B-Q4_K_M.gguf` (約15.6 GB)

- [ ] **Step 3: ファイルサイズ確認**

```bash
ls -lh ~/models/Qwen3.5-27B-Q4_K_M.gguf
```

Expected: ~15-16 GB

- [ ] **Step 4: llama-server でロード確認**

```bash
<llama-cpp-source>/build/bin/llama-server \
  -m ~/models/Qwen3.5-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  -ngl 999 -c 4096 \
  --chat-template-kwargs '{"enable_thinking":false}' &
sleep 5
curl -s http://127.0.0.1:8080/v1/models | python3 -m json.tool
kill %1
```

Expected: モデル一覧にエントリが表示される。

---

## Task 3: PageIndex utils.py にthinking制御を追加

**Files:**
- Modify: `/tmp/PageIndex/pageindex/utils.py:23-106`

- [ ] **Step 1: thinking制御のグローバル設定を追加**

`/tmp/PageIndex/pageindex/utils.py` の `litellm.drop_params = True` の直後（line 24付近）に追加:

```python
# Thinking mode control for reasoning models (e.g. Qwen3.5)
_ENABLE_THINKING = True  # Default: thinking enabled


def configure_thinking(enabled: bool) -> None:
    """Set whether LLM calls should use thinking/reasoning mode."""
    global _ENABLE_THINKING
    _ENABLE_THINKING = enabled
```

- [ ] **Step 2: `llm_completion` に `extra_body` を追加**

`llm_completion` 関数内の `litellm.completion()` 呼び出し（line 47-54付近）を変更:

```python
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=0,
                api_base=api_base,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                extra_body={"chat_template_kwargs": {"enable_thinking": _ENABLE_THINKING}},
            )
```

- [ ] **Step 3: `llm_acompletion` に `extra_body` を追加**

`llm_acompletion` 関数内の `litellm.acompletion()` 呼び出し（line 84-90付近）を変更:

```python
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=0,
                api_base=api_base,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                extra_body={"chat_template_kwargs": {"enable_thinking": _ENABLE_THINKING}},
            )
```

- [ ] **Step 4: 手動テスト — nothinkモードでJSON出力確認**

llama-server を起動（Task 2 Step 4 参照）し、Python で確認:

```python
import litellm
litellm.drop_params = True
resp = litellm.completion(
    model="openai/Qwen3.5-27B-Q4_K_M.gguf",
    messages=[{"role": "user", "content": 'Return JSON: {"answer": "yes"}'}],
    api_base="http://localhost:8080/v1",
    response_format={"type": "json_object"},
    max_tokens=256,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
print(repr(resp.choices[0].message.content))
```

Expected: `<think>` タグなしの純粋なJSON文字列（例: `'{"answer": "yes"}'`）

---

## Task 4: config/settings.yaml 更新

**Files:**
- Modify: `config/settings.yaml`

- [ ] **Step 1: llm セクション更新**

```yaml
llm:
  backend: llamacpp
  base_url: "http://localhost:8080/v1"
  model: "openai/Qwen3.5-27B-Q4_K_M.gguf"
  model_quality: "openai/Qwen3.5-27B-Q4_K_M.gguf"
  temperature: 0.1
  max_tokens: 131072
  request_timeout: 600
```

- [ ] **Step 2: pageindex セクション更新**

```yaml
pageindex:
  enabled: true
  toc_check_pages: 20
  max_pages_per_node: 10
  max_tokens_per_node: 20000
  add_node_summary: true
  add_node_text: true
  cache_indices: true
```

注: `model` と `backend` と `lm_studio_base_url` フィールドを削除。PageIndexは `llm` セクションの設定を使用する。

- [ ] **Step 3: コミット**

```bash
git add config/settings.yaml
git commit -m "config: switch LLM to Qwen3.5-27B Q4_K_M on llama.cpp"
```

---

## Task 5: LlmClient に thinking パラメータ追加

**Files:**
- Modify: `src/stock_analyze_system/services/llm_client.py`
- Test: `tests/unit/services/test_llm_client.py`

- [ ] **Step 1: テストファイル作成 — thinking パラメータ**

```python
# tests/unit/services/test_llm_client.py
"""LlmClient単体テスト"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from stock_analyze_system.config import LlmConfig
from stock_analyze_system.services.llm_client import LlmClient


@pytest.fixture
def llm_config():
    return LlmConfig(
        backend="llamacpp",
        base_url="http://localhost:8080/v1",
        model="openai/Qwen3.5-27B-Q4_K_M.gguf",
        model_quality="openai/Qwen3.5-27B-Q4_K_M.gguf",
        temperature=0.1,
        max_tokens=4096,
        request_timeout=60,
    )


@pytest.fixture
def client(llm_config):
    return LlmClient(llm_config)


class TestCompletion:
    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_thinking_false_passes_extra_body(self, mock_litellm, client):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = '{"answer": "yes"}'
        mock_litellm.acompletion.return_value = mock_resp

        await client.completion("test prompt", thinking=False)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": False},
        }

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_thinking_true_passes_extra_body(self, mock_litellm, client):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "deep analysis"
        mock_litellm.acompletion.return_value = mock_resp

        await client.completion("test prompt", thinking=True)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": True},
        }

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_thinking_default_is_false(self, mock_litellm, client):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_litellm.acompletion.return_value = mock_resp

        await client.completion("test prompt")

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


class TestResolveModel:
    def test_default_model(self, client):
        assert client.resolve_model() == "openai/Qwen3.5-27B-Q4_K_M.gguf"

    def test_quality_model(self, client):
        assert client.resolve_model(quality=True) == "openai/Qwen3.5-27B-Q4_K_M.gguf"

    def test_explicit_override(self, client):
        assert client.resolve_model(model="custom/model") == "custom/model"
```

- [ ] **Step 2: テスト実行 — RED確認**

```bash
cd <repo-root> && python -m pytest tests/unit/services/test_llm_client.py -v
```

Expected: `test_thinking_false_passes_extra_body` と `test_thinking_default_is_false` が FAIL（`extra_body` 未実装のため）

- [ ] **Step 3: LlmClient に thinking パラメータ実装**

`src/stock_analyze_system/services/llm_client.py` を以下に変更:

```python
"""litellm非同期ラッパー — モデル選択・タイムアウト・ヘルスチェック"""
from __future__ import annotations

import litellm

from stock_analyze_system.config import LlmConfig


class LlmClient:
    """litellm経由の非同期LLMクライアント"""

    def __init__(self, config: LlmConfig):
        self._config = config

    @property
    def base_url(self) -> str:
        """LLMバックエンドのベースURLを返す"""
        return self._config.base_url

    @property
    def max_tokens(self) -> int:
        """設定されたmax_tokensを返す"""
        return self._config.max_tokens

    def resolve_model(
        self,
        *,
        quality: bool = False,
        model: str | None = None,
    ) -> str:
        """用途に応じたモデル名を解決する"""
        if model:
            return model
        if quality and self._config.model_quality:
            return self._config.model_quality
        return self._config.model

    async def completion(
        self,
        prompt: str,
        *,
        system: str | None = None,
        quality: bool = False,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: bool = False,
    ) -> str:
        """LLM補完を実行し応答テキストを返す"""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await litellm.acompletion(
            model=self.resolve_model(quality=quality, model=model),
            messages=messages,
            api_base=self._config.base_url,
            timeout=self._config.request_timeout,
            max_tokens=max_tokens or self._config.max_tokens,
            temperature=temperature if temperature is not None else self._config.temperature,
            extra_body={"chat_template_kwargs": {"enable_thinking": thinking}},
        )
        return resp.choices[0].message.content or ""

    async def health_check(self) -> dict:
        """LLM接続ヘルスチェック"""
        try:
            await self.completion("Reply OK.", max_tokens=10)
            return {
                "status": "ok",
                "model": self._config.model,
                "backend": self._config.backend,
                "base_url": self._config.base_url,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "model": self._config.model,
                "backend": self._config.backend,
                "base_url": self._config.base_url,
            }
```

変更点: `completion()` に `thinking: bool = False` 引数を追加。`extra_body` 経由でllama.cppに `chat_template_kwargs` を渡す。デフォルトは `False`（PageIndex構築の呼び出しが大半のため）。

- [ ] **Step 4: テスト実行 — GREEN確認**

```bash
cd <repo-root> && python -m pytest tests/unit/services/test_llm_client.py -v
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/services/llm_client.py tests/unit/services/test_llm_client.py
git commit -m "feat: add thinking mode control to LlmClient"
```

---

## Task 6: PageIndexService で thinking モードを使い分ける

**Files:**
- Modify: `src/stock_analyze_system/services/pageindex_service.py:137-168,195-264`
- Modify: `tests/unit/services/test_pageindex_service.py`

- [ ] **Step 1: テスト追加 — build_index が configure_thinking(False) を呼ぶ**

`tests/unit/services/test_pageindex_service.py` の `TestBuildIndex` クラスに追加:

```python
    @patch("stock_analyze_system.services.pageindex_service.configure_thinking")
    @patch("stock_analyze_system.services.pageindex_service.page_index")
    async def test_build_index_disables_thinking(self, mock_pi, mock_cfg_think, service):
        mock_pi.return_value = {"title": "Doc"}

        await service.build_index(Path("/fake/doc.pdf"))

        mock_cfg_think.assert_any_call(False)
```

- [ ] **Step 2: テスト追加 — query が thinking=True を渡す**

`tests/unit/services/test_pageindex_service.py` の `TestQuery` クラスに追加:

```python
    async def test_query_uses_thinking_mode(self, service, llm_client):
        tree = {
            "title": "Doc",
            "nodes": [{"id": "1", "title": "S1", "text": "text"}],
        }
        llm_client.completion.side_effect = [
            json.dumps({"node_list": ["1"], "thinking": "reason"}),
            "Answer text.",
        ]

        await service.query(tree, "question?", Path("/fake/doc.pdf"))

        for call in llm_client.completion.call_args_list:
            assert call[1].get("thinking") is True
```

- [ ] **Step 3: テスト実行 — RED確認**

```bash
cd <repo-root> && python -m pytest tests/unit/services/test_pageindex_service.py::TestBuildIndex::test_build_index_disables_thinking tests/unit/services/test_pageindex_service.py::TestQuery::test_query_uses_thinking_mode -v
```

Expected: FAIL

- [ ] **Step 4: pageindex_service.py に configure_thinking import と thinking 制御を実装**

`src/stock_analyze_system/services/pageindex_service.py` の先頭 import に追加:

```python
try:
    from pageindex.utils import configure_thinking
except ImportError:  # pragma: no cover
    configure_thinking = None  # type: ignore[assignment]
```

`build_index` メソッドを変更（`async with _build_semaphore:` ブロック内の先頭）:

```python
    async def build_index(self, pdf_path: Path) -> BuildResult:
        """PDFからPageIndexツリーインデックスを構築する"""
        model = self._llm_client.resolve_model(quality=False)
        logger.info("Building PageIndex for %s with model %s", pdf_path, model)

        timing = BuildTiming()
        t_total = time.perf_counter()

        async with _build_semaphore:
            if configure_thinking is not None:
                configure_thinking(False)
            t0 = time.perf_counter()
            tree = await asyncio.to_thread(
                page_index,
                str(pdf_path),
                model=model,
                api_base=self._llm_client.base_url,
                toc_check_page_num=self._config.toc_check_pages,
                max_page_num_each_node=self._config.max_pages_per_node,
                max_token_num_each_node=self._config.max_tokens_per_node,
                if_add_node_summary="yes" if self._config.add_node_summary else "no",
                if_add_node_text="yes" if self._config.add_node_text else "no",
                max_tokens=self._llm_client.max_tokens,
            )
            timing.page_index_call = time.perf_counter() - t0

        timing.total = time.perf_counter() - t_total

        nodes = _count_nodes(tree)
        logger.info(
            "PageIndex built: %d nodes, timing: %s", nodes, timing,
        )
        return BuildResult(tree=tree, timing=timing)
```

`query` メソッド内の `completion` 呼び出しに `thinking=True` を追加:

```python
        search_result = await self._llm_client.completion(
            search_prompt, quality=True, model=model, thinking=True,
        )
```

```python
        answer = await self._llm_client.completion(
            answer_prompt, quality=True, model=model, thinking=True,
        )
```

- [ ] **Step 5: テスト実行 — GREEN確認**

```bash
cd <repo-root> && python -m pytest tests/unit/services/test_pageindex_service.py -v
```

Expected: 全テスト PASS

- [ ] **Step 6: コミット**

```bash
git add src/stock_analyze_system/services/pageindex_service.py tests/unit/services/test_pageindex_service.py
git commit -m "feat: PageIndex build uses nothink, RAG query uses think mode"
```

---

## Task 7: conftest と RAG テストスクリプト更新

**Files:**
- Modify: `tests/conftest.py:71`
- Modify: `scripts/rag_inference_test.py:26-28,76-77`

- [ ] **Step 1: conftest.py の RAG_TEST_MODEL 更新**

```python
RAG_TEST_MODEL = "openai/Qwen3.5-27B-Q4_K_M.gguf"
```

- [ ] **Step 2: rag_inference_test.py の設定更新**

```python
MODEL = "openai/Qwen3.5-27B-Q4_K_M.gguf"
PDF_PATH = "data/filings/SEC/US_AAPL/2025/annual/10-K/0000320193-25-000079/converted.pdf"
BASE_URL = "http://localhost:8080/v1"
```

- [ ] **Step 3: rag_inference_test.py の phase1_build_index を更新**

`phase1_build_index()` 内の `page_index()` 呼び出し前に thinking 無効化を追加:

```python
    from pageindex import page_index
    from pageindex.utils import configure_max_tokens, configure_thinking

    configure_max_tokens(client.max_tokens)
    configure_thinking(False)  # PageIndex構築はnothinkモード
```

- [ ] **Step 4: 既存ユニットテスト全体の通過確認**

```bash
cd <repo-root> && python -m pytest tests/unit/ -v --tb=short
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add tests/conftest.py scripts/rag_inference_test.py
git commit -m "config: update test model to Qwen3.5-27B Q4_K_M"
```

---

## Task 8: 統合テスト (llama-server + Qwen3.5-27B)

**Files:**
- Modify: `tests/integration/test_llamacpp_server.py`

- [ ] **Step 1: llama-server を起動**

```bash
<llama-cpp-source>/build/bin/llama-server \
  -m ~/models/Qwen3.5-27B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -ngl 999 -c 32768 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  2>&1 | tee <log-dir>/llama_server.log &
```

ロード完了を待つ（`"all slots are idle"` メッセージ）。

- [ ] **Step 2: 統合テストを Qwen3.5 用に更新**

`tests/integration/test_llamacpp_server.py` のモデル名を更新し、nothinkモードのJSONテストを追加:

```python
"""Qwen3.5-27B + llama.cpp 統合テスト"""
import json
import pytest
import httpx

BASE_URL = "http://localhost:8080"
MODEL = "Qwen3.5-27B-Q4_K_M.gguf"


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=60)


def test_models_list(client):
    resp = client.get("/v1/models")
    assert resp.status_code == 200


def test_nothink_json_output(client):
    """nothinkモードで純粋なJSON出力を返すことを確認"""
    resp = client.post("/v1/chat/completions", json={
        "model": MODEL,
        "messages": [{"role": "user", "content": 'Return JSON: {"status": "ok"}'}],
        "max_tokens": 256,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    })
    assert resp.status_code == 200
    content = resp.json()["choices"][0]["message"]["content"]
    assert content is not None and len(content) > 0
    parsed = json.loads(content)
    assert isinstance(parsed, dict)
    # <think> タグが含まれていないことを確認
    assert "<think>" not in content


def test_think_mode_produces_reasoning(client):
    """thinkモードで推論トークンが生成されることを確認"""
    resp = client.post("/v1/chat/completions", json={
        "model": MODEL,
        "messages": [{"role": "user", "content": "What is 15 * 37?"}],
        "max_tokens": 1024,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": True},
    })
    assert resp.status_code == 200
    content = resp.json()["choices"][0]["message"]["content"]
    assert content is not None and len(content) > 0
    # 回答に 555 が含まれることを確認
    assert "555" in content


def test_json_toc_extraction(client):
    """PageIndexの典型的なTOC抽出タスクをシミュレート"""
    prompt = """Task: Transform the table of contents into structured JSON.

Rules:
- "structure": hierarchical index as string
- "title": exact section title
- "page": page number as integer, or null

Table of contents:
1. Business Overview ........... 5
  1.1 Products and Services .... 8
  1.2 Competition .............. 12
2. Risk Factors ................ 15

Return JSON:
{"table_of_contents": [{"structure": "1", "title": "...", "page": ...}, ...]}"""

    resp = client.post("/v1/chat/completions", json={
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    })
    assert resp.status_code == 200
    content = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    toc = parsed.get("table_of_contents", parsed.get("items", []))
    assert len(toc) >= 4
    assert toc[0]["page"] == 5 or toc[0]["page"] == "5"
```

- [ ] **Step 3: 統合テスト実行**

```bash
cd <repo-root> && python -m pytest tests/integration/test_llamacpp_server.py -v
```

Expected: 全テスト PASS。特に `test_nothink_json_output` で `<think>` タグなしのJSON出力を確認。

- [ ] **Step 4: コミット**

```bash
git add tests/integration/test_llamacpp_server.py
git commit -m "test: Qwen3.5-27B integration tests (nothink JSON + think reasoning)"
```

---

## Task 9: PageIndex RAG E2E テスト実行

**Files:**
- Run: `scripts/rag_inference_test.py`

- [ ] **Step 1: llama-server が起動中であることを確認**

```bash
curl -s http://localhost:8080/v1/models | python3 -m json.tool
```

- [ ] **Step 2: RAG推論テスト実行**

```bash
cd <repo-root> && PYTHONUNBUFFERED=1 python3 scripts/rag_inference_test.py 2>&1 | tee /tmp/rag_qwen35_test.log
```

**成功基準:**
- Phase 1 (Build Index): 完走。ノード数 > 0。
- Phase 2 (TOC Verify): accuracy > 50%（初回目標）
- Phase 3 (RAG Query): 3つの質問に回答生成

- [ ] **Step 3: 結果分析**

```bash
cat data/rag_inference_test_result.json | python3 -m json.tool
```

Phase 2 の accuracy が 80% 未満の場合、`/tmp/rag_qwen35_test.log` で失敗パターンを確認し、`max_tokens` 調整やプロンプト修正を検討。

- [ ] **Step 4: 結果をデバッグドキュメントに追記**

`docs/RAGtest_debug.md` に Phase C (Qwen3.5-27B) セクションを追加し、結果を記録。

---

## Dependency Graph

```
Task 1 (llama.cpp rebuild)
Task 2 (download model) ──────┐
                               ├── Task 3 (PageIndex utils.py) ─┐
Task 4 (settings.yaml) ───────┤                                 │
                               │                                 ├── Task 8 (integration test)
Task 5 (LlmClient) ───────────┤                                 │
                               ├── Task 6 (PageIndexService) ────┤
Task 7 (conftest + script) ────┘                                 └── Task 9 (E2E test)
```

Tasks 1-2 はインフラ準備（並行可能）。Tasks 3-7 はコード変更（3と5は並行可能、6は5に依存）。Tasks 8-9 は統合検証。
