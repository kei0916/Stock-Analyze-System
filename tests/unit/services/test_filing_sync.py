"""FilingSyncService のテスト"""
from datetime import date
from unittest.mock import AsyncMock

from stock_analyze_system.models.enums import FilingSource
from stock_analyze_system.services.filing_sync import FilingSyncService
from stock_analyze_system.services.filing_sync import FilingSourceAdapter


class TestFilingSyncService:
    async def test_update_from_sec_returns_count(self):
        """SEC ファイリング更新がカウントを返すこと"""
        filing_repo = AsyncMock()
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = [
            {
                "form": "10-K", "accessionNumber": "acc-001",
                "reportDate": "2024-09-28", "filingDate": "2024-11-01",
                "documentUrl": "https://example.com/doc",
            },
        ]
        filing_repo.find_existing_accessions.return_value = set()
        filing_repo.bulk_upsert.return_value = 1

        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=sec_client,
            edinet_client=AsyncMock(),
        )
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 1

    async def test_update_from_sec_skip_existing(self):
        """既存ファイリングはスキップされること"""
        filing_repo = AsyncMock()
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = [
            {
                "form": "10-K", "accessionNumber": "acc-001",
                "reportDate": "2024-09-28", "filingDate": "2024-11-01",
                "documentUrl": "https://example.com/doc",
            },
        ]
        filing_repo.find_existing_accessions.return_value = {"acc-001"}

        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=sec_client,
            edinet_client=AsyncMock(),
        )
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0

    async def test_update_from_sec_records_registers_prefetched_daily_filing(self):
        filing_repo = AsyncMock()
        filing_repo.find_existing_accessions.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        sec_client = AsyncMock()
        daily_records = [
            {
                "form": "8-K",
                "accessionNumber": "0000789019-26-000002",
                "reportDate": "",
                "filingDate": "2026-04-28",
                "documentUrl": "https://www.sec.gov/Archives/edgar/data/789019/0000789019-26-000002.txt",
            },
        ]
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=sec_client,
            edinet_client=AsyncMock(),
        )

        count = await svc.update_from_sec_records("US_MSFT", daily_records)

        assert count == 1
        sec_client.list_filings.assert_not_called()
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["filing_type"] == "8-K"
        assert rows[0]["period_type"] == "quarterly"
        assert rows[0]["fiscal_year"] == 2026
        assert "period_end" not in rows[0]

    async def test_update_from_sec_records_treats_40f_as_annual(self):
        filing_repo = AsyncMock()
        filing_repo.find_existing_accessions.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(),
            edinet_client=AsyncMock(),
        )

        await svc.update_from_sec_records("US_SHOP", [
            {
                "form": "40-F",
                "accessionNumber": "0001594805-26-000001",
                "reportDate": "2025-12-31",
                "filingDate": "2026-02-15",
            },
        ])

        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["period_type"] == "annual"
        assert rows[0]["period_end"].isoformat() == "2025-12-31"


def _make_filing_svc(**overrides):
    defaults = {
        "filing_repo": AsyncMock(),
        "sec_client": AsyncMock(),
        "edinet_client": AsyncMock(),
    }
    defaults.update(overrides)
    return FilingSyncService(**defaults)


class TestDailySecFilingListing:
    async def test_list_daily_sec_filings_delegates_to_client(self):
        sec_client = AsyncMock()
        sec_client.list_daily_filings.return_value = [{"form": "10-K"}]
        svc = _make_filing_svc(sec_client=sec_client)

        result = await svc.list_daily_sec_filings(date(2026, 4, 28), form_types=["10-K"])

        assert result == [{"form": "10-K"}]
        sec_client.list_daily_filings.assert_awaited_once_with(
            date(2026, 4, 28),
            form_types=["10-K"],
        )

    async def test_find_sec_company_by_ticker_uses_sec_universe(self):
        sec_client = AsyncMock()
        sec_client.list_universe.return_value = [
            {
                "ticker": "WRBY",
                "cik": "0001504776",
                "name": "Warby Parker Inc.",
                "exchange": "NYSE",
            },
        ]
        svc = _make_filing_svc(sec_client=sec_client)

        result = await svc.find_sec_company_by_ticker("wrby")

        assert result == {
            "ticker": "WRBY",
            "cik": "0001504776",
            "name": "Warby Parker Inc.",
            "exchange": "NYSE",
        }

    async def test_find_sec_company_by_cik_uses_sec_universe(self):
        sec_client = AsyncMock()
        sec_client.list_universe.return_value = [
            {
                "ticker": "WRBY",
                "cik": "0001504776",
                "name": "Warby Parker Inc.",
                "exchange": "NYSE",
            },
        ]
        svc = _make_filing_svc(sec_client=sec_client)

        result = await svc.find_sec_company_by_cik("1504776")

        assert result["ticker"] == "WRBY"


