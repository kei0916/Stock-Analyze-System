# Phase 6: LLM/RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete RAG pipeline that converts SEC/EDINET filing HTML to PDF, builds PageIndex tree indices via local Ollama LLM, runs 4 structured analysis types + free Q&A, and exposes everything through the `rag` CLI subcommands.

**Architecture:** HTML filings → weasyprint PDF conversion → PageIndex tree index (via litellm/Ollama) → RAG query engine (tree search + LLM reasoning) → structured JSON results → DB persistence. All LLM calls go through litellm with Ollama backend, using Q8_0 for batch/indexing (speed) and UD-Q8_K_XL for interactive Q&A (quality). `asyncio.Semaphore(1)` enforces sequential index building.

**Tech Stack:** litellm 1.82+, weasyprint 68+, pymupdf 1.27+, PageIndex (git install), Ollama (Qwen3.5-27B), SQLAlchemy async, asyncio

---

## Pre-requisite: PageIndex Installation

PageIndex is not on PyPI. Install from source before starting:

```bash
pip install git+https://github.com/VectifyAI/PageIndex.git
```

If that fails, clone and install locally:

```bash
cd /tmp && git clone https://github.com/VectifyAI/PageIndex.git
cd PageIndex && pip install -e .
```

Verify: `python -c "from pageindex import page_index; print('OK')"`

---

## Config Model Identifier Update

The config currently uses HuggingFace paths (`ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:Q8_0`) but the Ollama library model is `qwen3.5:27b-q8_0`. The litellm model identifier for Ollama library models is `ollama/qwen3.5:27b-q8_0`.

For `model_quality` (UD-Q8_K_XL): This quantization is only available via HuggingFace, so it stays as `ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:UD-Q8_K_XL`. Ensure it's pulled: `ollama pull hf.co/unsloth/Qwen3.5-27B-GGUF:UD-Q8_K_XL`.

---

## File Structure

| File | Responsibility | Status |
|------|---------------|--------|
| `src/stock_analyze_system/config.py` | Update LlmConfig model identifiers | Modify |
| `src/stock_analyze_system/services/llm_client.py` | Thin async litellm wrapper with model selection, timeout, retry | Create |
| `src/stock_analyze_system/services/pdf_converter.py` | HTML→PDF via weasyprint (asyncio.to_thread) | Create |
| `src/stock_analyze_system/services/pageindex_service.py` | PageIndex tree build + query with semaphore | Create |
| `src/stock_analyze_system/services/prompts.py` | 4 analysis type prompt templates | Create |
| `src/stock_analyze_system/services/rag_service.py` | RAG orchestration: analysis, Q&A, health check | Create |
| `src/stock_analyze_system/cli/rag.py` | Full rag CLI handlers (replace stub) | Modify |
| `src/stock_analyze_system/cli/helpers.py` | Wire RagService into ServiceContainer + setup_services | Modify |
| `src/stock_analyze_system/models/company_analysis.py` | Widen model_name column String(50)→String(100) | Modify |
| `src/stock_analyze_system/models/document_index.py` | Widen model_name column String(50)→String(100) | Modify |
| `tests/unit/services/test_llm_client.py` | LlmClient unit tests | Create |
| `tests/unit/services/test_pdf_converter.py` | PdfConverter unit tests | Create |
| `tests/unit/services/test_pageindex_service.py` | PageIndexService unit tests | Create |
| `tests/unit/services/test_rag_service.py` | RagService unit tests | Create |
| `tests/unit/cli/test_rag_cli.py` | RAG CLI handler tests | Create |

**Spec Deviations (intentional improvements):**
- `PageIndexService.__init__` takes `llm_client` as a 4th parameter (spec has 3). This enables proper model resolution without coupling to config.
- `LlmClient` is a new class not in the spec. It consolidates litellm interaction, model selection, and health checks into a single testable unit.
- Default `model` in `LlmConfig` changed from HuggingFace path to Ollama library format (`ollama/qwen3.5:27b-q8_0`). Reason: Ollama v0.17.4 couldn't load HF GGUFs (qwen35 architecture unsupported); the Ollama library model works with v0.18.2.
- `model_name` column widened from `String(50)` to `String(100)` to accommodate long HuggingFace model identifiers (the quality model ID is 48 chars, leaving no headroom).

---

## Common Patterns

### LLM Call Pattern (all LLM calls use this)

```python
from stock_analyze_system.services.llm_client import LlmClient

client = LlmClient(config.llm)
response = await client.completion(
    prompt="...",
    quality=False,  # True for interactive Q&A
)
```

### Service Injection Pattern

```python
class SomeService:
    def __init__(self, dep_repo: SomeRepository):
        self._repo = dep_repo
```

### Test Pattern (mock LLM calls, never hit real Ollama)

```python
@pytest.fixture
def llm_client():
    client = AsyncMock(spec=LlmClient)
    client.completion.return_value = '{"key": "value"}'
    return client
```

---

## Task 1: LlmClient — litellm Async Wrapper

**Files:**
- Create: `src/stock_analyze_system/services/llm_client.py`
- Test: `tests/unit/services/test_llm_client.py`

- [ ] **Step 1: Write failing tests for LlmClient**

```python
# tests/unit/services/test_llm_client.py
"""LlmClient単体テスト"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from stock_analyze_system.config import LlmConfig
from stock_analyze_system.services.llm_client import LlmClient


class TestResolveModel:
    def test_default_speed_model(self):
        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        assert client.resolve_model(quality=False) == "ollama/qwen3.5:27b-q8_0"

    def test_quality_model(self):
        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            model_quality="ollama/qwen3.5:27b-ud-q8_k_xl",
        )
        client = LlmClient(config)
        assert client.resolve_model(quality=True) == "ollama/qwen3.5:27b-ud-q8_k_xl"

    def test_quality_fallback_when_empty(self):
        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0", model_quality="")
        client = LlmClient(config)
        assert client.resolve_model(quality=True) == "ollama/qwen3.5:27b-q8_0"

    def test_explicit_model_override(self):
        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        assert client.resolve_model(model="ollama/custom:latest") == "ollama/custom:latest"


class TestCompletion:
    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_calls_litellm(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "test response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            base_url="http://localhost:11434",
            temperature=0.1,
            max_tokens=4096,
            request_timeout=300,
        )
        client = LlmClient(config)
        result = await client.completion("What is 1+1?")

        assert result == "test response"
        mock_litellm.acompletion.assert_called_once()
        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "ollama/qwen3.5:27b-q8_0"
        assert call_kwargs["timeout"] == 300

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_with_quality(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "quality response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            model_quality="ollama/qwen3.5:27b-ud-q8_k_xl",
        )
        client = LlmClient(config)
        result = await client.completion("question", quality=True)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "ollama/qwen3.5:27b-ud-q8_k_xl"

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_with_system_prompt(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        await client.completion("question", system="You are an analyst.")

        call_kwargs = mock_litellm.acompletion.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestHealthCheck:
    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_health_check_ok(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        result = await client.health_check()
        assert result["status"] == "ok"

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_health_check_fail(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(side_effect=Exception("connection refused"))

        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        result = await client.health_check()
        assert result["status"] == "error"
        assert "connection refused" in result["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/services/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_analyze_system.services.llm_client'`

