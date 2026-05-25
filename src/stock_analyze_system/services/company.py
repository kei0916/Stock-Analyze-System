"""企業サービス"""
from __future__ import annotations

import logging

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository

logger = logging.getLogger(__name__)

_US_MARKETS = frozenset({"NYSE", "NASDAQ", "AMEX", "OTC"})
_JP_MARKETS = frozenset({"TSE_PRIME", "TSE_STANDARD", "TSE_GROWTH", "TSE"})
_SEC_EXCHANGE_MARKET_MAP = {
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "NYSE AMERICAN": "AMEX",
    "NYSE MKT": "AMEX",
    "OTC": "OTC",
}


def _normalize_cik(cik: str) -> str:
    return str(int(cik)).zfill(10)


def _normalize_ticker(ticker: str | None) -> str | None:
    normalized = (ticker or "").strip().upper()
    return normalized or None


def _market_from_sec_exchange(exchange: str | None) -> str:
    raw = (exchange or "").strip()
    if not raw:
        return "SEC"
    upper = raw.upper()
    return _SEC_EXCHANGE_MARKET_MAP.get(upper, raw[:20])


class CompanyService:
    """企業の登録・検索サービス"""

    def __init__(self, company_repo: CompanyRepository):
        self._repo = company_repo

    async def register_company(self, data: dict) -> Company:
        """企業を登録または更新する。

        Args:
            data: 登録データ。必須キーは `market` と `name`。
                  `ticker` / `security_code` / `sector` / `cik` / `edinet_code` /
                  `accounting_standard` / `name_ja` は任意。

        Returns:
            永続化された `Company` モデル。

        Raises:
            ValueError: `build_company_id` が拒絶する不正入力。
        """
        company_id = self.build_company_id(
            ticker=data.get("ticker"),
            security_code=data.get("security_code"),
            market=data["market"],
        )
        filters = {"id": company_id}
        remainder = {
            "ticker": data.get("ticker"),
            "security_code": data.get("security_code"),
            "name": data["name"],
            "name_ja": data.get("name_ja"),
            "market": data["market"],
            "sector": data.get("sector"),
            "accounting_standard": data.get("accounting_standard", "US-GAAP"),
            "cik": data.get("cik"),
            "edinet_code": data.get("edinet_code"),
        }
        company = await self._repo.upsert(filters, remainder)
        logger.info("Registered/updated company %s (%s)", company_id, data["name"])
        return company

    async def register_sec_filer(
        self,
        *,
        cik: str,
        name: str,
        ticker: str | None = None,
        exchange: str | None = None,
    ) -> Company:
        """SEC filing由来の提出企業をCIK/tickerから登録または更新する。"""
        normalized_cik = _normalize_cik(cik)
        normalized_ticker = _normalize_ticker(ticker)
        company_id = (
            f"US_{normalized_ticker}"
            if normalized_ticker
            else f"SEC_{normalized_cik}"
        )

        existing_by_cik = await self._repo.find_by_cik(normalized_cik)
        filters = {"id": existing_by_cik.id if existing_by_cik else company_id}
        remainder = {
            "ticker": normalized_ticker,
            "security_code": None,
            "name": (name or "").strip() or f"CIK {normalized_cik}",
            "name_ja": None,
            "market": _market_from_sec_exchange(exchange),
            "sector": None,
            "accounting_standard": "US-GAAP",
            "cik": normalized_cik,
            "edinet_code": None,
        }
        company = await self._repo.upsert(filters, remainder)
        logger.info("Registered/updated SEC filer %s (%s)", company.id, company.name)
        return company

    async def get_company(self, company_id: str) -> Company | None:
        """ID から `Company` を取得する (存在しなければ None)。"""
        return await self._repo.get_by_id(company_id)

    async def search_companies(self, query: str, limit: int = 20) -> list[Company]:
        """部分一致で企業を検索する。"""
        return await self._repo.search(query, limit=limit)

    async def find_by_identifier(self, query: str) -> Company | None:
        """ticker / security_code / company_id のいずれかで 1 件を特定する。"""
        return await self._repo.find_by_identifier(query)

    async def list_companies(self, **filters: object) -> list[Company]:
        """フィルタに合致する全企業を列挙する。"""
        return await self._repo.list_all(**filters)

    async def count_companies(self, **filters: object) -> int:
        """フィルタに合致する企業数。一覧をロードせずに COUNT(*) で返す。"""
        return await self._repo.count(**filters)

    @staticmethod
    def build_company_id(
        ticker: str | None, security_code: str | None, market: str,
    ) -> str:
        """市場と識別子から企業IDを生成する。

        Args:
            ticker: US 市場の ticker symbol。
            security_code: JP 市場の証券コード。
            market: 市場コード。JP 側は `TSE_PRIME` / `TSE_STANDARD` /
                `TSE_GROWTH` / `TSE`、US 側は `NYSE` / `NASDAQ` / `AMEX` / `OTC`。

        Returns:
            `JP_<security_code>` または `US_<ticker>` 形式の企業ID。

        Raises:
            ValueError: 市場が未知、または必須識別子が不足している場合。
        """
        if market in _JP_MARKETS:
            if security_code is None:
                raise ValueError("security_code is required for JP markets")
            return f"JP_{security_code}"
        if market in _US_MARKETS:
            if ticker is None:
                raise ValueError("ticker is required for US markets")
            return f"US_{ticker}"
        raise ValueError(f"Unknown market: {market}")

    @staticmethod
    def is_us_market(company_id: str) -> bool:
        """`company_id` が US マーケット企業 (`US_` 接頭辞) か判定する。"""
        return company_id.startswith("US_")

    @staticmethod
    def resolve_yf_ticker(company: Company) -> str | None:
        """Yahoo Finance で使用可能な ticker 文字列を解決する。

        Args:
            company: 対象企業。

        Returns:
            US 市場なら `company.ticker`、JP 市場なら `<security_code>.T`。
            解決不能なら None。
        """
        if company.id.startswith("US_"):
            return company.ticker
        return f"{company.security_code}.T" if company.security_code else None