class TestUpdateFromSecErrors:
    async def test_returns_zero_on_api_failure(self):
        """SEC API失敗時に0を返すこと"""
        sec_client = AsyncMock()
        sec_client.list_filings.side_effect = OSError("API error")
        svc = _make_filing_svc(sec_client=sec_client)
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0

    async def test_returns_zero_on_empty_list(self):
        """空リスト時に0を返すこと"""
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = []
        svc = _make_filing_svc(sec_client=sec_client)
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0

    async def test_skips_entry_without_accession(self):
        """accessionNumber がないエントリはスキップ"""
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = [
            {"form": "10-K", "reportDate": "2024-09-28"},
        ]
        filing_repo = AsyncMock()
        filing_repo.find_existing_accessions.return_value = set()
        svc = _make_filing_svc(filing_repo=filing_repo, sec_client=sec_client)
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0
        filing_repo.bulk_upsert.assert_not_called()

    async def test_quarterly_period_type_for_10q(self):
        """10-Q は quarterly として登録"""
        filing_repo = AsyncMock()
        filing_repo.find_existing_accessions.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = [
            {
                "form": "10-Q", "accessionNumber": "acc-002",
                "reportDate": "2024-06-30", "filingDate": "2024-08-01",
            },
        ]
        svc = _make_filing_svc(filing_repo=filing_repo, sec_client=sec_client)
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 1
        # bulk_upsert called once; check the rows list passed as second arg
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["period_type"] == "quarterly"