- [ ] **Step 3: Write LlmClient implementation**

```python
# src/stock_analyze_system/services/llm_client.py
"""litellm非同期ラッパー — モデル選択・タイムアウト・ヘルスチェック"""
from __future__ import annotations

import litellm
from stock_analyze_system.config import LlmConfig


class LlmClient:
    """litellm経由の非同期LLMクライアント"""

    def __init__(self, config: LlmConfig):
        self._config = config

    def resolve_model(
        self, *, quality: bool = False, model: str | None = None,
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/services/test_llm_client.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/llm_client.py tests/unit/services/test_llm_client.py
git commit -m "feat: add LlmClient async litellm wrapper with model selection"
```

---

## Task 2: PdfConverter — HTML→PDF Conversion

**Files:**
- Create: `src/stock_analyze_system/services/pdf_converter.py`
- Test: `tests/unit/services/test_pdf_converter.py`

- [ ] **Step 1: Write failing tests for PdfConverter**

```python
# tests/unit/services/test_pdf_converter.py
"""PdfConverter単体テスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stock_analyze_system.services.pdf_converter import PdfConverter


class TestConvert:
    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_convert_creates_pdf(self, mock_wp, mock_asyncio, tmp_path):
        html_path = tmp_path / "test.html"
        html_path.write_text("<html><body>Hello</body></html>")
        output_path = tmp_path / "output.pdf"

        # Mock asyncio.to_thread to call the function directly
        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_asyncio.to_thread = fake_to_thread
        mock_doc = MagicMock()
        mock_wp.HTML.return_value = mock_doc

        converter = PdfConverter()
        result = await converter.convert(html_path, output_path)

        assert result == output_path
        mock_wp.HTML.assert_called_once_with(filename=str(html_path))
        mock_doc.write_pdf.assert_called_once_with(str(output_path))


class TestGetOrConvert:
    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_skip_if_pdf_exists(self, mock_wp, mock_asyncio, tmp_path):
        pdf_path = tmp_path / "converted.pdf"
        pdf_path.write_text("fake pdf")

        filing = MagicMock()
        filing.storage_path = str(tmp_path)

        converter = PdfConverter()
        result = await converter.get_or_convert(filing)

        assert result == pdf_path
        mock_wp.HTML.assert_not_called()

    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_converts_when_no_pdf(self, mock_wp, mock_asyncio, tmp_path):
        html_dir = tmp_path / "raw"
        html_dir.mkdir()
        html_file = html_dir / "filing.html"
        html_file.write_text("<html>test</html>")

        filing = MagicMock()
        filing.storage_path = str(tmp_path)

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_asyncio.to_thread = fake_to_thread
        mock_doc = MagicMock()
        mock_wp.HTML.return_value = mock_doc

        converter = PdfConverter()
        result = await converter.get_or_convert(filing)

        assert result == tmp_path / "converted.pdf"
        mock_wp.HTML.assert_called_once()

    async def test_raises_when_no_html(self, tmp_path):
        filing = MagicMock()
        filing.storage_path = str(tmp_path)

        converter = PdfConverter()
        with pytest.raises(FileNotFoundError):
            await converter.get_or_convert(filing)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/services/test_pdf_converter.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write PdfConverter implementation**

```python
# src/stock_analyze_system/services/pdf_converter.py
"""HTML→PDF変換 (weasyprint, asyncio.to_thread)"""
from __future__ import annotations

import asyncio
from pathlib import Path

import weasyprint


class PdfConverter:
    """SEC/EDINETファイリングHTMLをPDFに変換する"""

    async def convert(self, html_path: Path, output_path: Path) -> Path:
        """HTMLファイルをPDFに変換する"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def _convert() -> None:
            doc = weasyprint.HTML(filename=str(html_path))
            doc.write_pdf(str(output_path))

        await asyncio.to_thread(_convert)
        return output_path

    async def get_or_convert(self, filing) -> Path:
        """変換済みPDFがあればそれを返し、なければHTML→PDF変換する"""
        base = Path(filing.storage_path)
        pdf_path = base / "converted.pdf"

        if pdf_path.exists():
            return pdf_path

        # raw/ ディレクトリからHTMLファイルを探す
        raw_dir = base / "raw"
        html_files = list(raw_dir.glob("*.html")) if raw_dir.exists() else []
        if not html_files:
            # base直下のHTMLも探す
            html_files = list(base.glob("*.html"))
        if not html_files:
            raise FileNotFoundError(
                f"No HTML files found for filing at {base}"
            )

        return await self.convert(html_files[0], pdf_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/services/test_pdf_converter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/pdf_converter.py tests/unit/services/test_pdf_converter.py
git commit -m "feat: add PdfConverter for HTML-to-PDF filing conversion"
```

---

## Task 3: PageIndexService — Tree Index Build + Query

**Files:**
- Create: `src/stock_analyze_system/services/pageindex_service.py`
- Test: `tests/unit/services/test_pageindex_service.py`

**Dependencies:** PageIndex must be installed (see Pre-requisite section).

- [ ] **Step 1: Write failing tests for PageIndexService**

```python
# tests/unit/services/test_pageindex_service.py
"""PageIndexService単体テスト"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stock_analyze_system.config import LlmConfig, PageIndexConfig
from stock_analyze_system.services.pageindex_service import (
    PageIndexService,
    QueryResult,
)


@pytest.fixture
def llm_client():
    client = AsyncMock()
    client.resolve_model.return_value = "ollama/qwen3.5:27b-q8_0"
    return client


@pytest.fixture
def doc_index_repo():
    return AsyncMock()


@pytest.fixture
def pdf_converter():
    return AsyncMock()


@pytest.fixture
def pageindex_config():
    return PageIndexConfig(
        enabled=True,
        toc_check_pages=20,
        max_pages_per_node=10,
        max_tokens_per_node=20000,
        add_node_summary=True,
        cache_indices=True,
    )


