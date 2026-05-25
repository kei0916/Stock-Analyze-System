# tests/unit/ingestion/test_sec_edgar.py
"""SEC EDGAR クライアントのテスト"""
from datetime import date

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient


@pytest.fixture
def mock_edgar(httpx_mock):
    """SEC EDGAR APIモックを設定"""
    return httpx_mock


class TestSearchCik:
    def test_sec_edgar_rate_is_capped_at_10_without_initial_burst(self):
        client = SecEdgarClient(email="test@example.com", rate=50)

        assert client._rate_limiter._rate == 10.0
        assert client._rate_limiter._allowance == 1.0

    async def test_search_cik_found(self, mock_edgar):
        tickers_data = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": "789019", "ticker": "MSFT", "title": "Microsoft Corp"},
        }
        mock_edgar.add_response(
            url="https://www.sec.gov/files/company_tickers.json",
            json=tickers_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            cik = await client.search_cik("AAPL")
            assert cik == "0000320193"

    async def test_search_cik_not_found(self, mock_edgar):
        mock_edgar.add_response(
            url="https://www.sec.gov/files/company_tickers.json",
            json={},
        )
        async with SecEdgarClient(email="test@example.com") as client:
            cik = await client.search_cik("NONEXISTENT")
            assert cik is None

    async def test_search_cik_case_insensitive(self, mock_edgar):
        tickers_data = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple"},
        }
        mock_edgar.add_response(
            url="https://www.sec.gov/files/company_tickers.json",
            json=tickers_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            cik = await client.search_cik("aapl")
            assert cik == "0000320193"


class TestGetCompanyFacts:
    async def test_get_company_facts(self, mock_edgar):
        facts_data = {"cik": 320193, "entityName": "Apple", "facts": {}}
        mock_edgar.add_response(
            url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            json=facts_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.get_company_facts("0000320193")
            assert result["cik"] == 320193


class TestGetSubmissions:
    async def test_get_submissions_simple(self, mock_edgar):
        submissions_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "primaryDocument": ["doc.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=submissions_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.get_submissions("0000320193")
            assert result["cik"] == "320193"

    async def test_get_submissions_with_pagination(self, mock_edgar):
        """ページネーション対応テスト（既知バグ#18修正確認）"""
        main_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["acc-1"],
                    "primaryDocument": ["doc1.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [{"name": "CIK0000320193-submissions-001.json"}],
            },
        }
        page_data = {
            "form": ["10-Q"], "filingDate": ["2024-08-01"],
            "reportDate": ["2024-06-29"],
            "accessionNumber": ["acc-2"],
            "primaryDocument": ["doc2.htm"],
            "primaryDocDescription": ["10-Q"],
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=main_data,
        )
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193-submissions-001.json",
            json=page_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.get_submissions("0000320193")
            forms = result["filings"]["recent"]["form"]
            assert len(forms) == 2
            assert "10-Q" in forms


class TestSearchEfts:
    async def test_search_efts(self, mock_edgar):
        """EFTS全文検索テスト（C2修正: 仕様書のsearch_efts追加）"""
        efts_data = {
            "hits": {
                "hits": [
                    {"_source": {"file_num": "001-36743", "entity_name": "Apple Inc."}},
                ],
                "total": {"value": 1},
            },
        }
        mock_edgar.add_response(
            url="https://efts.sec.gov/LATEST/search-index?q=%22AAPL%22&dateRange=custom&startdt=2024-01-01&enddt=2024-12-31",
            json=efts_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.search_efts("AAPL", start_date="2024-01-01", end_date="2024-12-31")
            assert result["hits"]["total"]["value"] == 1


class TestListFilings:
    async def test_list_filings(self, mock_edgar):
        submissions_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K"],
                    "filingDate": ["2024-11-01", "2024-08-02", "2024-07-15"],
                    "reportDate": ["2024-09-28", "2024-06-29", "2024-07-15"],
                    "accessionNumber": ["acc-1", "acc-2", "acc-3"],
                    "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
                    "primaryDocDescription": ["10-K", "10-Q", "8-K"],
                },
                "files": [],
            },
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=submissions_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            filings = await client.list_filings("0000320193", form_types=["10-K", "10-Q"])
            assert len(filings) == 2
            assert filings[0]["form"] == "10-K"
            assert "documentUrl" in filings[0]


class TestListDailyFilings:
    async def test_list_daily_filings_parses_master_index(self, mock_edgar):
        index_text = """Description: Master Index of EDGAR Dissemination Feed
Last Data Received: April 28, 2026
Comments: webmaster@sec.gov
Anonymous FTP: ftp://ftp.sec.gov/edgar/

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
320193|Apple Inc.|10-K|2026-04-28|edgar/data/320193/0000320193-26-000001.txt
789019|Microsoft Corp|8-K|2026-04-28|edgar/data/789019/0000789019-26-000002.txt
999999|Other Corp|4|2026-04-28|edgar/data/999999/0000999999-26-000003.txt
"""
        mock_edgar.add_response(
            url="https://www.sec.gov/Archives/edgar/daily-index/2026/QTR2/master.20260428.idx",
            text=index_text,
        )

        async with SecEdgarClient(email="test@example.com") as client:
            filings = await client.list_daily_filings(
                date(2026, 4, 28),
                form_types=["10-K", "8-K"],
            )

        assert len(filings) == 2
        assert filings[0] == {
            "cik": "0000320193",
            "companyName": "Apple Inc.",
            "form": "10-K",
            "filingDate": "2026-04-28",
            "reportDate": "",
            "accessionNumber": "0000320193-26-000001",
            "primaryDocument": "",
            "primaryDocDescription": "",
            "documentUrl": "https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001.txt",
        }
        assert filings[1]["cik"] == "0000789019"
        assert filings[1]["form"] == "8-K"

    async def test_list_daily_filings_skips_malformed_rows(self, mock_edgar, caplog):
        index_text = """CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
not-a-cik|Bad Corp|10-K|2026-04-28|edgar/data/bad/file.txt
320193|Apple Inc.|10-K|2026-04-27|edgar/data/320193/old.txt
320193|Apple Inc.|10-Q|2026-04-28|edgar/data/320193/0000320193-26-000004.txt
"""
        mock_edgar.add_response(
            url="https://www.sec.gov/Archives/edgar/daily-index/2026/QTR2/master.20260428.idx",
            text=index_text,
        )

        async with SecEdgarClient(email="test@example.com") as client:
            with caplog.at_level("WARNING", logger="stock_analyze_system.ingestion.sec_edgar"):
                filings = await client.list_daily_filings(date(2026, 4, 28))

        assert len(filings) == 1
        assert filings[0]["accessionNumber"] == "0000320193-26-000004"
        assert any("invalid daily filing row" in r.getMessage() for r in caplog.records)


class TestSecEdgarBranches:
    async def test_get_filing_html(self, mock_edgar):
        mock_edgar.add_response(
            url="https://www.sec.gov/Archives/edgar/data/320193/doc.htm",
            text="<html>10-K</html>",
        )
        async with SecEdgarClient(email="test@example.com") as client:
            html = await client.get_filing_html(
                "https://www.sec.gov/Archives/edgar/data/320193/doc.htm",
            )
            assert "<html>" in html

    async def test_list_filings_default_form_types(self, mock_edgar):
        """form_types=None なら FilingType の default set を使う (68)"""
        submissions_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["a"],
                    "primaryDocument": ["d.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=submissions_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            filings = await client.list_filings("0000320193")
            assert len(filings) == 1

    async def test_list_filings_skips_malformed_date(self, mock_edgar):
        """filingDate が壊れていれば ValueError → skip (93-95)"""
        submissions_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["notadate"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["a"],
                    "primaryDocument": ["d.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=submissions_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            filings = await client.list_filings("0000320193", form_types=["10-K"])
            assert filings == []


class TestGetPrimaryDocumentUrl:
    async def test_returns_full_url_for_known_accession(self, httpx_mock):
        """submissions JSON から該当 accession の primaryDocument を URL に組み立てる"""
        httpx_mock.add_response(json={
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "primaryDocument": ["aapl-20240928.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        })
        async with SecEdgarClient(email="t@example.com", rate=100) as client:
            url = await client.get_primary_document_url(
                "0000320193", "0000320193-24-000123",
            )
        assert url == (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        )

    async def test_raises_when_accession_not_found(self, httpx_mock):
        httpx_mock.add_response(json={
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "primaryDocument": ["aapl-20240928.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        })
        async with SecEdgarClient(email="t@example.com", rate=100) as client:
            with pytest.raises(ValueError, match="not found"):
                await client.get_primary_document_url(
                    "0000320193", "9999999999-99-999999",
                )


from tests.fixtures.sec_company_tickers_payload import sec_universe_payload  # noqa: E402


class TestSecEdgarListUniverse:
    @pytest.mark.asyncio
    async def test_returns_normalized_entries(self):
        client = SecEdgarClient(email="t@e.com")
        fake_resp = MagicMock()
        fake_resp.json = MagicMock(return_value=sec_universe_payload())
        with patch.object(client, "_get", AsyncMock(return_value=fake_resp)):
            entries = await client.list_universe()

        # 18 rows total in fixture (15 normal + 3 anomalies; "EMTNAM" name="" and 9999003 both empty also returned raw)
        assert len(entries) >= 15
        # cik must be 10-digit zero-padded string
        sample = next(e for e in entries if e["ticker"] == "AAPL")
        assert sample["cik"] == "0000320193"
        assert sample["exchange"] == "Nasdaq"
        assert sample["name"] == "Apple Inc"

    @pytest.mark.asyncio
    async def test_uses_company_tickers_exchange_endpoint(self):
        client = SecEdgarClient(email="t@e.com")
        fake_resp = MagicMock()
        fake_resp.json = MagicMock(return_value={"fields": ["cik", "name", "ticker", "exchange"], "data": []})
        with patch.object(client, "_get", AsyncMock(return_value=fake_resp)) as get:
            await client.list_universe()
        called_url = get.call_args[0][0]
        assert called_url == "https://www.sec.gov/files/company_tickers_exchange.json"