class TestUpdateFromEdinet:
    async def test_registers_edinet_filings(self):
        """EDINET ファイリングが登録されること"""
        filing_repo = AsyncMock()
        filing_repo.find_existing_doc_ids.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = [
            {"docID": "S100001", "periodEnd": "2024-03-31", "docTypeCode": "120"},
        ]
        svc = _make_filing_svc(filing_repo=filing_repo, edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 1
        filing_repo.bulk_upsert.assert_called_once()

    async def test_skips_existing_edinet_filing(self):
        """既存ファイリングはスキップ"""
        filing_repo = AsyncMock()
        filing_repo.find_existing_doc_ids.return_value = {"S100001"}
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = [
            {"docID": "S100001", "periodEnd": "2024-03-31", "docTypeCode": "120"},
        ]
        svc = _make_filing_svc(filing_repo=filing_repo, edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_skips_doc_without_id(self):
        """docIDがないドキュメントはスキップ"""
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = [
            {"periodEnd": "2024-03-31", "docTypeCode": "120"},
        ]
        filing_repo = AsyncMock()
        filing_repo.find_existing_doc_ids.return_value = set()
        svc = _make_filing_svc(filing_repo=filing_repo, edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_returns_zero_on_api_failure(self):
        """EDINET API失敗時に0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.side_effect = OSError("API error")
        svc = _make_filing_svc(edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_returns_zero_on_empty_docs(self):
        """空ドキュメントリスト時に0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = []
        svc = _make_filing_svc(edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_quarterly_period_type(self):
        """docTypeCode 140 は quarterly として登録"""
        filing_repo = AsyncMock()
        filing_repo.find_existing_doc_ids.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = [
            {"docID": "S100002", "periodEnd": "2024-06-30", "docTypeCode": "140"},
        ]
        svc = _make_filing_svc(filing_repo=filing_repo, edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 1
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["period_type"] == "quarterly"

    async def test_annual_period_type_for_130(self):
        """docTypeCode 130 は annual として登録"""
        filing_repo = AsyncMock()
        filing_repo.find_existing_doc_ids.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = [
            {"docID": "S100003", "periodEnd": "2024-03-31", "docTypeCode": "130"},
        ]
        svc = _make_filing_svc(filing_repo=filing_repo, edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 1
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["period_type"] == "annual"

    async def test_fiscal_year_from_period_end(self):
        """periodEnd から fiscal_year を抽出"""
        filing_repo = AsyncMock()
        filing_repo.find_existing_doc_ids.return_value = set()
        filing_repo.bulk_upsert.return_value = 1
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = [
            {"docID": "S100001", "periodEnd": "2024-03-31", "docTypeCode": "120"},
        ]
        svc = _make_filing_svc(filing_repo=filing_repo, edinet_client=edinet_client)
        await svc.update_from_edinet("JP_7203", "E02144")
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert rows[0]["fiscal_year"] == 2024


def _make_adapter(
    *,
    source=FilingSource.SEC,
    fetch=None,
    key_field="accessionNumber",
    find_existing=None,
    map_record=None,
):
    return FilingSourceAdapter(
        source=source,
        fetch=fetch or AsyncMock(return_value=[]),
        key_field=key_field,
        find_existing=find_existing or AsyncMock(return_value=set()),
        map_record=map_record or (lambda d: {"accession_no": d[key_field]}),
    )


class TestFilingSyncInternal:
    async def test_happy_path_filters_existing(self):
        filing_repo = AsyncMock()
        filing_repo.bulk_upsert.return_value = 2
        raw = [
            {"accessionNumber": "a1"},
            {"accessionNumber": "a2"},
            {"accessionNumber": "a3"},
        ]
        adapter = _make_adapter(
            fetch=AsyncMock(return_value=raw),
            find_existing=AsyncMock(return_value={"a2"}),
        )
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(),
            edinet_client=AsyncMock(),
        )

        n = await svc._sync(adapter, "US_AAPL", "0000320193")

        assert n == 2
        filing_repo.bulk_upsert.assert_called_once()
        kwargs = filing_repo.bulk_upsert.call_args.kwargs
        assert kwargs["source"] is FilingSource.SEC
        rows = filing_repo.bulk_upsert.call_args[0][1]
        assert len(rows) == 2

    async def test_empty_fetch_returns_zero_without_upsert(self):
        filing_repo = AsyncMock()
        adapter = _make_adapter(fetch=AsyncMock(return_value=[]))
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(),
            edinet_client=AsyncMock(),
        )

        n = await svc._sync(adapter, "US_AAPL", "0000320193")

        assert n == 0
        filing_repo.bulk_upsert.assert_not_called()

    async def test_all_existing_returns_zero_without_upsert(self):
        filing_repo = AsyncMock()
        raw = [{"accessionNumber": "a1"}, {"accessionNumber": "a2"}]
        adapter = _make_adapter(
            fetch=AsyncMock(return_value=raw),
            find_existing=AsyncMock(return_value={"a1", "a2"}),
        )
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(),
            edinet_client=AsyncMock(),
        )

        n = await svc._sync(adapter, "US_AAPL", "0000320193")

        assert n == 0
        filing_repo.bulk_upsert.assert_not_called()

    async def test_fetch_exception_logged_and_returns_zero(self, caplog):
        filing_repo = AsyncMock()
        adapter = _make_adapter(fetch=AsyncMock(side_effect=OSError("API down")))
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(),
            edinet_client=AsyncMock(),
        )

        with caplog.at_level("WARNING"):
            n = await svc._sync(adapter, "US_AAPL", "0000320193")

        assert n == 0
        filing_repo.bulk_upsert.assert_not_called()
        assert any("filing fetch failed" in r.message for r in caplog.records)

    async def test_map_record_called_only_for_new_entries(self):
        filing_repo = AsyncMock()
        filing_repo.bulk_upsert.return_value = 1
        raw = [{"accessionNumber": "a1"}, {"accessionNumber": "a2"}]
        map_calls = []

        def _map(d):
            map_calls.append(d)
            return {"accession_no": d["accessionNumber"]}

        adapter = _make_adapter(
            fetch=AsyncMock(return_value=raw),
            find_existing=AsyncMock(return_value={"a1"}),
            map_record=_map,
        )
        svc = FilingSyncService(
            filing_repo=filing_repo,
            sec_client=AsyncMock(),
            edinet_client=AsyncMock(),
        )

        await svc._sync(adapter, "US_AAPL", "0000320193")

        assert len(map_calls) == 1
        assert map_calls[0]["accessionNumber"] == "a2"
