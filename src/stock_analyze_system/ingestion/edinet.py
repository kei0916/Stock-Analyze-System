# src/stock_analyze_system/ingestion/edinet.py
"""EDINET API v2 クライアント (async)"""
from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from stock_analyze_system.ingestion.base import BaseClient

logger = logging.getLogger(__name__)

DOC_TYPE_YUHO = "120"


class EdinetClient(BaseClient):
    """EDINET API v2 クライアント"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.edinet-fsa.go.jp/api/v2",
        rate_limit_interval: float = 5.0,
    ):
        super().__init__(rate=1.0, interval=rate_limit_interval)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def get_document_list(
        self, date: str, doc_type: str = DOC_TYPE_YUHO,
    ) -> list[dict]:
        """指定日の書類一覧を取得"""
        if not self._api_key:
            logger.warning(
                "EDINET API key is not set. Skipping document list retrieval. "
                "Set EDINET_API_KEY environment variable."
            )
            return []

        url = f"{self._base_url}/documents.json"
        params = {"date": date, "type": 2, "Subscription-Key": self._api_key}
        resp = await self._get(url, params=params)
        data = resp.json()

        results = data.get("results", [])
        filtered = [
            doc for doc in results
            if doc.get("docTypeCode") == doc_type
        ]
        logger.info(
            "EDINET %s: %d documents found, %d matched type %s",
            date, len(results), len(filtered), doc_type,
        )
        return filtered

    async def download_xbrl_zip(
        self, doc_id: str, save_dir: str | Path,
    ) -> Path:
        """XBRLアーカイブをダウンロード・展開"""
        if not self._api_key:
            raise ValueError("EDINET API key is required for document download")

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        url = f"{self._base_url}/documents/{doc_id}"
        params = {"type": 1, "Subscription-Key": self._api_key}
        resp = await self._get(url, params=params)

        zip_path = save_dir / f"{doc_id}.zip"
        zip_path.write_bytes(resp.content)

        extract_dir = save_dir / doc_id
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            # ZIPスリップ・ZIP爆弾防御
            max_size = 500_000_000  # 500MB
            total = 0
            for info in zf.infolist():
                if info.filename.startswith("/") or ".." in info.filename:
                    raise ValueError(f"Unsafe zip member: {info.filename}")
                total += info.file_size
                if total > max_size:
                    raise ValueError("Zip extraction size limit exceeded")
            zf.extractall(extract_dir)
        zip_path.unlink()

        return extract_dir

    async def download_pdf(self, doc_id: str) -> bytes:
        """EDINET 書類本文を PDF (type=2) としてバイト列で取得する。

        Raises:
            ValueError: API key 未設定の場合。
            httpx.HTTPStatusError: 404 / その他のステータスエラー (呼び出し側で
                ContentNotFoundError へ変換する想定)。
        """
        if not self._api_key:
            raise ValueError("EDINET API key is required for document download")

        url = f"{self._base_url}/documents/{doc_id}"
        params = {"type": 2, "Subscription-Key": self._api_key}
        resp = await self._get(url, params=params)
        return resp.content

    async def search_company_filings(
        self,
        edinet_code: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """指定企業のファイリングを日付範囲で検索"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        results: list[dict] = []

        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            try:
                docs = await self.get_document_list(date_str)
                for doc in docs:
                    if doc.get("edinetCode") == edinet_code:
                        results.append(doc)
            except Exception as e:
                logger.warning("EDINET search error for %s: %s", date_str, e)
            current += timedelta(days=1)

        return results
