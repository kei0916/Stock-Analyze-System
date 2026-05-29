"""filings download の sync + content fetch E2E テスト。"""
from __future__ import annotations

import argparse
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from stock_analyze_system.cli.container import setup_services
from stock_analyze_system.cli.filings import handle
from stock_analyze_system.models.base import Base, get_session
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.shared.clients import ClientBundle
from tests.integration.conftest import build_test_config


class _MockSecClient:
    def __init__(
        self,
        *,
        records: list[dict] | None = None,
        html_responses: list[str | Exception] | None = None,
    ) -> None:
        self.list_calls: list[tuple[str, int]] = []
        self.url_calls: list[tuple[str, str]] = []
        self.html_calls: list[str] = []
        self._records = records or [
            {
                "accessionNumber": "0000320193-24-000123",
                "form": "10-K",
                "filingDate": "2024-11-01",
                "reportDate": "2024-09-28",
                "primaryDocument": "aapl-20240928.htm",
            },
        ]
        self._html_responses = html_responses or [
            "<html><body>10-K content</body></html>",
        ]

    async def list_filings(self, cik: str, max_years: int = 2) -> list[dict]:
        self.list_calls.append((cik, max_years))
        return self._records

    async def get_primary_document_url(self, cik: str, accession_no: str) -> str:
        self.url_calls.append((cik, accession_no))
        primary_document = next(
            r["primaryDocument"]
            for r in self._records
            if r["accessionNumber"] == accession_no
        )
        return (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            f"{accession_no.replace('-', '')}/{primary_document}"
        )

    async def get_filing_html(self, url: str) -> str:
        self.html_calls.append(url)
        response = self._html_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.integration
class TestFilingsDownloadE2E:
    async def test_download_syncs_metadata_and_fetches_content(
        self, session, tmp_path, capsys,
    ):
        sec_client = _MockSecClient()
        config = build_test_config(pageindex_enabled=False)
        config.filings.base_path = str(tmp_path / "filings")
        services = await setup_services(
            session,
            config,
            clients=ClientBundle(
                sec=sec_client,
                edinet=object(),
                yahoo=object(),
                fmp=object(),
            ),
        )
        await services.company_service.register_company({
            "ticker": "INTGR",
            "name": "Integration Corp",
            "market": "NASDAQ",
            "accounting_standard": "US-GAAP",
            "cik": "0000320193",
        })

        await handle(
            argparse.Namespace(action="download", json=False, company_id="US_INTGR"),
            services,
        )

        out = capsys.readouterr().out
        assert "Synced 1 filing metadata record(s)" in out
        assert "Fetched content: 1 new, 0 already-present, 0 failed." in out
        assert sec_client.list_calls == [("0000320193", 2)]
        assert sec_client.url_calls == [("0000320193", "0000320193-24-000123")]
        assert len(sec_client.html_calls) == 1

        filings = await services.filing_service.list_filings("US_INTGR")
        assert len(filings) == 1
        assert filings[0].storage_path is not None
        raw_path = Path(filings[0].storage_path) / "raw" / "aapl-20240928.htm"
        assert raw_path.read_text() == "<html><body>10-K content</body></html>"

    async def test_content_fetch_uses_company_cik_without_lazy_relationship(
        self, tmp_path,
    ):
        sec_client = _MockSecClient()
        config = build_test_config(pageindex_enabled=False)
        config.filings.base_path = str(tmp_path / "filings")
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            async with get_session(engine) as session:
                session.add(Company(
                    id="US_INTGR", ticker="INTGR", name="Integration Corp",
                    market="NASDAQ", accounting_standard="US-GAAP",
                    cik="0000320193",
                ))
                session.add(Filing(
                    id=1,
                    company_id="US_INTGR",
                    source="SEC",
                    filing_type="10-K",
                    period_type="annual",
                    fiscal_year=2024,
                    accession_no="0000320193-24-000123",
                ))

            async with get_session(engine) as session:
                services = await setup_services(
                    session,
                    config,
                    clients=ClientBundle(
                        sec=sec_client,
                        edinet=object(),
                        yahoo=object(),
                        fmp=object(),
                    ),
                )
                filing = await services.filing_service.get_filing_by_id(1)
                assert filing is not None
                assert "company" not in filing.__dict__

                await services.filing_content_service.ensure_content(filing)

                assert sec_client.url_calls == [
                    ("0000320193", "0000320193-24-000123"),
                ]
                assert filing.storage_path is not None
                assert list((Path(filing.storage_path) / "raw").glob("*.htm"))
        finally:
            await engine.dispose()

    async def test_partial_failure_returns_nonzero_but_commits_success(
        self, tmp_path, capsys,
    ):
        records = [
            {
                "accessionNumber": "0000320193-24-000123",
                "form": "10-K",
                "filingDate": "2024-11-01",
                "reportDate": "2024-09-28",
                "primaryDocument": "aapl-20240928.htm",
            },
            {
                "accessionNumber": "0000320193-25-000001",
                "form": "10-Q",
                "filingDate": "2025-02-01",
                "reportDate": "2024-12-28",
                "primaryDocument": "aapl-20241228.htm",
            },
        ]
        fetch_error = httpx.HTTPStatusError(
            "500",
            request=httpx.Request("GET", "http://sec.test/filing"),
            response=httpx.Response(500),
        )
        sec_client = _MockSecClient(
            records=records,
            html_responses=[
                "<html><body>10-K content</body></html>",
                fetch_error,
            ],
        )
        config = build_test_config(pageindex_enabled=False)
        config.filings.base_path = str(tmp_path / "filings")
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            async with get_session(engine) as session:
                services = await setup_services(
                    session,
                    config,
                    clients=ClientBundle(
                        sec=sec_client,
                        edinet=object(),
                        yahoo=object(),
                        fmp=object(),
                    ),
                )
                await services.company_service.register_company({
                    "ticker": "INTGR",
                    "name": "Integration Corp",
                    "market": "NASDAQ",
                    "accounting_standard": "US-GAAP",
                    "cik": "0000320193",
                })

                result = await handle(
                    argparse.Namespace(
                        action="download",
                        json=False,
                        company_id="US_INTGR",
                    ),
                    services,
                )

                assert result == 1

            async with get_session(engine) as session:
                services = await setup_services(
                    session,
                    config,
                    clients=ClientBundle(
                        sec=sec_client,
                        edinet=object(),
                        yahoo=object(),
                        fmp=object(),
                    ),
                )
                filings = await services.filing_service.list_filings("US_INTGR")
                by_accession = {f.accession_no: f for f in filings}
                assert set(by_accession) == {
                    "0000320193-24-000123",
                    "0000320193-25-000001",
                }
                stored = [f for f in filings if f.storage_path is not None]
                unstored = [f for f in filings if f.storage_path is None]
                assert len(stored) == 1
                assert len(unstored) == 1
                assert list((Path(stored[0].storage_path) / "raw").glob("*.htm"))
        finally:
            await engine.dispose()

        err = capsys.readouterr().err
        assert "filing_id=" in err
        assert "SEC fetch failed" in err
