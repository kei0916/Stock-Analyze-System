"""FilingContentService 単体テスト"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from stock_analyze_system.config import FilingsConfig
from stock_analyze_system.exceptions import ContentNotFoundError
from stock_analyze_system.services.filing_content import (
    FilingContentService,
)


def make_filing(**overrides):
    base = dict(
        id=1,
        company_id="US_AAPL",
        source="SEC",
        filing_type="10-K",
        period_type="annual",
        fiscal_year=2024,
        accession_no="0000320193-24-000123",
        doc_id=None,
        storage_path=None,
        content_hash=None,
        company=SimpleNamespace(cik="0000320193", edinet_code=None),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def filing_repo():
    repo = AsyncMock()
    repo.update_storage.return_value = None
    repo.get_company_identifiers.return_value = ("0000320193", None)
    return repo


@pytest.fixture
def sec_client():
    client = AsyncMock()
    client.get_primary_document_url.return_value = (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"
    )
    client.get_filing_html.return_value = "<html><body>aapl 10-K</body></html>"
    return client


@pytest.fixture
def edinet_client():
    client = AsyncMock()
    client.download_pdf.return_value = b"%PDF-1.7 fake"
    return client


@pytest.fixture
def service(filing_repo, sec_client, edinet_client, tmp_path):
    cfg = FilingsConfig(base_path=str(tmp_path))
    return FilingContentService(
        filing_repo=filing_repo,
        sec_client=sec_client,
        edinet_client=edinet_client,
        config=cfg,
    )


class TestEnsureContentSEC:
    async def test_writes_html_and_updates_storage(
        self,
        service,
        filing_repo,
        sec_client,
        tmp_path,
    ):
        filing = make_filing()
        result = await service.ensure_content(filing)

        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        html_files = list((target_dir / "raw").glob("*.htm*"))
        assert len(html_files) == 1
        assert html_files[0].read_text() == "<html><body>aapl 10-K</body></html>"

        filing_repo.update_storage.assert_awaited_once()
        kwargs = filing_repo.update_storage.await_args.kwargs
        assert kwargs["filing_id"] == 1
        assert kwargs["storage_path"] == str(target_dir)
        assert (
            kwargs["content_hash"]
            == hashlib.sha256(
                b"<html><body>aapl 10-K</body></html>",
            ).hexdigest()
        )

        assert result.storage_path == str(target_dir)

    async def test_noop_when_already_present(
        self,
        service,
        filing_repo,
        sec_client,
        tmp_path,
    ):
        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        (target_dir / "raw").mkdir(parents=True)
        (target_dir / "raw" / "aapl-20240928.htm").write_text("present")

        filing = make_filing(storage_path=str(target_dir))
        await service.ensure_content(filing)

        sec_client.get_filing_html.assert_not_called()
        filing_repo.update_storage.assert_not_called()

    async def test_refetches_when_sec_storage_has_only_converted_pdf(
        self,
        service,
        sec_client,
        tmp_path,
    ):
        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        target_dir.mkdir(parents=True)
        (target_dir / "converted.pdf").write_bytes(b"%PDF-1.7 stale")

        filing = make_filing(storage_path=str(target_dir))
        await service.ensure_content(filing)

        sec_client.get_filing_html.assert_awaited_once()
        assert list((target_dir / "raw").glob("*.htm*"))

    async def test_recovers_storage_path_when_file_exists_but_db_is_null(
        self,
        service,
        filing_repo,
        sec_client,
        tmp_path,
    ):
        """DB の storage_path が NULL だがファイルシステムに実体がある場合、DB を復元する"""
        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        (target_dir / "raw").mkdir(parents=True)
        html_content = "<html><body>recovered</body></html>"
        (target_dir / "raw" / "aapl-20240928.htm").write_text(html_content)

        filing = make_filing(storage_path=None)
        result = await service.ensure_content(filing)

        sec_client.get_filing_html.assert_not_called()
        filing_repo.update_storage.assert_awaited_once()
        kwargs = filing_repo.update_storage.await_args.kwargs
        assert kwargs["filing_id"] == 1
        assert kwargs["storage_path"] == str(target_dir)
        assert kwargs["content_hash"] == hashlib.sha256(html_content.encode()).hexdigest()
        assert result.storage_path == str(target_dir)

    async def test_re_fetches_when_storage_path_set_but_file_missing(
        self,
        service,
        sec_client,
        tmp_path,
    ):
        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        target_dir.mkdir(parents=True)  # ディレクトリだけ作って中身なし

        filing = make_filing(storage_path=str(target_dir))
        await service.ensure_content(filing)

        sec_client.get_filing_html.assert_awaited_once()

    async def test_raises_value_error_when_accession_missing(self, service):
        filing = make_filing(accession_no=None)
        with pytest.raises(ValueError, match="accession"):
            await service.ensure_content(filing)

    async def test_converts_missing_primary_document_to_content_not_found(
        self,
        service,
        sec_client,
    ):
        sec_client.get_primary_document_url.side_effect = ValueError(
            "accession A-1 not found in submissions for CIK 0000320193",
        )
        filing = make_filing(accession_no="A-1")

        with pytest.raises(ContentNotFoundError):
            await service.ensure_content(filing)


class TestEnsureContentEdinet:
    async def test_writes_pdf_and_updates_storage(
        self,
        service,
        filing_repo,
        edinet_client,
        tmp_path,
    ):
        filing = make_filing(
            source="EDINET",
            filing_type="annual_report",
            accession_no=None,
            doc_id="S100ABCD",
            company=SimpleNamespace(cik=None, edinet_code="E02144"),
        )
        await service.ensure_content(filing)

        target_dir = tmp_path / "EDINET/US_AAPL/2024/annual/annual_report/S100ABCD"
        assert (target_dir / "converted.pdf").read_bytes() == b"%PDF-1.7 fake"

        filing_repo.update_storage.assert_awaited_once()
        kwargs = filing_repo.update_storage.await_args.kwargs
        assert kwargs["storage_path"] == str(target_dir)

    async def test_raises_value_error_when_doc_id_missing(self, service):
        filing = make_filing(
            source="EDINET",
            accession_no=None,
            doc_id=None,
        )
        with pytest.raises(ValueError, match="doc_id"):
            await service.ensure_content(filing)

    async def test_converts_404_to_content_not_found(
        self,
        service,
        edinet_client,
    ):
        edinet_client.download_pdf.side_effect = httpx.HTTPStatusError(
            "404",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(404),
        )
        filing = make_filing(
            source="EDINET",
            accession_no=None,
            doc_id="S100MISS",
        )
        with pytest.raises(ContentNotFoundError):
            await service.ensure_content(filing)


class TestFetchForCompany:
    async def test_aggregates_results(
        self,
        service,
        filing_repo,
        sec_client,
        tmp_path,
    ):
        present_dir = tmp_path / "present"
        (present_dir / "raw").mkdir(parents=True)
        (present_dir / "raw" / "filing.htm").write_text("present")
        filings = [
            make_filing(id=1, accession_no="A-1"),
            make_filing(id=2, accession_no="A-2", storage_path=str(present_dir)),
            make_filing(id=3, accession_no=None),  # 欠落で失敗
        ]
        filing_repo.list_filings.return_value = filings

        summary = await service.fetch_for_company("US_AAPL")

        assert summary.fetched == 1  # id=1 成功
        assert summary.skipped == 1  # id=2 は実体ファイルありでスキップ
        assert len(summary.failed) == 1  # id=3 failure
        assert summary.failed[0][0] == 3

    async def test_refetches_stale_storage_path(
        self,
        service,
        filing_repo,
        sec_client,
        tmp_path,
    ):
        stale_dir = tmp_path / "stale"
        stale_dir.mkdir()
        filing_repo.list_filings.return_value = [
            make_filing(id=1, accession_no="A-1", storage_path=str(stale_dir)),
        ]

        summary = await service.fetch_for_company("US_AAPL")

        assert summary.fetched == 1
        assert summary.skipped == 0
        assert summary.failed == []
        sec_client.get_filing_html.assert_awaited_once()

    async def test_fetch_for_company_refetches_sec_pdf_only_storage(
        self,
        service,
        filing_repo,
        sec_client,
        tmp_path,
    ):
        pdf_only = tmp_path / "pdf-only"
        pdf_only.mkdir()
        (pdf_only / "converted.pdf").write_bytes(b"%PDF-1.7 stale")
        filing_repo.list_filings.return_value = [
            make_filing(id=1, accession_no="A-1", storage_path=str(pdf_only)),
        ]

        summary = await service.fetch_for_company("US_AAPL")

        assert summary.fetched == 1
        assert summary.skipped == 0
        assert summary.failed == []
        sec_client.get_filing_html.assert_awaited_once()

    async def test_aggregates_http_fetch_failures(
        self,
        service,
        filing_repo,
        sec_client,
    ):
        filings = [
            make_filing(id=1, accession_no="A-1"),
            make_filing(id=2, accession_no="A-2"),
        ]
        filing_repo.list_filings.return_value = filings
        sec_client.get_filing_html.side_effect = [
            "<html><body>ok</body></html>",
            httpx.HTTPStatusError(
                "500",
                request=httpx.Request("GET", "http://x"),
                response=httpx.Response(500),
            ),
        ]

        summary = await service.fetch_for_company("US_AAPL")

        assert summary.fetched == 1
        assert summary.skipped == 0
        assert len(summary.failed) == 1
        assert summary.failed[0][0] == 2
        assert "SEC fetch failed" in summary.failed[0][1]
        filing_repo.update_storage.assert_awaited_once()
        assert filing_repo.update_storage.await_args.kwargs["filing_id"] == 1
