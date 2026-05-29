# src/stock_analyze_system/ingestion/sec_edgar.py
"""SEC EDGAR API クライアント (async)"""
from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import date as date_type
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from stock_analyze_system.ingestion.base import BaseClient
from stock_analyze_system.models.enums import FilingType

logger = logging.getLogger(__name__)

_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_DAILY_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/daily-index/"
    "{year}/QTR{quarter}/master.{yyyymmdd}.idx"
)
_SEC_MAX_RATE_RPS = 10.0


def _quarter_for_date(filing_date: date_type) -> int:
    """Return SEC quarter number for a calendar date."""
    return ((filing_date.month - 1) // 3) + 1


def _daily_index_url(filing_date: date_type) -> str:
    """Build SEC daily master index URL for a filing date."""
    return _DAILY_INDEX_URL.format(
        year=filing_date.year,
        quarter=_quarter_for_date(filing_date),
        yyyymmdd=filing_date.strftime("%Y%m%d"),
    )


def _normalize_cik(raw: str) -> str:
    """Normalize a CIK value to SEC's 10-digit string form."""
    return str(int(raw)).zfill(10)


def _accession_from_filename(filename: str) -> str:
    """Extract accession number from a daily-index filename."""
    return PurePosixPath(filename).stem


class SecEdgarClient(BaseClient):
    """SEC EDGAR 公開API クライアント"""

    def __init__(self, email: str, rate: float = 10.0):
        effective_rate = min(float(rate), _SEC_MAX_RATE_RPS)
        super().__init__(
            rate=effective_rate,
            initial_allowance=1.0,
            headers={"User-Agent": f"Stock-Analyze-System {email}"},
        )
        self._ticker_cik_map: dict[str, str] | None = None

    async def get_company_facts(self, cik: str) -> dict:
        """企業の XBRL Company Facts を取得する。

        Args:
            cik: 企業の CIK 番号 (ゼロパディング不要)。

        Returns:
            SEC EDGAR の companyfacts JSON をパースした dict。
            トップレベルキーに ``entityName`` / ``facts`` 等を含む。

        Raises:
            ApiConnectionError: レートリミット超過または接続失敗によりリトライ上限に達した場合。
            httpx.HTTPStatusError: 404 等の非リトライ対象ステータスが返された場合。
        """
        cik = cik.zfill(10)
        url = _COMPANY_FACTS_URL.format(cik=cik)
        resp = await self._get(url)
        return resp.json()

    async def get_submissions(self, cik: str) -> dict:
        """企業の提出書類情報を取得する (ページネーション対応)。

        ``filings.files`` に追加ページが存在する場合、各ページを順にフェッチして
        ``filings.recent`` の各リストに結合する。

        Args:
            cik: 企業の CIK 番号 (ゼロパディング不要)。

        Returns:
            SEC EDGAR の submissions JSON をパースした dict。
            ``filings.recent`` に全ページ分のファイリング情報が結合されている。

        Raises:
            ApiConnectionError: レートリミット超過または接続失敗によりリトライ上限に達した場合。
            httpx.HTTPStatusError: 404 等の非リトライ対象ステータスが返された場合。
        """
        cik = cik.zfill(10)
        url = _SUBMISSIONS_URL.format(cik=cik)
        resp = await self._get(url)
        data = resp.json()

        # ページネーション: files[] の追加ページもフェッチして recent に結合
        additional_files = data.get("filings", {}).get("files", [])
        for file_info in additional_files:
            page_url = f"https://data.sec.gov/submissions/{file_info['name']}"
            page_resp = await self._get(page_url)
            page_data = page_resp.json()
            recent = data["filings"]["recent"]
            for key in recent:
                if key in page_data:
                    recent[key].extend(page_data[key])

        return data

    async def get_filing_html(self, url: str) -> str:
        """指定 URL からファイリングの HTML テキストを取得する。

        Args:
            url: ファイリングドキュメントの完全 URL。

        Returns:
            レスポンスボディの文字列 (HTML)。

        Raises:
            ApiConnectionError: レートリミット超過または接続失敗によりリトライ上限に達した場合。
            httpx.HTTPStatusError: 404 等の非リトライ対象ステータスが返された場合。
        """
        resp = await self._get(url)
        return resp.text

    async def list_filings(
        self,
        cik: str,
        form_types: list[str] | None = None,
        max_years: int = 10,
    ) -> list[dict]:
        """フォームタイプと年数でフィルタしたファイリング一覧を取得する。

        Args:
            cik: 企業の CIK 番号 (ゼロパディング不要)。
            form_types: 対象フォームタイプのリスト。``None`` の場合は
                10-K / 10-Q / 20-F / 6-K を対象とする。
            max_years: 取得対象の最大年数。現在日時から遡った cutoff より古い
                ファイリングは除外される。デフォルトは 10。

        Returns:
            ファイリング情報の dict リスト。各 dict のキー:
            ``form`` / ``filingDate`` / ``reportDate`` / ``accessionNumber`` /
            ``primaryDocument`` / ``primaryDocDescription`` / ``documentUrl``。

        Raises:
            ApiConnectionError: レートリミット超過または接続失敗によりリトライ上限に達した場合。
            httpx.HTTPStatusError: 404 等の非リトライ対象ステータスが返された場合。
        """
        if form_types is None:
            form_types = [FilingType.TEN_K, FilingType.TEN_Q, FilingType.TWENTY_F, FilingType.SIX_K]

        data = await self.get_submissions(cik)
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        primary_descs = recent.get("primaryDocDescription", [])

        cutoff = datetime.now() - timedelta(days=max_years * 365)
        cik_num = cik.lstrip("0") or "0"
        results = []

        for form, filing_date, report_date, acc_no, primary_doc, desc in zip(
            forms, filing_dates, report_dates,
            accession_numbers, primary_docs, primary_descs,
        ):
            if form not in form_types:
                continue
            try:
                if datetime.strptime(filing_date, "%Y-%m-%d") < cutoff:
                    continue
            except ValueError:
                continue

            acc_clean = acc_no.replace("-", "")
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_num}/{acc_clean}/{primary_doc}"
            )
            results.append({
                "form": form,
                "filingDate": filing_date,
                "reportDate": report_date,
                "accessionNumber": acc_no,
                "primaryDocument": primary_doc,
                "primaryDocDescription": desc,
                "documentUrl": doc_url,
            })

        return results

    async def list_daily_filings(
        self,
        filing_date: date_type,
        form_types: Collection[str] | None = None,
    ) -> list[dict]:
        """SEC daily master index rows for one SEC filingDate.

        Args:
            filing_date: SEC filing date to fetch.
            form_types: Optional form filter. If omitted, all forms in the
                daily index are returned.

        Returns:
            Normalized filing records compatible with FilingSyncService.
        """
        resp = await self._get(_daily_index_url(filing_date))
        allowed_forms = set(form_types) if form_types is not None else None
        target_date = filing_date.isoformat()
        rows: list[dict] = []
        in_table = False

        for line in resp.text.splitlines():
            if not in_table:
                if line.startswith("----"):
                    in_table = True
                continue
            if not line.strip():
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 5:
                logger.warning("invalid daily filing row: %s", line)
                continue
            cik_raw, company_name, form, filed_at, filename = parts
            if filed_at != target_date:
                continue
            if allowed_forms is not None and form not in allowed_forms:
                continue
            try:
                cik = _normalize_cik(cik_raw)
            except ValueError:
                logger.warning("invalid daily filing row: %s", line)
                continue
            accession_no = _accession_from_filename(filename)
            if not accession_no:
                logger.warning("invalid daily filing row: %s", line)
                continue
            rows.append({
                "cik": cik,
                "companyName": company_name,
                "form": form,
                "filingDate": filed_at,
                "reportDate": "",
                "accessionNumber": accession_no,
                "primaryDocument": "",
                "primaryDocDescription": "",
                "documentUrl": f"https://www.sec.gov/Archives/{filename}",
            })

        return rows

    async def get_primary_document_url(self, cik: str, accession_no: str) -> str:
        """submissions JSON から指定 accession の primaryDocument の完全 URL を返す。

        Raises:
            ValueError: 該当 accession_no が submissions に存在しない場合。
        """
        cik_padded = cik.zfill(10)
        data = await self.get_submissions(cik_padded)
        recent = data.get("filings", {}).get("recent", {})
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        cik_num = cik_padded.lstrip("0") or "0"
        for acc, doc in zip(accessions, primary_docs):
            if acc == accession_no:
                acc_clean = acc.replace("-", "")
                return (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik_num}/{acc_clean}/{doc}"
                )
        raise ValueError(
            f"accession {accession_no} not found in submissions for CIK {cik_padded}",
        )

    async def search_efts(
        self, query: str, start_date: str = "", end_date: str = "",
    ) -> dict:
        """EFTS 全文検索エンドポイントにクエリを送信する。

        Args:
            query: 検索キーワード。ダブルクォートで囲まれたフレーズ検索として送信される。
            start_date: 検索開始日 (``YYYY-MM-DD`` 形式)。``end_date`` と共に指定した場合のみ有効。
            end_date: 検索終了日 (``YYYY-MM-DD`` 形式)。``start_date`` と共に指定した場合のみ有効。

        Returns:
            EFTS 検索 API のレスポンス JSON をパースした dict。

        Raises:
            ApiConnectionError: レートリミット超過または接続失敗によりリトライ上限に達した場合。
            httpx.HTTPStatusError: 404 等の非リトライ対象ステータスが返された場合。
        """
        url = "https://efts.sec.gov/LATEST/search-index"
        params: dict[str, str] = {"q": f'"{query}"'}
        if start_date and end_date:
            params["dateRange"] = "custom"
            params["startdt"] = start_date
            params["enddt"] = end_date
        resp = await self._get(url, params=params)
        return resp.json()

    async def search_cik(self, ticker: str) -> str | None:
        """ティッカーシンボルに対応する CIK を検索する。

        初回呼び出し時に SEC の company_tickers.json をロードしてキャッシュする。
        以降の呼び出しではキャッシュを参照する。

        Args:
            ticker: 企業のティッカーシンボル (大文字・小文字どちらでも可)。

        Returns:
            10 桁ゼロパディングされた CIK 文字列。ティッカーが見つからない場合は ``None``。

        Raises:
            ApiConnectionError: ticker マップのロード中に接続失敗した場合。
            httpx.HTTPStatusError: ticker マップのロード中に非リトライ対象ステータスが返された場合。
        """
        if self._ticker_cik_map is None:
            await self._load_ticker_map()
        cik = self._ticker_cik_map.get(ticker.upper())
        if cik is None:
            return None
        return cik.zfill(10)

    async def _load_ticker_map(self) -> None:
        """SEC company_tickers.json をロード"""
        resp = await self._get(_COMPANY_TICKERS_URL)
        data = resp.json()
        self._ticker_cik_map = {}
        for entry in data.values():
            self._ticker_cik_map[entry["ticker"].upper()] = str(entry["cik_str"])

    async def list_universe(self) -> list[dict]:
        """SEC 全 ticker (10-K/20-F filer) の (ticker, cik, name, exchange) を返す.

        Source: https://www.sec.gov/files/company_tickers_exchange.json
        cik は 10 桁 zero-padded で正規化する。
        """
        resp = await self._get(_COMPANY_TICKERS_EXCHANGE_URL)
        payload = resp.json()
        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        idx = {f: i for i, f in enumerate(fields)}
        out: list[dict] = []
        for row in rows:
            cik_raw = row[idx["cik"]]
            out.append({
                "ticker": str(row[idx["ticker"]] or ""),
                "cik": f"{int(cik_raw):010d}",
                "name": str(row[idx["name"]] or ""),
                "exchange": str(row[idx["exchange"]] or ""),
            })
        return out
