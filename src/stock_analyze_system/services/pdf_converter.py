"""HTML→PDF変換 (weasyprint, asyncio.to_thread)"""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

import weasyprint
from weasyprint.urls import URLFetcher


_ALLOWED_PROTOCOLS = {"file", "data"}


def _resolve_local_url(url: str, *, base_dir: Path) -> Path:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()

    if scheme and scheme != "file":
        raise ValueError(f"Disallowed URL scheme: {scheme}")
    if not scheme and parts.netloc:
        raise ValueError("Disallowed URL scheme: relative-network")
    if scheme == "file" and parts.netloc not in ("", "localhost"):
        raise ValueError("Disallowed file host")

    if scheme == "file":
        path = Path(url2pathname(unquote(parts.path)))
    else:
        path = base_dir / url2pathname(unquote(parts.path))
    return path.resolve()


def _build_safe_url_fetcher(*, fetch_base_dir: Path, allowed_root: Path):
    fetch_base_dir = fetch_base_dir.resolve()
    allowed_root = allowed_root.resolve()
    base_fetcher = URLFetcher(allowed_protocols=_ALLOWED_PROTOCOLS)

    def _fetch(url: str):
        if urlsplit(url).scheme.lower() == "data":
            return base_fetcher.fetch(url)
        resolved = _resolve_local_url(url, base_dir=fetch_base_dir)
        try:
            resolved.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(f"Resolved path is outside allowed root: {resolved}") from exc
        return base_fetcher.fetch(resolved.as_uri())

    return _fetch


class PdfConverter:
    """SEC/EDINETファイリングHTMLをPDFに変換する"""

    async def convert(
        self,
        html_path: Path,
        output_path: Path,
        *,
        allowed_root: Path | None = None,
    ) -> Path:
        """HTMLファイルをPDFに変換する"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fetch_base_dir = html_path.parent.resolve()
        fetch_root = (allowed_root or fetch_base_dir).resolve()
        url_fetcher = _build_safe_url_fetcher(
            fetch_base_dir=fetch_base_dir,
            allowed_root=fetch_root,
        )

        def _convert() -> None:
            doc = weasyprint.HTML(
                filename=str(html_path),
                url_fetcher=url_fetcher,
            )
            doc.write_pdf(str(output_path))

        await asyncio.to_thread(_convert)
        return output_path

    async def get_or_convert(self, filing) -> Path:
        """変換済みPDFがあればそれを返し、なければHTML→PDF変換する"""
        base = Path(filing.storage_path)
        pdf_path = base / "converted.pdf"

        if pdf_path.exists():
            return pdf_path

        raw_dir = base / "raw"
        html_files: list[Path] = []
        if raw_dir.exists():
            html_files.extend(sorted(raw_dir.glob("*.html")))
            html_files.extend(sorted(raw_dir.glob("*.htm")))
        if not html_files:
            html_files.extend(sorted(base.glob("*.html")))
            html_files.extend(sorted(base.glob("*.htm")))
        if not html_files:
            raise FileNotFoundError(
                f"No HTML files found for filing at {base}"
            )

        return await self.convert(html_files[0], pdf_path, allowed_root=base)
