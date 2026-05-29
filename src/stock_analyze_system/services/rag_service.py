# src/stock_analyze_system/services/rag_service.py
"""RAGサービス — 定型分析・自由質問のオーケストレーション"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.company_analysis import PIPELINE_EXTRACTOR
from stock_analyze_system.models.enums import ADR004_SUPPORTED_DESC, is_adr004_supported
from stock_analyze_system.services.filing_content import (
    filing_content_exists,
    filing_raw_html_exists,
)
from stock_analyze_system.services.filing_section_extractor import (
    ExtractionInputMissingError,
    FilingSectionExtractor,
    is_structurally_empty,
)
from stock_analyze_system.services.pageindex import QueryResult
from stock_analyze_system.services.prompts import ANALYSIS_TYPES, ANALYSIS_TYPE_NAMES
from stock_analyze_system.shared.json_utils import json_dumps_ja, safe_json_loads

if TYPE_CHECKING:
    from stock_analyze_system.repositories.analysis import AnalysisRepository
    from stock_analyze_system.repositories.rag_qa_history import RagQaHistoryRepository
    from stock_analyze_system.services.filing_content import FilingContentService
    from stock_analyze_system.services.llm_client import LlmClient
    from stock_analyze_system.services.pageindex import PageIndexService

logger = logging.getLogger(__name__)


_PLACEHOLDER_MODEL = "structural-placeholder"
_EMPTY_LLM_REASON = (
    "LLM returned empty content (possible reasoning_content runaway"
    " — see ADR-004 §4.5)"
)


class PageIndexDisabledError(RuntimeError):
    """PageIndex 経路 (ask_question / build_index / get_index_status) が
    config.pageindex.enabled=False のため無効化されているときに送出される。

    定型分析 (run_full_analysis / run_full_analysis_stream / run_analysis) は
    PageIndex 非依存なので、これらは pageindex_service=None でも動く."""


class UnsupportedFilingForExtractorError(ValueError):
    """FilingSectionExtractor が扱えない filing を定型分析へ渡した。"""


def _is_empty_llm_response(answer: str | None) -> bool:
    return not (answer or "").strip()


def _error_event(index: int, analysis_type: str, message: str) -> dict:
    return {
        "event": "error", "index": index,
        "analysis_type": analysis_type, "message": message,
    }


def _skipped_event(index: int, analysis_type: str) -> dict:
    return {
        "event": "skipped", "index": index,
        "analysis_type": analysis_type, "reason": "structurally_absent",
    }


def _placeholder_result(filing_type: str, analysis_type: str) -> dict:
    """Sentinel the UI keys off `_status="not_applicable"` to render 適用外."""
    return {
        "_status": "not_applicable",
        "_filing_type": filing_type,
        "_analysis_type": analysis_type,
        "_message": (
            f"このファイリング種別 ({filing_type}) には "
            f"{analysis_type} の章がありません"
        ),
    }


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


@dataclass
class _PerTypeOutcome:
    """Outcome of processing a single analysis_type — drives both stream and
    non-stream entry points so per-type semantics (cache / placeholder / error)
    cannot drift between them.

    `cause` is set for runtime failures (cache lookup, cached-row parse,
    placeholder save, LLM analyze, save) and left None for the
    "chapter is just missing" case. Non-stream callers re-raise when cause
    is set so the CLI keeps failing fast on real errors, but still skip the
    chapter-missing case so 3/4 partial results survive (matches the
    streaming UX where the worker keeps progressing).
    """
    kind: Literal["cached", "done", "skipped", "error"]
    analysis_type: str
    result: AnalysisResult | None = None
    message: str = ""
    cause: BaseException | None = None


class RagService:
    """RAG分析オーケストレーション"""

    def __init__(
        self,
        pageindex_service: PageIndexService | None,
        analysis_repo: AnalysisRepository,
        llm_client: LlmClient,
        qa_history_repo: RagQaHistoryRepository | None = None,
        filing_content_service: FilingContentService | None = None,
        section_extractor: FilingSectionExtractor | None = None,
    ):
        self._pageindex = pageindex_service
        self._analysis_repo = analysis_repo
        self._llm_client = llm_client
        self._qa_history_repo = qa_history_repo
        self._filing_content_service = filing_content_service
        self._section_extractor = section_extractor or FilingSectionExtractor()

    @property
    def pageindex_available(self) -> bool:
        """PageIndex 経路 (ask_question / build_index / get_index_status) が
        使えるかどうか. web route が rate limit を消費する前に 503 で
        早期 return するために参照する.

        `get_qa_history` は PageIndex に依存しないため本プロパティのガード対象外
        (qa_history_repo が無い場合は `[]` を返す)."""
        return self._pageindex is not None

    async def health_check(self) -> dict:
        """LLMヘルスチェックを委譲する"""
        return await self._llm_client.health_check()

    async def build_index(self, filing) -> dict:
        """インデックスを構築または取得する。PageIndex 無効時は明示エラー."""
        if self._pageindex is None:
            raise PageIndexDisabledError(
                "pageindex.enabled=false; build_index は無効化されています"
            )
        filing = await self._ensure_filing_content(filing)
        return await self._pageindex.get_or_create_index(filing)

    async def _ensure_filing_content(self, filing):
        if self._filing_content_available(filing):
            return filing
        if self._filing_content_service is None:
            if filing.storage_path:
                return filing
            raise FileNotFoundError(
                "Filing content not available; run `stock-analyze filings download` first.",
            )
        return await self._filing_content_service.ensure_content(filing)

    async def _ensure_extractor_content(self, filing):
        self._ensure_supported_extractor_filing(filing)
        if self._filing_extractor_content_available(filing):
            return filing
        if self._filing_content_service is None:
            if filing.storage_path:
                return filing
            raise FileNotFoundError(
                "Filing content not available; run `stock-analyze filings download` first.",
            )
        return await self._filing_content_service.ensure_content(filing)

    @staticmethod
    def _filing_content_available(filing) -> bool:
        return filing_content_exists(filing.storage_path)

    @staticmethod
    def _filing_extractor_content_available(filing) -> bool:
        return filing_raw_html_exists(filing.storage_path)

    @staticmethod
    def _has_concrete_extractor_support_fields(filing) -> bool:
        return isinstance(getattr(filing, "source", None), str) and isinstance(
            getattr(filing, "filing_type", None),
            str,
        )

    @staticmethod
    def _unsupported_filing_message(filing) -> str:
        return (
            f"定型分析は {ADR004_SUPPORTED_DESC} の raw HTML filing のみ対応です "
            f"(source={getattr(filing, 'source', None)!r}, "
            f"filing_type={getattr(filing, 'filing_type', None)!r}, "
            f"filing_id={getattr(filing, 'id', None)!r})"
        )

    def _ensure_supported_extractor_filing(self, filing) -> None:
        # Unit tests and small duck-typed callers may omit concrete model fields;
        # production Filing rows always carry string source/filing_type values.
        if not self._has_concrete_extractor_support_fields(filing):
            return
        if not is_adr004_supported(filing):
            raise UnsupportedFilingForExtractorError(
                self._unsupported_filing_message(filing),
            )

    async def _save_analysis(
        self, filing, analysis_type: str, qr: QueryResult,
    ) -> AnalysisResult:
        """Parse the LLM answer as JSON and persist the resulting row."""
        return await self._persist(filing, analysis_type, safe_json_loads(qr.answer), qr)

    async def _persist(
        self,
        filing,
        analysis_type: str,
        result_json: dict,
        qr: QueryResult,
    ) -> AnalysisResult:
        await self._analysis_repo.upsert(
            {
                "company_id": filing.company_id,
                "filing_id": filing.id,
                "analysis_type": analysis_type,
                "pipeline": PIPELINE_EXTRACTOR,
            },
            {"result_json": json_dumps_ja(result_json), "model_name": qr.model},
        )
        return AnalysisResult(
            analysis_type=analysis_type,
            result_json=result_json,
            query_result=qr,
        )

    async def run_analysis(
        self, filing, analysis_type: str,
    ) -> AnalysisResult:
        """単一の定型分析を実行する (ADR-004: extractor + LLM 1 回)."""
        if analysis_type not in ANALYSIS_TYPES:
            raise ValueError(
                f"Unknown analysis type: {analysis_type}. "
                f"Valid types: {ANALYSIS_TYPE_NAMES}"
            )

        logger.info(
            "Running %s analysis for filing %d", analysis_type, filing.id,
        )

        filing = await self._ensure_extractor_content(filing)
        try:
            sections = await self._section_extractor.extract(filing)
        except ExtractionInputMissingError:
            if is_structurally_empty(filing.filing_type, analysis_type):
                return await self._save_placeholder(filing, analysis_type)
            raise

        section_text = sections.get(analysis_type, "")
        if not section_text and is_structurally_empty(
            filing.filing_type, analysis_type,
        ):
            return await self._save_placeholder(filing, analysis_type)
        qr = await self._analyze_section(analysis_type, section_text)
        return await self._save_analysis(filing, analysis_type, qr)

    async def _analyze_section(
        self, analysis_type: str, section_text: str,
    ) -> QueryResult:
        """章テキストを LLM に渡し、構造化 JSON を生成する (step 3 only)."""
        spec = ANALYSIS_TYPES[analysis_type]
        if not section_text:
            raise ValueError(
                f"Section text for analysis_type={analysis_type!r} is empty "
                "(filing has no matching chapter)."
            )
        prompt = (
            f"{spec['prompt']}\n\n"
            f"--- Filing section text ---\n{section_text}"
        )
        answer = await self._llm_client.completion(prompt, quality=True)
        if _is_empty_llm_response(answer):
            # Empty content would otherwise round-trip via safe_json_loads as
            # {"raw_answer": ""} and be cached as success — hides the failure.
            raise ValueError(f"{_EMPTY_LLM_REASON} (analysis_type={analysis_type!r})")
        return QueryResult(
            answer=answer,
            source_pages=[],
            source_sections=[analysis_type],
            confidence=1.0,
            model=self._llm_client.resolve_model(quality=True),
        )

    async def preflight(self) -> dict:
        """Step-3-equivalent LLM probe (same model / chat template / timeout).

        Returns:
            {"status": "ok" | "error", "model": str,
             "response_head"?: str, "reason"?: str}
        """
        model = self._llm_client.resolve_model(quality=True)
        try:
            answer = await self._llm_client.completion(
                "Reply with the literal string: ok",
                quality=True,
                max_tokens=10,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RagService preflight failed: %s", exc)
            return {"status": "error", "model": model, "reason": str(exc)}

        head = (answer or "")[:200]
        if _is_empty_llm_response(answer):
            return {
                "status": "error", "model": model,
                "reason": _EMPTY_LLM_REASON,
                "response_head": head,
            }
        return {"status": "ok", "model": model, "response_head": head}

    async def run_full_analysis_stream(
        self, filing,
    ) -> AsyncIterator[dict]:
        """全タイプの定型分析を逐次実行し、進捗イベントを yield する。

        発火イベント:
          {"event": "fetching", "filing_id": int}
          {"event": "extracting"}
          {"event": "started", "total": N}
          {"event": "phase", "index": i, "total": N, "analysis_type": str, "label": str}
          {"event": "cached" | "done" | "skipped" | "error",
           "index": i, "analysis_type": str, ...}
          {"event": "complete"}
        """
        try:
            self._ensure_supported_extractor_filing(filing)
        except UnsupportedFilingForExtractorError as exc:
            yield {"event": "error", "analysis_type": None, "message": str(exc)}
            yield {"event": "complete"}
            return

        if not self._filing_extractor_content_available(filing):
            if self._filing_content_service is None:
                if not filing.storage_path:
                    yield {
                        "event": "error", "analysis_type": None,
                        "message": (
                            "ファイリング本体の自動取得に失敗しました。"
                            "`stock-analyze filings download <company_id>` を実行してください。"
                        ),
                    }
                    yield {"event": "complete"}
                    return
            else:
                yield {"event": "fetching", "filing_id": filing.id}
                try:
                    filing = await self._filing_content_service.ensure_content(filing)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("content fetch failed for filing %d", filing.id)
                    yield {
                        "event": "error", "analysis_type": None,
                        "message": f"本体取得に失敗しました: {exc}",
                    }
                    yield {"event": "complete"}
                    return

        yield {"event": "extracting"}
        try:
            sections = await self._section_extractor.extract(filing)
        except Exception as exc:  # noqa: BLE001
            logger.exception("section extraction failed for filing %d", filing.id)
            yield {"event": "error", "analysis_type": None, "message": str(exc)}
            yield {"event": "complete"}
            return

        types = list(ANALYSIS_TYPE_NAMES)
        total = len(types)
        yield {"event": "started", "total": total}

        for i, atype in enumerate(types):
            async for event in self._iteration_events(filing, i, total, atype, sections):
                yield event

        yield {"event": "complete"}

    async def _iteration_events(
        self,
        filing,
        i: int,
        total: int,
        atype: str,
        sections: dict[str, str],
    ) -> AsyncIterator[dict]:
        """Yield events for one analysis_type. Splits per-type processing from
        event shape so both stream and non-stream go through `_process_one`."""
        spec = ANALYSIS_TYPES[atype]
        yield {
            "event": "phase", "index": i, "total": total,
            "analysis_type": atype, "label": spec.get("label", atype),
        }
        outcome = await self._process_one(filing, atype, sections)
        if outcome.kind == "error":
            yield _error_event(i, atype, outcome.message)
        elif outcome.kind == "skipped":
            yield _skipped_event(i, atype)
        elif outcome.kind == "cached":
            yield {"event": "cached", "index": i, "analysis_type": atype}
        else:  # "done"
            yield {"event": "done", "index": i, "analysis_type": atype}

    async def _process_one(
        self, filing, atype: str, sections: dict[str, str],
    ) -> _PerTypeOutcome:
        """Resolve one analysis_type to a single outcome.

        Cache hit on a placeholder row stays "skipped" so the UI label keeps
        "適用外" instead of degrading to "(キャッシュ使用)".
        """
        try:
            cached = await self._analysis_repo.get_by_type(
                filing.company_id, filing.id, atype,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("cache lookup failed for %s/%s", filing.id, atype)
            return _PerTypeOutcome(
                kind="error", analysis_type=atype, message=str(exc), cause=exc,
            )

        if cached is not None:
            try:
                ar = self._cached_to_result(cached, atype)
            except Exception as exc:  # noqa: BLE001
                logger.exception("cached row parse failed for %s/%s", filing.id, atype)
                return _PerTypeOutcome(
                    kind="error", analysis_type=atype, message=str(exc), cause=exc,
                )
            kind: Literal["cached", "skipped"] = (
                "skipped"
                if getattr(cached, "model_name", None) == _PLACEHOLDER_MODEL
                else "cached"
            )
            return _PerTypeOutcome(kind=kind, analysis_type=atype, result=ar)

        section_text = sections.get(atype, "")
        if not section_text:
            if not is_structurally_empty(filing.filing_type, atype):
                # cause=None marks this as "chapter just missing", not a
                # runtime failure — non-stream skips silently, stream still
                # yields an error event.
                return _PerTypeOutcome(
                    kind="error", analysis_type=atype,
                    message="ファイリングから章テキストを抽出できませんでした",
                )
            try:
                placeholder = await self._save_placeholder(filing, atype)
            except Exception as exc:  # noqa: BLE001
                logger.exception("placeholder save failed for %s/%s", filing.id, atype)
                return _PerTypeOutcome(
                    kind="error", analysis_type=atype, message=str(exc), cause=exc,
                )
            return _PerTypeOutcome(kind="skipped", analysis_type=atype, result=placeholder)

        try:
            qr = await self._analyze_section(atype, section_text)
            result = await self._save_analysis(filing, atype, qr)
        except Exception as exc:  # noqa: BLE001
            logger.exception("analysis %s failed for filing %d", atype, filing.id)
            return _PerTypeOutcome(
                kind="error", analysis_type=atype, message=str(exc), cause=exc,
            )

        return _PerTypeOutcome(kind="done", analysis_type=atype, result=result)

    @staticmethod
    def _cached_to_result(cached, atype: str) -> AnalysisResult:
        qr = QueryResult(
            answer=cached.result_json,
            source_pages=[], source_sections=[],
            confidence=1.0, model=cached.model_name,
        )
        return AnalysisResult(
            analysis_type=atype,
            result_json=json.loads(cached.result_json),
            query_result=qr,
        )

    async def _save_placeholder(self, filing, analysis_type: str) -> AnalysisResult:
        """Persist a not_applicable sentinel so cache hits return quickly."""
        result_json = _placeholder_result(filing.filing_type, analysis_type)
        qr = QueryResult(
            answer=json_dumps_ja(result_json),
            source_pages=[], source_sections=[analysis_type],
            confidence=1.0, model=_PLACEHOLDER_MODEL,
        )
        # Skip the parse-then-reserialize round trip in _save_analysis.
        return await self._persist(filing, analysis_type, result_json, qr)

    async def _save_structural_placeholders_for_missing_input(
        self, filing,
    ) -> list[AnalysisResult]:
        """Persist placeholders for analysis types absent by filing structure."""
        results: list[AnalysisResult] = []
        for atype in ANALYSIS_TYPE_NAMES:
            if is_structurally_empty(filing.filing_type, atype):
                results.append(await self._save_placeholder(filing, atype))
        return results

    async def run_full_analysis(self, filing) -> list[AnalysisResult]:
        """全4タイプの定型分析を逐次実行する (ADR-004: extractor + LLM 4 回)."""
        filing = await self._ensure_extractor_content(filing)
        try:
            sections = await self._section_extractor.extract(filing)
        except ExtractionInputMissingError:
            await self._save_structural_placeholders_for_missing_input(filing)
            raise

        results: list[AnalysisResult] = []
        for atype in ANALYSIS_TYPE_NAMES:
            outcome = await self._process_one(filing, atype, sections)
            if outcome.kind == "error":
                if outcome.cause is None:
                    # Chapter just missing (not a runtime failure). Match the
                    # streaming UX: log and continue so the 3 healthy chapters
                    # still come back.
                    logger.warning(
                        "filing %d: %s chapter extraction failed (filing_type=%s)",
                        filing.id, atype, filing.filing_type,
                    )
                    continue
                # Runtime failure (LLM / cache / save): CLI semantics demand
                # fail-fast, so bubble the original exception.
                raise outcome.cause
            if outcome.result is not None:
                results.append(outcome.result)

        return results

    async def ask_question(self, filing, question: str) -> QueryResult:
        """自由質問を実行し、結果を Q&A 履歴に永続化する"""
        if self._pageindex is None:
            raise PageIndexDisabledError(
                "pageindex.enabled=false; ask_question は無効化されています"
            )
        logger.info("RAG Q&A for filing %d: %s", filing.id, question[:50])

        filing = await self._ensure_filing_content(filing)
        tree = await self._pageindex.get_or_create_index(filing)
        pdf_path = Path(filing.storage_path) / "converted.pdf"

        result = await self._pageindex.query(tree, question, pdf_path)

        if self._qa_history_repo is not None:
            try:
                await self._persist_qa_history(filing, question, result)
            except Exception:
                logger.exception("Failed to persist RAG Q&A history; answer is still returned")

        return result

    async def _persist_qa_history(
        self, filing, question: str, result: QueryResult,
    ) -> None:
        """Persist Q&A history without letting a failed flush poison the caller session."""
        if self._qa_history_repo is None:
            return

        async def add_history() -> None:
            await self._qa_history_repo.add(
                company_id=filing.company_id,
                filing_id=filing.id,
                question=question,
                answer=result.answer or "",
                source_pages=list(result.source_pages or []),
                source_sections=list(result.source_sections or []),
                model_name=result.model,
                confidence=result.confidence,
            )

        session = self._qa_history_repo.session
        if isinstance(session, AsyncSession):
            async with session.begin_nested():
                await add_history()
            return

        await add_history()

    async def get_qa_history(
        self, company_id: str, *, limit: int = 50,
    ) -> list[dict]:
        """企業ごとの Q&A 履歴を新しい順で返す"""
        if self._qa_history_repo is None:
            return []
        from stock_analyze_system.repositories.rag_qa_history import RagQaHistoryRepository
        rows = await self._qa_history_repo.list_by_company(company_id, limit=limit)
        return [RagQaHistoryRepository.to_dict(r) for r in rows]

    async def get_index_status(self, company_id: str) -> list[dict]:
        """企業のインデックス構築状態を返す"""
        if self._pageindex is None:
            raise PageIndexDisabledError(
                "pageindex.enabled=false; get_index_status は無効化されています"
            )
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
