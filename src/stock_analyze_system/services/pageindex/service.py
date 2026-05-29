"""PageIndex ツリーインデックスの構築・クエリサービス."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from stock_analyze_system.config import PageIndexConfig
from stock_analyze_system.exceptions import IndexBuildError
from stock_analyze_system.services.pageindex.diagnostics import (
    configure_max_tokens_clamp,
    get_last_diagnostic,
    install_diagnostic_wrappers,
    reset_diagnostic,
)
from stock_analyze_system.services.pageindex.compat import (
    _HAS_PAGEINDEX_ASYNC_HELPERS,
    ConfigLoader,
    _pi_extract_json,
    add_node_text,
    configure_litellm_timeout,
    configure_max_tokens,
    configure_thinking,
    get_page_tokens,
    get_pdf_name,
    llm_acompletion,
    page_index,
    remove_structure_text,
    structure_to_list,
    tree_parser,
    write_node_id,
)
from stock_analyze_system.services.pageindex.models import (
    BuildResult,
    BuildTiming,
    QueryResult,
    QueryTiming,
)
from stock_analyze_system.services.pageindex.prompts import (
    _DOCUMENT_GUARDRAIL_EN,
    _DOCUMENT_GUARDRAIL_JA,
)
from stock_analyze_system.services.pageindex.tree_utils import (
    collect_node_map,
    count_nodes,
    extract_page_count,
    node_page,
    strip_text,
)
from stock_analyze_system.shared.json_utils import extract_json_object, json_dumps_ja

if TYPE_CHECKING:
    from stock_analyze_system.repositories.document_index import DocumentIndexRepository
    from stock_analyze_system.services.llm_client import LlmClient
    from stock_analyze_system.services.pdf_converter import PdfConverter

logger = logging.getLogger(__name__)

_build_semaphore = asyncio.Semaphore(1)

_FALLBACK_NODE_LIMIT = 5
_FALLBACK_SYNONYMS = {
    "検査数": (
        "test volume",
        "test volumes",
        "testing volume",
        "tests performed",
        "clinical tests",
        "diagnostic tests",
        "volumes",
    ),
    "検査": (
        "test",
        "tests",
        "testing",
        "diagnostic",
        "diagnostics",
        "sequencing",
    ),
    "提携病院": (
        "hospital",
        "hospitals",
        "provider",
        "providers",
        "healthcare provider",
        "health systems",
        "provider network",
    ),
    "病院": (
        "hospital",
        "hospitals",
        "provider",
        "providers",
        "healthcare provider",
    ),
    "医療データ": (
        "clinical data",
        "medical data",
        "records",
        "de-identified records",
        "datasets",
        "database",
    ),
    "データ": (
        "data",
        "records",
        "datasets",
        "database",
    ),
    "企業": (
        "company",
        "companies",
        "customer",
        "customers",
        "partner",
        "partners",
        "third parties",
    ),
}


def _fallback_query_terms(question: str) -> list[str]:
    """Return lightweight lexical terms for RAG fallback node selection."""
    terms: list[str] = []
    question_lower = question.lower()

    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", question_lower):
        if token not in terms:
            terms.append(token)

    for needle, synonyms in _FALLBACK_SYNONYMS.items():
        if needle in question:
            for term in synonyms:
                if term not in terms:
                    terms.append(term)

    return terms


def _fallback_node_ids(
    question: str,
    node_map: dict[str, dict],
    *,
    limit: int = _FALLBACK_NODE_LIMIT,
) -> list[str]:
    """Select likely nodes when the LLM tree search returns no usable node IDs."""
    terms = _fallback_query_terms(question)
    if not terms:
        return []

    scored: list[tuple[int, int, str]] = []
    for order, (node_id, node) in enumerate(node_map.items()):
        haystack = " ".join(
            str(node.get(key, ""))
            for key in ("title", "summary", "text")
        ).lower()
        if not haystack:
            continue

        score = 0
        for term in terms:
            if term in haystack:
                score += 3 if " " in term else 1
        if score:
            scored.append((score, -order, node_id))

    scored.sort(reverse=True)
    return [node_id for _, _, node_id in scored[:limit]]


def _resolve_nodes(
    node_ids: list[str],
    node_map: dict[str, dict],
) -> list[tuple[str, dict]]:
    return [(node_id, node_map[node_id]) for node_id in node_ids if node_id in node_map]


class PageIndexService:
    """PageIndexツリーインデックスの構築とクエリ"""

    def __init__(
        self,
        doc_index_repo: DocumentIndexRepository,
        pdf_converter: PdfConverter,
        llm_client: LlmClient,
        config: PageIndexConfig,
    ):
        self._repo = doc_index_repo
        self._pdf_converter = pdf_converter
        self._llm_client = llm_client
        self._config = config

    def _pageindex_options(self, model: str) -> dict:
        return {
            "model": model,
            "api_base": self._llm_client.base_url,
            "toc_check_page_num": self._config.toc_check_pages,
            "max_page_num_each_node": self._config.max_pages_per_node,
            "max_token_num_each_node": self._config.max_tokens_per_node,
            "if_add_node_summary": "yes" if self._config.add_node_summary else "no",
            "if_add_node_text": "yes" if self._config.add_node_text else "no",
            "max_tokens": self._llm_client.max_tokens,
        }

    def _pageindex_request_timeout(self) -> int:
        timeout = getattr(self._llm_client, "request_timeout", None)
        if isinstance(timeout, (int, float)) and timeout > 0:
            return int(timeout)
        return 120

    async def build_index(self, pdf_path: Path) -> BuildResult:
        """PDFからPageIndexツリーインデックスを構築する

        Note: PageIndexライブラリは内部で asyncio.run() を呼ぶため、
        asyncio.to_thread() と組み合わせると大規模PDFでデッドロックする。
        そのため同期部分(PDF解析)のみスレッドで実行し、
        非同期部分はカレントイベントループで直接実行する。
        """
        model = self._llm_client.resolve_model(quality=False)
        logger.info("Building PageIndex for %s with model %s", pdf_path, model)

        timing = BuildTiming()
        t_total = time.perf_counter()

        async with _build_semaphore:
            if configure_thinking is not None:
                configure_thinking(False)

            t0 = time.perf_counter()

            if _HAS_PAGEINDEX_ASYNC_HELPERS:
                tree = await self._build_index_async(str(pdf_path), model)
            elif page_index is not None:
                tree = await asyncio.to_thread(
                    page_index,
                    str(pdf_path),
                    **self._pageindex_options(model),
                )
            else:
                raise IndexBuildError(
                    "PageIndex is not available. Install pageindex or configure "
                    "the PageIndex integration before building indexes.",
                )

            timing.page_index_call = time.perf_counter() - t0

        timing.total = time.perf_counter() - t_total

        nodes = count_nodes(tree)
        logger.info(
            "PageIndex built: %d nodes, timing: %s", nodes, timing,
        )
        return BuildResult(tree=tree, timing=timing)

    async def _build_index_async(self, pdf_path: str, model: str) -> dict:
        """PageIndexのasyncビルダーをカレントループで直接実行する（デッドロック回避）"""
        user_opt = self._pageindex_options(model)
        opt = ConfigLoader().load(user_opt)
        timeout_seconds = self._pageindex_request_timeout()

        max_tokens = getattr(opt, "max_tokens", None)
        if max_tokens is not None:
            configure_max_tokens(int(max_tokens))

        # 1リクエストあたりのHTTPタイムアウト。これがないとllama-server側で
        # 迷子になったリクエストが永久ブロックし、TEM 10-K等の大規模PDFで
        # デッドロック化する (utils.py に渡される)。
        configure_litellm_timeout(timeout_seconds)

        # PageIndexの _LLM_SEMAPHORE はllama-serverのスロット数(4)と一致。
        # tem_direct_build.log で100%精度完了を確認済み(直接PageIndex呼出)。
        # 以前は _sync_wrapped_acompletion で acompletion を to_thread + wait_for
        # ラップしていたが、py-spy で全スレッドidle・event loop 1スケジュール
        # コールバックのみのデッドロック発生を確認 → ラッパー削除し純粋な
        # litellm.acompletion を使用 (utils.py に timeout=120s 追加済み)。

        # PageIndex 内部の LLM 呼び出しを横取りして finish_reason / content_head 等を
        # 採取できるようにする (pageindex.page_index 名前空間への setattr).
        # tree_parser 例外時に最後の状態を IndexBuildError.diagnostic に載せ、
        # `Processing failed` の本当の原因 (length 切れ / error / 空応答) を残す.
        install_diagnostic_wrappers()
        reset_diagnostic()
        # generate_toc_init は max_tokens=32768 をハードコードしており、
        # `configure_max_tokens(...)` をバイパスする. ラッパー越しに config の
        # max_tokens でクランプして <think> 暴走の最大ダメージを上限する.
        if max_tokens is not None:
            configure_max_tokens_clamp(int(max_tokens))

        # PDF解析・トークナイズ (同期 CPU-bound) → スレッドで実行
        page_list = await asyncio.to_thread(get_page_tokens, pdf_path, opt.model)

        # 非同期ビルダー — カレントイベントループで直接実行
        from pageindex import JsonLogger

        log = JsonLogger(pdf_path)
        try:
            structure, verification_log = await tree_parser(
                page_list, opt, doc=pdf_path, logger=log,
            )

            if opt.if_add_node_id == "yes":
                write_node_id(structure)
            if opt.if_add_node_text == "yes":
                add_node_text(structure, page_list)
            if opt.if_add_node_summary == "yes":
                if opt.if_add_node_text == "no":
                    add_node_text(structure, page_list)
                await self._generate_summaries_safe(
                    structure,
                    model=opt.model,
                    api_base=opt.api_base,
                    timeout=float(timeout_seconds),
                )
                if opt.if_add_node_text == "no":
                    remove_structure_text(structure)
        except IndexBuildError:
            raise
        except Exception as exc:
            last_diag = get_last_diagnostic()
            logger.error(
                "PI-BUILD-FAIL: %s | diagnostic=%s",
                exc, last_diag,
            )
            raise IndexBuildError(
                f"PageIndex build failed: {exc}",
                diagnostic=last_diag,
            ) from exc

        return {
            "doc_name": get_pdf_name(pdf_path),
            "page_count": len(page_list),
            "structure": structure,
            "verification_log": verification_log,
        }

    async def _generate_summaries_safe(
        self,
        structure: list,
        *,
        model: str,
        api_base: str,
        max_text_chars: int = 50_000,
        timeout: float | None = None,
    ) -> None:
        """generate_summaries_for_structureの安全版

        * ノードテキストを max_text_chars で切り詰め (巨大ノードでの長時間推論を回避)
        * 1呼び出しあたり timeout 秒のタイムアウト (CLOSE-WAIT デッドロック防止)
        """
        if timeout is None:
            timeout = float(self._pageindex_request_timeout())
        nodes = structure_to_list(structure)
        sem = asyncio.Semaphore(4)

        async def _summarise_one(node: dict) -> str:
            text = node.get("text", "")
            if not text:
                return ""
            if len(text) > max_text_chars:
                text = text[:max_text_chars] + "\n...[truncated]"

            prompt = (
                "Task: Summarize the main points of the following document "
                "section in 2-4 sentences.\n"
                f"{_DOCUMENT_GUARDRAIL_EN}\n\n"
                f"Document text:\n{text}\n\n"
                'Return JSON: {"summary": "<concise summary of the main points>"}'
            )
            async with sem:
                try:
                    response = await asyncio.wait_for(
                        llm_acompletion(model, prompt, api_base=api_base, max_tokens=4096),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    title = node.get("title", "unknown")
                    logger.warning("Summary timed out for node: %s", title)
                    return f"(Summary timed out: {title})"

            parsed = _pi_extract_json(response)
            if isinstance(parsed, dict) and "summary" in parsed:
                return parsed["summary"]
            return response

        logger.info("Generating summaries for %d nodes …", len(nodes))
        summaries = await asyncio.gather(*[_summarise_one(n) for n in nodes])
        for node, summary in zip(nodes, summaries):
            node["summary"] = summary

    async def get_or_create_index(self, filing) -> dict:
        """キャッシュ済みインデックスを返すか、なければ構築・保存する"""
        if self._config.cache_indices:
            cached = await self._repo.get_by_filing(filing.id)
            if cached is not None:
                logger.info("Using cached index for filing %d", filing.id)
                return json.loads(cached.index_json)

        pdf_path = await self._pdf_converter.get_or_convert(filing)
        result = await self.build_index(pdf_path)
        tree = result.tree

        model = self._llm_client.resolve_model(quality=False)
        await self._repo.save_index(
            filing_id=filing.id,
            company_id=filing.company_id,
            data={
                "index_json": json_dumps_ja(tree),
                "model_name": model,
                "page_count": extract_page_count(tree),
                "node_count": count_nodes(tree),
            },
        )

        return tree

    async def query(self, tree: dict, question: str, pdf_path: Path) -> QueryResult:
        """ツリーインデックスに対してRAGクエリを実行する"""
        timing = QueryTiming()
        t_total = time.perf_counter()

        model = self._llm_client.resolve_model(quality=True)
        node_map = collect_node_map(tree)

        tree_summary = json_dumps_ja(strip_text(tree), indent=2)
        search_prompt = (
            f"以下のドキュメントツリー構造から、質問に回答するために必要なノードを特定してください。\n\n"
            f"{_DOCUMENT_GUARDRAIL_JA}\n\n"
            f"質問: {question}\n\n"
            f"ドキュメントツリー:\n{tree_summary}\n\n"
            f"JSON形式で回答してください: "
            f'{{"thinking": "理由", "node_list": ["ノードID1", "ノードID2"]}}'
        )
        t0 = time.perf_counter()
        search_result = await self._llm_client.completion(
            search_prompt, quality=True, model=model, thinking=False,
        )
        timing.tree_search = time.perf_counter() - t0

        parsed = extract_json_object(search_result)
        if parsed is not None:
            node_ids = parsed.get("node_list", [])
        else:
            logger.warning("Failed to extract JSON from tree search result, using first 5 nodes")
            node_ids = list(node_map.keys())[:5]
        selected_nodes = _resolve_nodes(node_ids, node_map)
        if parsed is not None and not selected_nodes:
            fallback_ids = _fallback_node_ids(question, node_map)
            if fallback_ids:
                logger.info(
                    "Tree search returned no usable nodes; keyword fallback selected %s",
                    fallback_ids,
                )
                selected_nodes = _resolve_nodes(fallback_ids, node_map)

        t0 = time.perf_counter()
        sections = []
        pages = []
        context_parts = []
        resolved_nodes = 0
        for nid, node in selected_nodes:
            resolved_nodes += 1
            sections.append(node.get("title", nid))
            page = node_page(node)
            if page is not None:
                pages.append(page)
            text = node.get("text", node.get("summary", ""))
            if text:
                context_parts.append(f"[{node.get('title', nid)}]\n{text}")

        context = "\n\n".join(context_parts)
        timing.context_build = time.perf_counter() - t0

        answer_prompt = (
            f"以下のコンテキストに基づいて質問に日本語で回答してください。\n\n"
            f"{_DOCUMENT_GUARDRAIL_JA}\n"
            f"コンテキストに根拠がない場合は、わからないと答えてください。\n\n"
            f"質問: {question}\n\n"
            f"コンテキスト:\n{context}"
        )
        t0 = time.perf_counter()
        answer = await self._llm_client.completion(
            answer_prompt, quality=True, model=model, thinking=True,
        )
        timing.answer_generation = time.perf_counter() - t0

        timing.total = time.perf_counter() - t_total
        logger.info("Query timing: %s", timing)

        return QueryResult(
            answer=answer,
            source_pages=sorted(set(pages)),
            source_sections=sections,
            confidence=min(1.0, resolved_nodes * 0.3) if resolved_nodes else 0.0,
            model=model,
            timing=timing,
        )

    async def get_indices_for_company(self, company_id: str) -> list:
        """企業のインデックス一覧を返す"""
        return await self._repo.list_all(company_id=company_id)
