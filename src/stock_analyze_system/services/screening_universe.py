"""Screening universe / enrichment write service."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.screening import ScreeningRepository

logger = logging.getLogger(__name__)


@dataclass
class RefreshUniverseResult:
    fetched: int
    inserted: int
    updated: int
    skipped: int


@dataclass
class EnrichResult:
    eligible: int
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    elapsed_seconds: float


class ScreeningUniverseService:
    """SEC universe ingestion + Yahoo enrichment (write 系)."""

    def __init__(
        self,
        screening_repo: ScreeningRepository,
        company_repo: CompanyRepository,
        sec_client: SecEdgarClient,
        yahoo_client: YahooFinanceClient,
    ):
        self._screening_repo = screening_repo
        self._company_repo = company_repo
        self._sec = sec_client
        self._yahoo = yahoo_client

    async def refresh_universe(self) -> RefreshUniverseResult:
        """SEC company_tickers_exchange.json を取り込み companies へ bulk upsert.

        既存行の `accounting_standard` は上書きしない (新規 insert 時のみ default
        US-GAAP を入れる)。 ticker/name 空 entry は skip + warn。
        """
        entries = await self._sec.list_universe()
        existing_ids = await self._company_repo.find_existing_ids(
            [self._make_id(e) for e in entries if e["ticker"]],
        )
        rows_insert: list[dict] = []
        rows_update: list[dict] = []
        skipped = 0
        seen_ids: set[str] = set()
        for entry in entries:
            ticker = (entry.get("ticker") or "").strip()
            name = (entry.get("name") or "").strip()
            if not ticker or not name:
                logger.warning(
                    "screening universe: skip entry ticker=%r name=%r cik=%s",
                    ticker, name, entry.get("cik"),
                )
                skipped += 1
                continue
            cid = self._make_id(entry)
            if cid in seen_ids:
                # 同 SEC payload 内の重複は無視
                continue
            seen_ids.add(cid)
            row = {
                "id": cid,
                "ticker": ticker.upper(),
                "name": name,
                "market": (entry.get("exchange") or "UNKNOWN") or "UNKNOWN",
                "cik": entry.get("cik"),
            }
            if cid in existing_ids:
                # accounting_standard は ON CONFLICT DO UPDATE の set_ に含めないが
                # SQLite は INSERT 行でも NOT NULL を検証するため placeholder を入れる。
                # ON CONFLICT DO UPDATE では update_columns に含まれないので上書きされない。
                row["accounting_standard"] = "US-GAAP"
                rows_update.append(row)
            else:
                row["accounting_standard"] = "US-GAAP"
                rows_insert.append(row)

        if rows_insert:
            await self._company_repo._bulk_upsert_native(
                rows_insert,
                index_elements=["id"],
                update_columns=[],   # insert-only (既存衝突は ON CONFLICT DO NOTHING)
            )
        if rows_update:
            await self._company_repo._bulk_upsert_native(
                rows_update,
                index_elements=["id"],
                update_columns=["ticker", "name", "market", "cik"],
            )
        await self._screening_repo._session.commit()

        return RefreshUniverseResult(
            fetched=len(entries),
            inserted=len(rows_insert),
            updated=len(rows_update),
            skipped=skipped,
        )

    async def enrich_with_yahoo(
        self,
        limit: int | None = None,
        stale_hours: int | None = 24,
        max_concurrency: int = 8,
    ) -> EnrichResult:
        """eligible 全件の ScreeningCache を Yahoo v7 batch API で更新.

        - ティッカー一覧を Yahoo batch API に一括送信 (1000 銘柄/リクエスト)
        - 取得結果を screening_cache に一括 upsert
        - 一括 upsert 失敗時は個別 upsert_cache にフォールバック (R7)
        - max_concurrency は batch mode では無視 (API 互換のため残存)
        """
        eligible = await self._screening_repo.list_eligible_for_enrich(
            stale_hours=stale_hours, limit=limit,
        )
        logger.info(
            "enrich start (batch mode): eligible=%d limit=%s",
            len(eligible), limit,
        )
        t0 = time.perf_counter()

        if not eligible:
            return self._empty_enrich_result(0, 0, t0)

        unique_tickers = list(dict.fromkeys(tk for _, tk in eligible))

        try:
            batch_results = await self._yahoo.get_screening_info_batch(unique_tickers)
        except Exception as exc:  # noqa: BLE001
            logger.error("yahoo batch fetch failed: %s", exc, exc_info=exc)
            return self._empty_enrich_result(len(eligible), len(eligible), t0)

        payloads: list[tuple[str, dict]] = []
        skipped = 0
        for cid, ticker in eligible:
            data = batch_results.get(ticker)
            if not data:
                skipped += 1
                continue
            payloads.append((cid, data))

        if not payloads:
            return self._empty_enrich_result(len(eligible), skipped, t0)

        succeeded = 0
        failed = 0
        try:
            await self._screening_repo.bulk_upsert_cache(payloads)
            await self._screening_repo._session.commit()
            succeeded = len(payloads)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "bulk upsert failed (%s), falling back to individual upserts",
                exc, exc_info=exc,
            )
            await self._screening_repo._session.rollback()
            for cid, data in payloads:
                try:
                    await self._screening_repo.upsert_cache(cid, data)
                    await self._screening_repo._session.commit()
                    succeeded += 1
                except Exception as inner_exc:  # noqa: BLE001
                    await self._screening_repo._session.rollback()
                    logger.warning(
                        "individual upsert %s failed: %s",
                        cid, inner_exc, exc_info=inner_exc,
                    )
                    failed += 1

        elapsed = time.perf_counter() - t0
        logger.info(
            "enrich done (batch mode): succeeded=%d failed=%d skipped=%d elapsed=%.2fs",
            succeeded, failed, skipped, elapsed,
        )
        return EnrichResult(
            eligible=len(eligible),
            attempted=len(eligible),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            elapsed_seconds=elapsed,
        )

    @staticmethod
    def _empty_enrich_result(
        eligible_count: int, skipped: int, t0: float,
    ) -> EnrichResult:
        return EnrichResult(
            eligible=eligible_count,
            attempted=eligible_count,
            succeeded=0,
            failed=0,
            skipped=skipped,
            elapsed_seconds=time.perf_counter() - t0,
        )

    @staticmethod
    def _make_id(entry: dict) -> str:
        return f"US_{(entry.get('ticker') or '').upper().strip()}"