@pytest.fixture
def service(doc_index_repo, pdf_converter, llm_client, pageindex_config):
    return PageIndexService(
        doc_index_repo=doc_index_repo,
        pdf_converter=pdf_converter,
        llm_client=llm_client,
        config=pageindex_config,
    )


class TestBuildIndex:
    @patch("stock_analyze_system.services.pageindex_service.page_index")
    async def test_build_index_returns_tree(self, mock_pi, service):
        tree = {"title": "Doc", "nodes": [{"title": "Section 1", "id": "1"}]}
        mock_pi.return_value = tree

        result = await service.build_index(Path("/fake/doc.pdf"))

        assert result == tree
        mock_pi.assert_called_once()

    @patch("stock_analyze_system.services.pageindex_service.page_index")
    async def test_build_index_passes_config(self, mock_pi, service):
        mock_pi.return_value = {"title": "Doc"}

        await service.build_index(Path("/fake/doc.pdf"))

        call_kwargs = mock_pi.call_args
        # page_index receives pdf path and model config
        assert call_kwargs is not None


class TestGetOrCreateIndex:
    async def test_returns_cached_index(self, service, doc_index_repo):
        cached = MagicMock()
        cached.index_json = json.dumps({"title": "Cached"})
        doc_index_repo.get_by_filing.return_value = cached

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"

        result = await service.get_or_create_index(filing)
        assert result["title"] == "Cached"
        doc_index_repo.get_by_filing.assert_called_once_with(1)

    @patch("stock_analyze_system.services.pageindex_service.page_index")
    async def test_builds_and_caches_new_index(
        self, mock_pi, service, doc_index_repo, pdf_converter,
    ):
        doc_index_repo.get_by_filing.return_value = None
        tree = {"title": "New", "nodes": [{"id": "1", "title": "S1"}]}
        mock_pi.return_value = tree
        pdf_converter.get_or_convert.return_value = Path("/fake/doc.pdf")

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"

        result = await service.get_or_create_index(filing)
        assert result["title"] == "New"
        doc_index_repo.save_index.assert_called_once()


class TestQuery:
    async def test_query_returns_result(self, service, llm_client):
        tree = {
            "title": "Doc",
            "nodes": [
                {"id": "1", "title": "Revenue", "text": "Revenue was $100B"},
            ],
        }
        # First LLM call: find relevant nodes
        # Second LLM call: generate answer
        llm_client.completion.side_effect = [
            json.dumps({"node_list": ["1"], "thinking": "Revenue section"}),
            "Revenue was $100B in FY2025.",
        ]

        result = await service.query(
            tree, "What was the revenue?", Path("/fake/doc.pdf"),
        )

        assert isinstance(result, QueryResult)
        assert "100B" in result.answer
        assert result.source_sections == ["Revenue"]


