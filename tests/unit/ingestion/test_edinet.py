# tests/unit/ingestion/test_edinet.py
"""EDINET クライアントのテスト"""
import io
import zipfile

import pytest

from stock_analyze_system.ingestion.edinet import EdinetClient


class TestGetDocumentList:
    async def test_get_document_list(self, httpx_mock):
        response_data = {
            "metadata": {"status": "200"},
            "results": [
                {"docTypeCode": "120", "edinetCode": "E02144",
                 "docID": "S100TEST", "filerName": "Toyota"},
                {"docTypeCode": "130", "edinetCode": "E02144",
                 "docID": "S100SKIP", "filerName": "Toyota"},
            ],
        }
        httpx_mock.add_response(json=response_data)
        async with EdinetClient(api_key="test_key") as client:
            docs = await client.get_document_list("2024-03-01", doc_type="120")
            assert len(docs) == 1
            assert docs[0]["docID"] == "S100TEST"


class TestApiKeyValidation:
    async def test_warns_on_missing_api_key(self, httpx_mock, caplog):
        """APIキー未設定時にWARNINGログ（既知バグ#10修正確認）"""
        async with EdinetClient(api_key="") as client:
            import logging
            with caplog.at_level(logging.WARNING):
                docs = await client.get_document_list("2024-03-01")
            assert len(docs) == 0
            assert "API key" in caplog.text or "api_key" in caplog.text


class TestSearchCompanyFilings:
    async def test_search_returns_matching(self, httpx_mock):
        """M2修正: httpx_mock.reset() は無効なため、1日分のみテスト"""
        httpx_mock.add_response(json={
            "metadata": {"status": "200"},
            "results": [
                {"docTypeCode": "120", "edinetCode": "E02144",
                 "docID": "S100MATCH", "filerName": "Toyota"},
                {"docTypeCode": "120", "edinetCode": "E99999",
                 "docID": "S100OTHER", "filerName": "Other Corp"},
            ],
        })
        async with EdinetClient(api_key="test_key", rate_limit_interval=0.01) as client:
            results = await client.search_company_filings(
                "E02144", "2024-01-01", "2024-01-01",
            )
            assert len(results) == 1
            assert results[0]["docID"] == "S100MATCH"

    async def test_search_continues_on_daily_error(self, httpx_mock):
        """日次検索でエラーがあっても続行すること"""
        # 1日目: エラー、2日目: 成功
        httpx_mock.add_exception(RuntimeError("network error"))
        httpx_mock.add_response(json={
            "metadata": {"status": "200"},
            "results": [
                {"docTypeCode": "120", "edinetCode": "E02144",
                 "docID": "S100OK", "filerName": "Toyota"},
            ],
        })
        async with EdinetClient(api_key="test_key", rate_limit_interval=0.01) as client:
            results = await client.search_company_filings(
                "E02144", "2024-01-01", "2024-01-02",
            )
            assert len(results) == 1
            assert results[0]["docID"] == "S100OK"


class TestDownloadXbrlZip:
    async def test_raises_without_api_key(self, tmp_path):
        """APIキーなしでValueErrorが発生すること"""
        async with EdinetClient(api_key="") as client:
            with pytest.raises(ValueError, match="API key"):
                await client.download_xbrl_zip("S100TEST", tmp_path)

    async def test_downloads_and_extracts(self, httpx_mock, tmp_path):
        """ZIPダウンロード・展開が正常に動作すること"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("test.xml", "<xbrl>test</xbrl>")
        zip_bytes = buf.getvalue()

        httpx_mock.add_response(content=zip_bytes)

        async with EdinetClient(api_key="test_key") as client:
            result = await client.download_xbrl_zip("S100TEST", tmp_path)
            assert result.exists()
            assert (result / "test.xml").exists()


class TestDownloadPdf:
    async def test_raises_without_api_key(self):
        async with EdinetClient(api_key="") as client:
            with pytest.raises(ValueError, match="API key"):
                await client.download_pdf("S100TEST")

    async def test_returns_pdf_bytes(self, httpx_mock):
        pdf_bytes = b"%PDF-1.7 fake pdf body"
        httpx_mock.add_response(content=pdf_bytes)

        async with EdinetClient(api_key="test_key") as client:
            result = await client.download_pdf("S100TEST")

        assert result == pdf_bytes

    async def test_uses_type_2_param(self, httpx_mock):
        httpx_mock.add_response(content=b"x")

        async with EdinetClient(api_key="test_key") as client:
            await client.download_pdf("S100TEST")

        request = httpx_mock.get_requests()[0]
        assert request.url.params.get("type") == "2"
        assert request.url.params.get("Subscription-Key") == "test_key"
