"""Filing 本体 (HTML/PDF) のフェッチ・保存サービス"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from stock_analyze_system.exceptions import ContentFetchError, ContentNotFoundError
from stock_analyze_system.services.filing import FilingService

if TYPE_CHECKING:
    from stock_analyze_system.config import FilingsConfig
    from stock_analyze_system.ingestion.edinet import EdinetClient
    from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
    from stock_analyze_system.repositories.filing import FilingRepository

logger = logging.getLogger(__name__)


def filing_raw_html_exists(path: str | Path | None) -> bool:
    if path is None:
        return False
    raw = Path(path) / "raw"
    if not raw.exists():
        return False
    for pattern in ("*.html", "*.htm"):
        if any(raw.glob(pattern)):
            return True
    return False


def filing_content_exists(path: str | Path | None) -> bool:
    if path is None:
        return False
    base = Path(path)
    if (base / "converted.pdf").exists():
        return True
    return filing_raw_html_exists(base)


def filing_content_exists_for_source(source: str | None, path: str | Path | None) -> bool:
    if (source or "").upper() == "SEC":
        return filing_raw_html_exists(path)
    return filing_content_exists(path)


@dataclass
class FetchSummary:
    """fetch_for_company の集計結果"""
    fetched: int = 0
    skipped: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)


class FilingContentService:
    """SEC HTML / EDINET PDF を fetch し、storage_path を確定するサービス"""

    def __init__(
        self,
        filing_repo: FilingRepository,
        sec_client: SecEdgarClient,
        edinet_client: EdinetClient,
        config: FilingsConfig,
    ):
        self._repo = filing_repo
        self._sec = sec_client
        self._edinet = edinet_client
        self._base_path = Path(config.base_path)

    async def ensure_content(self, filing):
        """filing.storage_path が空 (または実体不在) なら fetch & save。
        既に揃っていれば no-op。常に最新の filing を返す。"""
        if filing_content_exists_for_source(filing.source, filing.storage_path):
            return filing

        target_dir = self._compute_target_dir(filing)

        # DB・ファイル不整合の自動修復: storage_path=NULL だが
        # target_dir にファイルが既存する場合、DB を復元して再ダウンロードを回避
        if filing_content_exists_for_source(filing.source, str(target_dir)):
            content_hash = self._compute_dir_hash(target_dir)
            await self._repo.update_storage(
                filing_id=filing.id,
                storage_path=str(target_dir),
                content_hash=content_hash,
            )
            filing.storage_path = str(target_dir)
            filing.content_hash = content_hash
            return filing

        target_dir.mkdir(parents=True, exist_ok=True)

        source = (filing.source or "").upper()
        if source == "SEC":
            data = await self._fetch_sec(filing, target_dir)
        elif source == "EDINET":
            data = await self._fetch_edinet(filing, target_dir)
        else:
            raise NotImplementedError(f"unsupported filing source: {source!r}")

        content_hash = hashlib.sha256(data).hexdigest()
        await self._repo.update_storage(
            filing_id=filing.id,
            storage_path=str(target_dir),
            content_hash=content_hash,
        )
        filing.storage_path = str(target_dir)
        filing.content_hash = content_hash
        return filing

    async def fetch_for_company(self, company_id: str) -> FetchSummary:
        """企業の storage_path 未設定 filing を直列で fetch する。"""
        all_filings = await self._repo.list_filings(company_id)
        summary = FetchSummary()
        for filing in all_filings:
            if filing_content_exists_for_source(filing.source, filing.storage_path):
                summary.skipped += 1
                continue
            try:
                await self.ensure_content(filing)
                summary.fetched += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "content fetch failed for filing %d: %s", filing.id, exc,
                )
                summary.failed.append((filing.id, str(exc)))
        return summary

    # ---- private helpers ----

    def _compute_target_dir(self, filing) -> Path:
        source = (filing.source or "").upper()
        if source == "SEC":
            key = filing.accession_no
            if not key:
                raise ValueError(
                    f"filing {filing.id} missing accession_no; cannot fetch SEC content",
                )
        elif source == "EDINET":
            key = filing.doc_id
            if not key:
                raise ValueError(
                    f"filing {filing.id} missing doc_id; cannot fetch EDINET content",
                )
        else:
            raise NotImplementedError(f"unsupported filing source: {source!r}")

        return FilingService.get_storage_path(
            base_path=str(self._base_path),
            source=source,
            company_id=filing.company_id,
            fiscal_year=filing.fiscal_year,
            period_type=str(filing.period_type),
            filing_type=str(filing.filing_type),
            key=key,
        )

    async def _fetch_sec(self, filing, target_dir: Path) -> bytes:
        cik = await self._get_company_cik(filing)
        if not cik:
            raise ValueError(
                f"filing {filing.id} company has no CIK; cannot fetch SEC content",
            )
        try:
            url = await self._sec.get_primary_document_url(cik, filing.accession_no)
        except ValueError as exc:
            raise ContentNotFoundError(
                f"SEC primary document not found for {filing.accession_no}",
            ) from exc

        try:
            html = await self._sec.get_filing_html(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ContentNotFoundError(
                    f"SEC primary document not found for {filing.accession_no}",
                ) from exc
            raise ContentFetchError(
                f"SEC fetch failed for {filing.accession_no}: {exc}",
            ) from exc

        filename = self._sanitize_filename(url.rsplit("/", 1)[-1] or "filing.htm")
        raw_dir = target_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = raw_dir / filename
        body = html.encode("utf-8")
        out_path.write_bytes(body)
        return body

    async def _fetch_edinet(self, filing, target_dir: Path) -> bytes:
        try:
            data = await self._edinet.download_pdf(filing.doc_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ContentNotFoundError(
                    f"EDINET PDF not found for doc {filing.doc_id}",
                ) from exc
            raise ContentFetchError(
                f"EDINET fetch failed for {filing.doc_id}: {exc}",
            ) from exc
        out_path = target_dir / "converted.pdf"
        out_path.write_bytes(data)
        return data

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        cleaned = name.replace("..", "_").replace("/", "_").replace("\\", "_")
        return cleaned or "filing.htm"

    @staticmethod
    def _compute_dir_hash(target_dir: Path) -> str:
        """target_dir 内の既存ファイルから SHA-256 ハッシュを計算する。
        raw/ 内の HTML を優先し、次に直下の HTML、最後に converted.pdf を対象とする。
        """
        raw_dir = target_dir / "raw"
        files: list[Path] = []
        if raw_dir.exists():
            files.extend(sorted(raw_dir.glob("*.html")))
            files.extend(sorted(raw_dir.glob("*.htm")))
        if not files:
            files.extend(sorted(target_dir.glob("*.html")))
            files.extend(sorted(target_dir.glob("*.htm")))
        if not files:
            pdf = target_dir / "converted.pdf"
            if pdf.exists():
                files = [pdf]
        if not files:
            return ""

        hasher = hashlib.sha256()
        for f in files:
            hasher.update(f.read_bytes())
        return hasher.hexdigest()

    async def _get_company_cik(self, filing) -> str | None:
        company = getattr(filing, "__dict__", {}).get("company")
        cik = getattr(company, "cik", None) if company is not None else None
        if cik:
            return cik
        cik, _edinet_code = await self._repo.get_company_identifiers(filing.company_id)
        return cik