class TestQueryResult:
    def test_to_dict(self):
        qr = QueryResult(
            answer="test",
            source_pages=[1, 2],
            source_sections=["Intro"],
            confidence=0.95,
            model="ollama/qwen3.5:27b-q8_0",
        )
        d = qr.to_dict()
        assert d["answer"] == "test"
        assert d["source_pages"] == [1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/services/test_pageindex_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write PageIndexService implementation**

```python
# src/stock_analyze_system/services/pageindex_service.py
"""PageIndex統合 — ツリーインデックス構築・クエリ"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from stock_analyze_system.config import PageIndexConfig

logger = logging.getLogger(__name__)

# インデックス構築の同時実行を1に制限（GPU競合防止）
_build_semaphore = asyncio.Semaphore(1)


@dataclass
class QueryResult:
    """RAGクエリ結果"""
    answer: str
    source_pages: list[int]
    source_sections: list[str]
    confidence: float
    model: str

    def to_dict(self) -> dict:
        return asdict(self)


def _count_nodes(tree: dict) -> int:
    """ツリー内のノード数を再帰カウントする"""
    count = 1
    for child in tree.get("nodes", []):
        count += _count_nodes(child)
    return count


def _collect_node_map(tree: dict) -> dict[str, dict]:
    """ノードIDからノード情報へのマッピングを構築する"""
    mapping: dict[str, dict] = {}
    if "id" in tree:
        mapping[tree["id"]] = tree
    for child in tree.get("nodes", []):
        mapping.update(_collect_node_map(child))
    return mapping


class PageIndexService:
    """PageIndexツリーインデックスの構築とクエリ"""

    def __init__(
        self,
        doc_index_repo,
        pdf_converter,
        llm_client,
        config: PageIndexConfig,
    ):
        self._repo = doc_index_repo
        self._pdf_converter = pdf_converter
        self._llm_client = llm_client
        self._config = config

    async def build_index(self, pdf_path: Path) -> dict:
        """PDFからPageIndexツリーインデックスを構築する"""
        from pageindex import page_index  # lazy import: PageIndex未インストール時もアプリ起動可能

        model = self._llm_client.resolve_model(quality=False)
        logger.info("Building PageIndex for %s with model %s", pdf_path, model)

        async with _build_semaphore:
            tree = await asyncio.to_thread(
                page_index,
                str(pdf_path),
                model=model,
                toc_check_page_num=self._config.toc_check_pages,
                max_page_num_each_node=self._config.max_pages_per_node,
                max_token_num_each_node=self._config.max_tokens_per_node,
                if_add_node_summary=self._config.add_node_summary,
                if_add_node_text=self._config.add_node_text,
            )

        logger.info("PageIndex built: %d nodes", _count_nodes(tree))
        return tree

    async def get_or_create_index(self, filing) -> dict:
        """キャッシュ済みインデックスを返すか、なければ構築・保存する"""
        if self._config.cache_indices:
            cached = await self._repo.get_by_filing(filing.id)
            if cached is not None:
                logger.info("Using cached index for filing %d", filing.id)
                return json.loads(cached.index_json)

        pdf_path = await self._pdf_converter.get_or_convert(filing)
        tree = await self.build_index(pdf_path)

        # DBに保存
        model = self._llm_client.resolve_model(quality=False)
        await self._repo.save_index(
            filing_id=filing.id,
            company_id=filing.company_id,
            data={
                "index_json": json.dumps(tree, ensure_ascii=False),
                "model_name": model,
                "page_count": tree.get("page_count", 0),
                "node_count": _count_nodes(tree),
            },
        )

        return tree

    async def query(
        self, tree: dict, question: str, pdf_path: Path,
    ) -> QueryResult:
        """ツリーインデックスに対してRAGクエリを実行する"""
        model = self._llm_client.resolve_model(quality=True)
        node_map = _collect_node_map(tree)

        # Step 1: ツリー検索 — 関連ノードを特定
        tree_summary = json.dumps(
            _strip_text(tree), indent=2, ensure_ascii=False,
        )
        search_prompt = (
            f"以下のドキュメントツリー構造から、質問に回答するために必要なノードを特定してください。\n\n"
            f"質問: {question}\n\n"
            f"ドキュメントツリー:\n{tree_summary}\n\n"
            f"JSON形式で回答してください: "
            f'{{"thinking": "理由", "node_list": ["ノードID1", "ノードID2"]}}'
        )
        search_result = await self._llm_client.completion(
            search_prompt, quality=True, model=model,
        )

        try:
            parsed = json.loads(search_result)
            node_ids = parsed.get("node_list", [])
        except json.JSONDecodeError:
            logger.warning("Failed to parse tree search result, using all nodes")
            node_ids = list(node_map.keys())[:5]

        # Step 2: ノードテキスト抽出
        sections = []
        pages = []
        context_parts = []
        for nid in node_ids:
            node = node_map.get(nid)
            if node is None:
                continue
            sections.append(node.get("title", nid))
            if "physical_index" in node:
                pages.append(node["physical_index"])
            text = node.get("text", node.get("summary", ""))
            if text:
                context_parts.append(f"[{node.get('title', nid)}]\n{text}")

        context = "\n\n".join(context_parts)

        # Step 3: 回答生成
        answer_prompt = (
            f"以下のコンテキストに基づいて質問に日本語で回答してください。\n\n"
            f"質問: {question}\n\n"
            f"コンテキスト:\n{context}"
        )
        answer = await self._llm_client.completion(
            answer_prompt, quality=True, model=model,
        )

        return QueryResult(
            answer=answer,
            source_pages=sorted(set(pages)),
            source_sections=sections,
            confidence=min(1.0, len(node_ids) * 0.3) if node_ids else 0.0,
            model=model,
        )


    async def get_indices_for_company(self, company_id: str) -> list:
        """企業のインデックス一覧を返す"""
        return await self._repo.list_all(company_id=company_id)


def _strip_text(tree: dict) -> dict:
    """ツリーからtextフィールドを除去し構造だけ返す（検索用）"""
    result = {k: v for k, v in tree.items() if k not in ("text",)}
    if "nodes" in result:
        result["nodes"] = [_strip_text(n) for n in result["nodes"]]
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/services/test_pageindex_service.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/pageindex_service.py tests/unit/services/test_pageindex_service.py
git commit -m "feat: add PageIndexService for tree index build and RAG query"
```

---

## Task 4: Analysis Prompts — 4 Structured Analysis Types

**Files:**
- Create: `src/stock_analyze_system/services/prompts.py`

- [ ] **Step 1: Write prompts module**

No dedicated test needed — prompts are pure data (string templates). They will be tested through RagService tests.

```python
# src/stock_analyze_system/services/prompts.py
"""RAG定型分析プロンプトテンプレート"""
from __future__ import annotations

ANALYSIS_TYPES: dict[str, dict[str, str]] = {
    "business_summary": {
        "label": "事業概要",
        "prompt": (
            "この企業の有価証券報告書/10-K/20-Fに基づき、事業概要を日本語で構造化してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "company_name": "企業名",\n'
            '  "industry": "業種",\n'
            '  "business_segments": [\n'
            '    {"name": "セグメント名", "description": "概要", "revenue_share": "売上比率"}\n'
            "  ],\n"
            '  "key_products": ["主要製品/サービス"],\n'
            '  "geographic_presence": ["主要展開地域"],\n'
            '  "employees": "従業員数",\n'
            '  "summary": "200字程度の事業概要"\n'
            "}"
        ),
    },
    "risk_factors": {
        "label": "リスク要因",
        "prompt": (
            "この企業の有価証券報告書/10-Kに記載されているリスク要因を分析してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "risks": [\n'
            "    {\n"
            '      "category": "カテゴリ（市場/規制/技術/財務/オペレーション）",\n'
            '      "title": "リスク名",\n'
            '      "description": "概要",\n'
            '      "severity": "high/medium/low"\n'
            "    }\n"
            "  ],\n"
            '  "top_risks_summary": "最も重要なリスク3つの要約"\n'
            "}"
        ),
    },
    "mda": {
        "label": "経営者による分析 (MD&A)",
        "prompt": (
            "経営者による財政状態及び経営成績の分析（MD&A）セクションを要約してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "revenue_analysis": "売上高の動向と要因分析",\n'
            '  "profitability": "利益率の動向",\n'
            '  "cash_flow": "キャッシュフローの状況",\n'
            '  "capital_allocation": "資本配分方針",\n'
            '  "outlook": "業績見通し",\n'
            '  "key_metrics": [\n'
            '    {"metric": "指標名", "current": "当期", "previous": "前期", "change": "変化率"}\n'
            "  ],\n"
            '  "summary": "200字程度のMD&A要約"\n'
            "}"
        ),
    },
    "competitors": {
        "label": "競合分析",
        "prompt": (
            "この企業の競合環境を有価証券報告書/10-Kの記載に基づいて分析してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "competitive_position": "競合ポジション",\n'
            '  "market_share": "市場シェア（記載があれば）",\n'
            '  "competitors": [\n'
            '    {"name": "競合企業名", "description": "概要"}\n'
            "  ],\n"
            '  "competitive_advantages": ["競合優位性"],\n'
            '  "competitive_risks": ["競合上のリスク"],\n'
            '  "summary": "200字程度の競合分析要約"\n'
            "}"
        ),
    },
}

ANALYSIS_TYPE_NAMES = list(ANALYSIS_TYPES.keys())
```

- [ ] **Step 2: Commit**

```bash
git add src/stock_analyze_system/services/prompts.py
git commit -m "feat: add structured analysis prompt templates (4 types)"
```

---

## Task 5: RagService — Analysis Orchestration

**Files:**
- Create: `src/stock_analyze_system/services/rag_service.py`
- Test: `tests/unit/services/test_rag_service.py`

- [ ] **Step 1: Write failing tests for RagService**

```python
# tests/unit/services/test_rag_service.py
"""RagService単体テスト"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.services.pageindex_service import QueryResult
from stock_analyze_system.services.rag_service import AnalysisResult, RagService


@pytest.fixture
def pageindex_service():
    svc = AsyncMock()
    svc.query.return_value = QueryResult(
        answer='{"summary": "test"}',
        source_pages=[1, 2],
        source_sections=["Section 1"],
        confidence=0.9,
        model="ollama/qwen3.5:27b-q8_0",
    )
    return svc


@pytest.fixture
def analysis_repo():
    repo = AsyncMock()
    repo.get_by_type.return_value = None
    return repo


@pytest.fixture
def filing_repo():
    repo = AsyncMock()
    filing = MagicMock()
    filing.id = 1
    filing.company_id = "US_AAPL"
    filing.storage_path = "/data/filings/sec/US_AAPL/2025"
    repo.get_by_id.return_value = filing
    return repo


@pytest.fixture
def llm_client():
    client = AsyncMock()
    client.health_check.return_value = {"status": "ok", "model": "test", "backend": "ollama", "base_url": "http://localhost:11434"}
    return client


@pytest.fixture
def service(pageindex_service, analysis_repo, filing_repo, llm_client):
    return RagService(
        pageindex_service=pageindex_service,
        analysis_repo=analysis_repo,
        filing_repo=filing_repo,
        llm_client=llm_client,
    )


class TestRunAnalysis:
    async def test_runs_single_analysis(self, service, pageindex_service):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"

        result = await service.run_analysis(filing, "business_summary")

        assert isinstance(result, AnalysisResult)
        assert result.analysis_type == "business_summary"
        pageindex_service.get_or_create_index.assert_called_once()
        pageindex_service.query.assert_called_once()

    async def test_unknown_analysis_type_raises(self, service):
        filing = MagicMock()
        with pytest.raises(ValueError, match="Unknown analysis type"):
            await service.run_analysis(filing, "nonexistent")


class TestRunFullAnalysis:
    async def test_runs_all_4_types(self, service, pageindex_service):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"

        results = await service.run_full_analysis(filing)

        assert len(results) == 4
        types = {r.analysis_type for r in results}
        assert types == {"business_summary", "risk_factors", "mda", "competitors"}

    async def test_returns_cached_analysis(
        self, service, analysis_repo, pageindex_service,
    ):
        cached = MagicMock()
        cached.analysis_type = "business_summary"
        cached.result_json = '{"summary": "cached"}'
        analysis_repo.get_by_type.return_value = cached

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"

        results = await service.run_full_analysis(filing)
        # All 4 types attempted, but business_summary uses cache
        assert len(results) == 4


class TestAskQuestion:
    async def test_ask_returns_query_result(self, service, pageindex_service):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"

        result = await service.ask_question(filing, "What is the revenue?")

        assert isinstance(result, QueryResult)
        assert result.answer == '{"summary": "test"}'
        pageindex_service.get_or_create_index.assert_called_once()
        pageindex_service.query.assert_called_once()


class TestHealthCheck:
    async def test_health_delegates_to_llm_client(self, service, llm_client):
        result = await service.health_check()
        assert result["status"] == "ok"
        llm_client.health_check.assert_called_once()


class TestAnalysisResult:
    def test_to_dict(self):
        qr = QueryResult(
            answer="test", source_pages=[1], source_sections=["S1"],
            confidence=0.9, model="m",
        )
        ar = AnalysisResult(
            analysis_type="business_summary", result_json={"key": "val"},
            query_result=qr,
        )
        d = ar.to_dict()
        assert d["analysis_type"] == "business_summary"
        assert d["result_json"] == {"key": "val"}
        assert d["query_result"]["answer"] == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/services/test_rag_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write RagService implementation**

```python
# src/stock_analyze_system/services/rag_service.py
"""RAGサービス — 定型分析・自由質問のオーケストレーション"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from stock_analyze_system.services.pageindex_service import QueryResult
from stock_analyze_system.services.prompts import ANALYSIS_TYPES, ANALYSIS_TYPE_NAMES

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """定型分析結果"""
    analysis_type: str
    result_json: dict
    query_result: QueryResult

    def to_dict(self) -> dict:
        return {
            "analysis_type": self.analysis_type,
            "result_json": self.result_json,
            "query_result": self.query_result.to_dict(),
        }


class RagService:
    """RAG分析オーケストレーション"""

    def __init__(self, pageindex_service, analysis_repo, filing_repo, llm_client):
        self._pageindex = pageindex_service
        self._analysis_repo = analysis_repo
        self._filing_repo = filing_repo
        self._llm_client = llm_client

    async def health_check(self) -> dict:
        """LLMヘルスチェックを委譲する"""
        return await self._llm_client.health_check()

    async def build_index(self, filing) -> dict:
        """インデックスを構築または取得する"""
        return await self._pageindex.get_or_create_index(filing)

    async def run_analysis(
        self, filing, analysis_type: str,
    ) -> AnalysisResult:
        """単一の定型分析を実行する"""
        if analysis_type not in ANALYSIS_TYPES:
            raise ValueError(
                f"Unknown analysis type: {analysis_type}. "
                f"Valid types: {ANALYSIS_TYPE_NAMES}"
            )

        spec = ANALYSIS_TYPES[analysis_type]
        logger.info(
            "Running %s analysis for filing %d", analysis_type, filing.id,
        )

        tree = await self._pageindex.get_or_create_index(filing)
        pdf_path = Path(filing.storage_path) / "converted.pdf"

        qr = await self._pageindex.query(tree, spec["prompt"], pdf_path)

        # 回答をJSON解析（失敗時はrawテキストを格納）
        try:
            result_json = json.loads(qr.answer)
        except json.JSONDecodeError:
            result_json = {"raw_answer": qr.answer}

        # DB保存
        model = qr.model
        await self._analysis_repo.upsert(
            {"company_id": filing.company_id, "filing_id": filing.id,
             "analysis_type": analysis_type},
            {"result_json": json.dumps(result_json, ensure_ascii=False),
             "model_name": model},
        )

        return AnalysisResult(
            analysis_type=analysis_type,
            result_json=result_json,
            query_result=qr,
        )

    async def run_full_analysis(self, filing) -> list[AnalysisResult]:
        """全4タイプの定型分析を逐次実行する"""
        # インデックスを1回だけ取得（4回の重複回避）
        tree = await self._pageindex.get_or_create_index(filing)
        pdf_path = Path(filing.storage_path) / "converted.pdf"

        results: list[AnalysisResult] = []
        for atype in ANALYSIS_TYPE_NAMES:
            # キャッシュチェック
            cached = await self._analysis_repo.get_by_type(
                filing.company_id, filing.id, atype,
            )
            if cached is not None:
                logger.info("Using cached %s analysis for filing %d", atype, filing.id)
                qr = QueryResult(
                    answer=cached.result_json,
                    source_pages=[], source_sections=[],
                    confidence=1.0, model=cached.model_name,
                )
                results.append(AnalysisResult(
                    analysis_type=atype,
                    result_json=json.loads(cached.result_json),
                    query_result=qr,
                ))
                continue

            # 事前取得済みtreeを使ってクエリ実行
            spec = ANALYSIS_TYPES[atype]
            logger.info("Running %s analysis for filing %d", atype, filing.id)
            qr = await self._pageindex.query(tree, spec["prompt"], pdf_path)

            try:
                result_json = json.loads(qr.answer)
            except json.JSONDecodeError:
                result_json = {"raw_answer": qr.answer}

            await self._analysis_repo.upsert(
                {"company_id": filing.company_id, "filing_id": filing.id,
                 "analysis_type": atype},
                {"result_json": json.dumps(result_json, ensure_ascii=False),
                 "model_name": qr.model},
            )
            results.append(AnalysisResult(
                analysis_type=atype, result_json=result_json, query_result=qr,
            ))

        return results

    async def ask_question(self, filing, question: str) -> QueryResult:
        """自由質問を実行する"""
        logger.info("RAG Q&A for filing %d: %s", filing.id, question[:50])

        tree = await self._pageindex.get_or_create_index(filing)
        pdf_path = Path(filing.storage_path) / "converted.pdf"

        return await self._pageindex.query(tree, question, pdf_path)

    async def ask_questions(
        self, filing, questions: list[str],
    ) -> list[QueryResult]:
        """複数質問を逐次実行する"""
        results: list[QueryResult] = []
        for q in questions:
            result = await self.ask_question(filing, q)
            results.append(result)
        return results

    async def get_index_status(self, company_id: str) -> list[dict]:
        """企業のインデックス構築状態を返す"""
        indices = await self._pageindex.get_indices_for_company(company_id)
        return [
            {
                "filing_id": idx.filing_id,
                "model_name": idx.model_name,
                "page_count": idx.page_count,
                "node_count": idx.node_count,
                "created_at": str(idx.created_at),
            }
            for idx in indices
        ]

    async def get_analyses(
        self, company_id: str, filing_id: int,
    ) -> list[dict]:
        """保存済み分析結果を返す"""
        analyses = await self._analysis_repo.get_analyses(company_id, filing_id)
        return [
            {
                "analysis_type": a.analysis_type,
                "result_json": json.loads(a.result_json),
                "model_name": a.model_name,
                "created_at": str(a.created_at),
            }
            for a in analyses
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/services/test_rag_service.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/services/rag_service.py tests/unit/services/test_rag_service.py
git commit -m "feat: add RagService for analysis orchestration and Q&A"
```

---

## Task 6: CLI rag Handlers — Replace Stub

**Files:**
- Modify: `src/stock_analyze_system/cli/rag.py`
- Test: `tests/unit/cli/test_rag_cli.py`

- [ ] **Step 1: Write failing tests for rag CLI**

```python
# tests/unit/cli/test_rag_cli.py
"""RAG CLIハンドラテスト"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli.rag import handle
from stock_analyze_system.services.pageindex_service import QueryResult
from stock_analyze_system.services.rag_service import AnalysisResult


@pytest.fixture
def services():
    svc = MagicMock()
    svc.rag_service = AsyncMock()
    svc.filing_service = AsyncMock()
    svc.company_service = AsyncMock()

    company = MagicMock()
    company.id = "US_AAPL"
    company.name = "Apple Inc."
    svc.company_service.get_company.return_value = company

    filing = MagicMock()
    filing.id = 1
    filing.company_id = "US_AAPL"
    filing.storage_path = "/data/filings/sec/US_AAPL/2025"
    svc.filing_service.get_latest_filing.return_value = filing

    return svc


def make_args(**kwargs):
    args = MagicMock()
    args.json = False
    args.quality = False
    args.model = None
    for k, v in kwargs.items():
        setattr(args, k, v)
    return args


class TestRagHealth:
    async def test_health_ok(self, services, capsys):
        services.rag_service.health_check.return_value = {
            "status": "ok", "model": "test", "backend": "ollama",
            "base_url": "http://localhost:11434",
        }
        args = make_args(action="health")
        await handle(args, services)

        captured = capsys.readouterr()
        assert "ok" in captured.out
        services.rag_service.health_check.assert_called_once()


class TestRagIndex:
    async def test_index_builds(self, services, capsys):
        tree = {"title": "Doc", "nodes": [], "node_count": 5}
        services.rag_service.build_index.return_value = tree

        args = make_args(action="index", company_id="US_AAPL")
        await handle(args, services)

        services.rag_service.build_index.assert_called_once()
        captured = capsys.readouterr()
        assert "5 nodes" in captured.out


class TestRagAnalyze:
    async def test_analyze_runs_all(self, services, capsys):
        qr = QueryResult(
            answer="test", source_pages=[1], source_sections=["S1"],
            confidence=0.9, model="m",
        )
        results = [
            AnalysisResult("business_summary", {"summary": "test"}, qr),
        ]
        services.rag_service.run_full_analysis.return_value = results

        args = make_args(action="analyze", company_id="US_AAPL", type=None)
        await handle(args, services)

        captured = capsys.readouterr()
        assert "business_summary" in captured.out


class TestRagAsk:
    async def test_ask_question(self, services, capsys):
        qr = QueryResult(
            answer="Revenue was $100B",
            source_pages=[5, 6],
            source_sections=["Revenue"],
            confidence=0.9,
            model="ollama/qwen3.5:27b-q8_0",
        )
        services.rag_service.ask_question.return_value = qr

        args = make_args(
            action="ask", company_id="US_AAPL", question="What was revenue?",
        )
        await handle(args, services)

        captured = capsys.readouterr()
        assert "100B" in captured.out


class TestRagStatus:
    async def test_status_shows_indices(self, services, capsys):
        services.rag_service.get_index_status.return_value = [
            {"filing_id": 1, "model_name": "m", "page_count": 50,
             "node_count": 12, "created_at": "2026-03-22"},
        ]

        args = make_args(action="status", company_id="US_AAPL")
        await handle(args, services)

        captured = capsys.readouterr()
        assert "50" in captured.out


class TestRagShow:
    async def test_show_analyses(self, services, capsys):
        services.rag_service.get_analyses.return_value = [
            {"analysis_type": "business_summary",
             "result_json": {"summary": "Apple makes iPhones"},
             "model_name": "m", "created_at": "2026-03-22"},
        ]

        args = make_args(
            action="show", company_id="US_AAPL", filing_id=1, json=True,
        )
        await handle(args, services)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["analysis_type"] == "business_summary"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/cli/test_rag_cli.py -v`
Expected: FAIL — handler still prints stub message and exits

- [ ] **Step 3: Replace rag.py stub with full implementation**

```python
# src/stock_analyze_system/cli/rag.py
"""RAG分析サブコマンド"""
from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from stock_analyze_system.cli.formatters import format_json, format_table
from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES

if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("rag", help="RAG分析")
    parser.add_argument("--json", action="store_true", help="JSON出力")
    sub = parser.add_subparsers(dest="action", required=True)

    # rag analyze
    p_analyze = sub.add_parser("analyze", help="定型分析実行")
    p_analyze.add_argument("company_id", help="企業ID (例: US_AAPL)")
    p_analyze.add_argument(
        "--type", dest="type", choices=ANALYSIS_TYPE_NAMES, default=None,
        help="分析タイプ (省略時は全4タイプ実行)",
    )
    p_analyze.add_argument("--quality", action="store_true", help="高精度モデル使用")

    # rag ask
    p_ask = sub.add_parser("ask", help="自由質問")
    p_ask.add_argument("company_id", help="企業ID")
    p_ask.add_argument("question", help="質問文")
    p_ask.add_argument("--quality", action="store_true", help="高精度モデル使用")
    p_ask.add_argument("--model", default=None, help="モデル明示指定")

    # rag index
    p_index = sub.add_parser("index", help="インデックス構築")
    p_index.add_argument("company_id", nargs="?", default=None, help="企業ID (省略時は--all必須)")
    p_index.add_argument("--all", action="store_true", dest="all_companies", help="全企業の未構築インデックスを一括構築")

    # rag status
    p_status = sub.add_parser("status", help="インデックス状態")
    p_status.add_argument("company_id", help="企業ID")

    # rag health
    sub.add_parser("health", help="LLMヘルスチェック")

    # rag show
    p_show = sub.add_parser("show", help="分析結果表示")
    p_show.add_argument("company_id", help="企業ID")
    p_show.add_argument("--filing-id", type=int, default=None, help="ファイリングID")

    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    if services.rag_service is None:
        print("RAG service is not configured.", file=sys.stderr)
        sys.exit(1)

    rag = services.rag_service
    action = args.action

    if action == "health":
        await _handle_health(rag, args)
    elif action == "index":
        await _handle_index(rag, services, args)
    elif action == "analyze":
        await _handle_analyze(rag, services, args)
    elif action == "ask":
        await _handle_ask(rag, services, args)
    elif action == "status":
        await _handle_status(rag, args)
    elif action == "show":
        await _handle_show(rag, services, args)


async def _handle_health(rag, args) -> None:
    result = await rag.health_check()
    if args.json:
        print(format_json(result))
    else:
        status = result["status"]
        print(f"LLM Status: {status}")
        print(f"  Model:   {result.get('model', 'N/A')}")
        print(f"  Backend: {result.get('backend', 'N/A')}")
        print(f"  URL:     {result.get('base_url', 'N/A')}")
        if status == "error":
            print(f"  Error:   {result.get('error', '')}", file=sys.stderr)
            sys.exit(1)


async def _handle_index(rag, services, args) -> None:
    from stock_analyze_system.cli.helpers import require_company, require_latest_filing

    if getattr(args, "all_companies", False):
        # 全企業の未構築インデックスを一括構築
        targets = await services.target_service.list_targets()
        for t in targets:
            filing = await services.filing_service.get_latest_filing(t.company_id, "10-K")
            if filing is None:
                print(f"  {t.company_id}: no 10-K filing, skipped")
                continue
            print(f"  Building index for {t.company_id} (filing {filing.id})...")
            tree = await rag.build_index(filing)
            node_count = tree.get("node_count", len(tree.get("nodes", [])))
            print(f"  {t.company_id}: {node_count} nodes")
        return

    if args.company_id is None:
        print("company_id or --all is required.", file=sys.stderr)
        sys.exit(1)

    company = await require_company(services.company_service, args.company_id)
    filing = await require_latest_filing(
        services.filing_service, company.id, "10-K",
    )
    print(f"Building index for {company.id} (filing {filing.id})...")
    tree = await rag.build_index(filing)
    node_count = tree.get("node_count", len(tree.get("nodes", [])))
    print(f"Index built: {node_count} nodes")


async def _handle_analyze(rag, services, args) -> None:
    from stock_analyze_system.cli.helpers import require_company, require_latest_filing
    company = await require_company(services.company_service, args.company_id)
    filing = await require_latest_filing(
        services.filing_service, company.id, "10-K",
    )

    if args.type:
        print(f"Running {args.type} analysis for {company.id}...")
        result = await rag.run_analysis(filing, args.type)
        results = [result]
    else:
        print(f"Running full analysis for {company.id} (4 types)...")
        results = await rag.run_full_analysis(filing)

    if args.json:
        print(format_json([r.to_dict() for r in results]))
    else:
        for r in results:
            label = r.analysis_type
            print(f"\n{'='*60}")
            print(f"  {label}")
            print(f"{'='*60}")
            print(json.dumps(r.result_json, indent=2, ensure_ascii=False))
            print(f"  Sources: pages {r.query_result.source_pages}")
            print(f"  Confidence: {r.query_result.confidence:.0%}")


async def _handle_ask(rag, services, args) -> None:
    from stock_analyze_system.cli.helpers import require_company, require_latest_filing
    company = await require_company(services.company_service, args.company_id)
    filing = await require_latest_filing(
        services.filing_service, company.id, "10-K",
    )

    print(f"Querying {company.id}...")
    result = await rag.ask_question(filing, args.question)

    if args.json:
        print(format_json(result.to_dict()))
    else:
        print(f"\nAnswer:\n{result.answer}")
        print(f"\nSources: pages {result.source_pages}")
        print(f"Sections: {', '.join(result.source_sections)}")
        print(f"Model: {result.model}")
        print(f"Confidence: {result.confidence:.0%}")


async def _handle_status(rag, args) -> None:
    indices = await rag.get_index_status(args.company_id)
    if args.json:
        print(format_json(indices))
    elif not indices:
        print(f"No indices found for {args.company_id}.")
    else:
        headers = ["Filing ID", "Model", "Pages", "Nodes", "Created"]
        rows = [
            {"Filing ID": i["filing_id"], "Model": i["model_name"],
             "Pages": i["page_count"], "Nodes": i["node_count"],
             "Created": i["created_at"]}
            for i in indices
        ]
        print(format_table(rows, headers))


async def _handle_show(rag, services, args) -> None:
    from stock_analyze_system.cli.helpers import require_company, require_latest_filing
    company = await require_company(services.company_service, args.company_id)

    filing_id = args.filing_id
    if filing_id is None:
        filing = await require_latest_filing(
            services.filing_service, company.id, "10-K",
        )
        filing_id = filing.id

    analyses = await rag.get_analyses(company.id, filing_id)
    if args.json:
        print(format_json(analyses))
    elif not analyses:
        print(f"No analyses found for {company.id} filing {filing_id}.")
    else:
        for a in analyses:
            print(f"\n{'='*60}")
            print(f"  {a['analysis_type']} (model: {a['model_name']})")
            print(f"  Created: {a['created_at']}")
            print(f"{'='*60}")
            print(json.dumps(a["result_json"], indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/cli/test_rag_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_analyze_system/cli/rag.py tests/unit/cli/test_rag_cli.py
git commit -m "feat: implement rag CLI handlers (analyze/ask/index/status/health/show)"
```

---

## Task 7: DI Wiring — ServiceContainer + setup_services

**Files:**
- Modify: `src/stock_analyze_system/cli/helpers.py`
- Modify: `src/stock_analyze_system/config.py`

- [ ] **Step 1: Update LlmConfig model identifiers in config.py**

Change `LlmConfig.model` default from `"ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:Q8_0"` to `"ollama/qwen3.5:27b-q8_0"`.

Keep `model_quality` as `"ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:UD-Q8_K_XL"` (only available via HF).

In `src/stock_analyze_system/config.py`:

```python
# Change line 53:
    model: str = "ollama/qwen3.5:27b-q8_0"
# Keep line 54 as-is (UD-Q8_K_XL only on HuggingFace)
```

- [ ] **Step 1b: Widen model_name column in DB models**

In `src/stock_analyze_system/models/company_analysis.py` and `src/stock_analyze_system/models/document_index.py`, change `String(50)` to `String(100)` for `model_name`:

```python
# Both files:
    model_name: Mapped[str] = mapped_column(String(100))
```

This prevents truncation of long HuggingFace model identifiers (the quality model ID is 48 chars).

- [ ] **Step 2: Wire RAG services into setup_services**

In `src/stock_analyze_system/cli/helpers.py`, add RAG service assembly to `setup_services()`:

```python
# Add imports at the end of the lazy import block in setup_services():
    from stock_analyze_system.repositories.document_index import DocumentIndexRepository
    from stock_analyze_system.repositories.analysis import AnalysisRepository
    from stock_analyze_system.services.llm_client import LlmClient
    from stock_analyze_system.services.pdf_converter import PdfConverter
    from stock_analyze_system.services.pageindex_service import PageIndexService
    from stock_analyze_system.services.rag_service import RagService

# Add after existing service initialization:
    # RAG services
    doc_index_repo = DocumentIndexRepository(session)
    analysis_repo = AnalysisRepository(session)
    llm_client = LlmClient(config.llm)
    pdf_converter = PdfConverter()
    pageindex_service = PageIndexService(
        doc_index_repo=doc_index_repo,
        pdf_converter=pdf_converter,
        llm_client=llm_client,
        config=config.pageindex,
    )
    rag_service = RagService(
        pageindex_service=pageindex_service,
        analysis_repo=analysis_repo,
        filing_repo=filing_repo,
        llm_client=llm_client,
    )

# Update return statement:
    return ServiceContainer(
        ...
        rag_service=rag_service,  # was None
        ...
    )
```

- [ ] **Step 3: Run all existing tests to verify nothing breaks**

Run: `python -m pytest tests/ -v`
Expected: All PASS (no regressions)

- [ ] **Step 4: Commit**

```bash
git add src/stock_analyze_system/config.py src/stock_analyze_system/cli/helpers.py src/stock_analyze_system/models/company_analysis.py src/stock_analyze_system/models/document_index.py
git commit -m "feat: wire RAG services into ServiceContainer, update model identifiers, widen model_name column"
```

---

## Task 8: Full Test Suite Verification

- [ ] **Step 1: Run complete test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run ruff linter**

Run: `ruff check src/stock_analyze_system/services/llm_client.py src/stock_analyze_system/services/pdf_converter.py src/stock_analyze_system/services/pageindex_service.py src/stock_analyze_system/services/prompts.py src/stock_analyze_system/services/rag_service.py src/stock_analyze_system/cli/rag.py`
Expected: No errors

- [ ] **Step 3: Fix any linting issues**

Apply fixes if needed, then re-run ruff and tests.

- [ ] **Step 4: Commit fixes if any**

```bash
git add -u
git commit -m "fix: resolve linting issues in Phase 6 code"
```

---

## Task 9: Integration Smoke Test (Manual)

This task requires a running Ollama instance with qwen3.5:27b-q8_0 loaded.

- [ ] **Step 1: Verify LLM health**

```bash
python -m stock_analyze_system rag health
```

Expected output:
```
LLM Status: ok
  Model:   ollama/qwen3.5:27b-q8_0
  Backend: ollama
  URL:     http://localhost:11434
```

- [ ] **Step 2: Test with a real filing (if available)**

```bash
# Check if any filings exist
python -m stock_analyze_system filings list US_AAPL

# If filings exist with downloaded HTML:
python -m stock_analyze_system rag index US_AAPL
python -m stock_analyze_system rag status US_AAPL
python -m stock_analyze_system rag ask US_AAPL "What is the main business?"
python -m stock_analyze_system rag analyze US_AAPL --type business_summary
```

- [ ] **Step 3: Document results and commit any fixes**

---

## Summary

| Task | Component | Tests | Files |
|------|-----------|-------|-------|
| 1 | LlmClient | 7 tests | 2 files |
| 2 | PdfConverter | 3 tests | 2 files |
| 3 | PageIndexService | 5 tests | 2 files |
| 4 | Prompts | (tested via Task 5) | 1 file |
| 5 | RagService | 6 tests | 2 files |
| 6 | CLI rag | 5+ tests | 2 files |
| 7 | DI Wiring | regression | 2 files (modify) |
| 8 | Full Verification | all | — |
| 9 | Smoke Test | manual | — |

**Total new files:** 9 (5 services, 4 test files)
**Modified files:** 3 (rag.py, helpers.py, config.py)
