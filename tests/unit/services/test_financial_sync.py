"""FinancialSyncService のテスト"""
from unittest.mock import AsyncMock, MagicMock, patch

from stock_analyze_system.services.financial_sync import FinancialSyncService
from stock_analyze_system.shared.financial import derive_fcf


def _make_sync_svc(**overrides):
    defaults = {
        "financial_repo": AsyncMock(),
        "sec_client": AsyncMock(),
        "edinet_client": AsyncMock(),
        "yahoo_client": AsyncMock(),
        "fmp_client": AsyncMock(),
    }
    defaults.update(overrides)
    return FinancialSyncService(**defaults)


class TestUpdateFromSec:
    async def test_returns_record_count(self):
        """Bug #4: SEC 更新がレコード数を返すこと"""
        repo = AsyncMock()
        repo.upsert.return_value = MagicMock()
        sec_client = AsyncMock()
        sec_client.get_company_facts.return_value = {"facts": {"us-gaap": {}}}

        svc = _make_sync_svc(financial_repo=repo, sec_client=sec_client)

        with patch.object(svc, "_parse_and_upsert_sec", return_value=3):
            count = await svc.update_from_sec(
                "US_AAPL", "0000320193", "US-GAAP",
                period_types=("annual",),
            )
        assert count == 3

    async def test_returns_zero_on_failure(self):
        """SEC API 失敗時に 0 を返すこと"""
        sec_client = AsyncMock()
        sec_client.get_company_facts.side_effect = OSError("API error")

        svc = _make_sync_svc(sec_client=sec_client)
        count = await svc.update_from_sec(
            "US_AAPL", "0000320193", "US-GAAP",
        )
        assert count == 0


class TestUpdateFromEdinet:
    async def test_returns_record_count(self):
        """Bug #4: EDINET 更新がレコード数を返すこと"""
        repo = AsyncMock()
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = [
            {"docID": "S100001", "docTypeCode": "120", "periodEnd": "2024-03-31"},
        ]
        edinet_client.download_xbrl_zip.return_value = "/tmp/xbrl"

        svc = _make_sync_svc(financial_repo=repo, edinet_client=edinet_client)

        with patch.object(svc, "_parse_and_upsert_edinet", return_value=1):
            count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 1


class TestUpdateFromEdinetEdgeCases:
    async def test_returns_zero_when_no_docs(self):
        """EDINET 検索結果が空の場合は0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.return_value = []
        svc = _make_sync_svc(edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0

    async def test_returns_zero_on_api_failure(self):
        """EDINET API失敗時に0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.search_company_filings.side_effect = OSError("EDINET error")
        svc = _make_sync_svc(edinet_client=edinet_client)
        count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 0


class TestParseAndUpsertSec:
    async def test_parses_and_upserts_records(self):
        """SEC facts をパースして各レコードをupsertすること"""
        repo = AsyncMock()
        svc = _make_sync_svc(financial_repo=repo)

        fake_records = [
            {"fiscal_year_end": "2024-09-28", "revenue": 100.0, "currency": "USD"},
        ]
        with patch(
            "stock_analyze_system.services.financial_sync.SecXbrlParser",
        ) as MockParser:
            MockParser.return_value.parse_company_facts.return_value = fake_records
            count = await svc._parse_and_upsert_sec(
                "US_AAPL", {"facts": {}}, "US-GAAP", "annual",
            )
        assert count == 1
        repo.upsert.assert_called_once()

    async def test_returns_zero_on_parse_error(self):
        """パーサーエラー時に0を返すこと"""
        svc = _make_sync_svc()
        with patch(
            "stock_analyze_system.services.financial_sync.SecXbrlParser",
        ) as MockParser:
            MockParser.return_value.parse_company_facts.side_effect = ValueError(
                "bad data",
            )
            count = await svc._parse_and_upsert_sec(
                "US_AAPL", {}, "US-GAAP", "annual",
            )
        assert count == 0

    async def test_derives_fcf_for_each_record(self):
        """各レコードでFCF導出が呼ばれること"""
        repo = AsyncMock()
        svc = _make_sync_svc(financial_repo=repo)
        fake_records = [
            {
                "fiscal_year_end": "2024-09-28",
                "operating_cf": 100.0,
                "capex": -30.0,
                "fcf": None,
                "currency": "USD",
            },
        ]
        with patch(
            "stock_analyze_system.services.financial_sync.SecXbrlParser",
        ) as MockParser:
            MockParser.return_value.parse_company_facts.return_value = fake_records
            await svc._parse_and_upsert_sec("US_AAPL", {}, "US-GAAP", "annual")
        call_args = repo.upsert.call_args
        upserted_data = call_args[0][1]
        assert upserted_data.get("fcf") == 70.0

    async def test_multiple_records(self):
        """複数レコードが全てupsertされること"""
        repo = AsyncMock()
        svc = _make_sync_svc(financial_repo=repo)
        fake_records = [
            {"fiscal_year_end": "2024-09-28", "revenue": 100.0, "currency": "USD"},
            {"fiscal_year_end": "2023-09-30", "revenue": 90.0, "currency": "USD"},
        ]
        with patch(
            "stock_analyze_system.services.financial_sync.SecXbrlParser",
        ) as MockParser:
            MockParser.return_value.parse_company_facts.return_value = fake_records
            count = await svc._parse_and_upsert_sec(
                "US_AAPL", {}, "US-GAAP", "annual",
            )
        assert count == 2
        assert repo.upsert.call_count == 2


class TestParseAndUpsertEdinet:
    async def test_uses_download_xbrl_zip_contract(self):
        """実クライアント契約どおり download_xbrl_zip() を使うこと"""
        repo = AsyncMock()

        class _ZipOnlyEdinetClient:
            def __init__(self):
                self.download_xbrl_zip = AsyncMock(return_value="/tmp/xbrl")

        edinet_client = _ZipOnlyEdinetClient()
        svc = _make_sync_svc(financial_repo=repo, edinet_client=edinet_client)

        with patch(
            "stock_analyze_system.services.financial_sync.EdinetXbrlParser",
        ) as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.detect_accounting_standard.return_value = "jp_gaap"
            parser_inst.parse_xbrl_directory.return_value = {
                "fiscal_year_end": "2024-03-31",
                "revenue": 5000.0,
            }
            count = await svc._parse_and_upsert_edinet(
                "JP_7203", {"docID": "S100001"},
            )

        assert count == 1
        edinet_client.download_xbrl_zip.assert_awaited_once()

    async def test_parses_and_upserts_edinet_doc(self):
        """EDINET ドキュメントをパースしてupsertすること"""
        repo = AsyncMock()
        edinet_client = AsyncMock()
        edinet_client.download_xbrl_zip.return_value = "/tmp/xbrl"
        svc = _make_sync_svc(financial_repo=repo, edinet_client=edinet_client)

        with patch(
            "stock_analyze_system.services.financial_sync.EdinetXbrlParser",
        ) as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.detect_accounting_standard.return_value = "jp_gaap"
            parser_inst.parse_xbrl_directory.return_value = {
                "fiscal_year_end": "2024-03-31",
                "revenue": 5000.0,
            }
            count = await svc._parse_and_upsert_edinet(
                "JP_7203", {"docID": "S100001"},
            )
        assert count == 1
        repo.upsert.assert_called_once()

    async def test_returns_zero_when_no_doc_id(self):
        """docIDがない場合は0を返すこと"""
        svc = _make_sync_svc()
        count = await svc._parse_and_upsert_edinet("JP_7203", {})
        assert count == 0

    async def test_returns_zero_on_download_error(self):
        """ダウンロードエラー時は0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.download_xbrl_zip.side_effect = OSError("download failed")
        svc = _make_sync_svc(edinet_client=edinet_client)
        count = await svc._parse_and_upsert_edinet(
            "JP_7203", {"docID": "S100001"},
        )
        assert count == 0

    async def test_returns_zero_when_parse_result_empty(self):
        """パース結果が空の場合は0を返すこと"""
        edinet_client = AsyncMock()
        edinet_client.download_xbrl_zip.return_value = "/tmp/xbrl"
        svc = _make_sync_svc(edinet_client=edinet_client)
        with patch(
            "stock_analyze_system.services.financial_sync.EdinetXbrlParser",
        ) as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.detect_accounting_standard.return_value = "jp_gaap"
            parser_inst.parse_xbrl_directory.return_value = {}
            count = await svc._parse_and_upsert_edinet(
                "JP_7203", {"docID": "S100001"},
            )
        assert count == 0

    async def test_accounting_standard_normalized(self):
        """会計基準が正規化されること (jp_gaap → JP-GAAP)"""
        repo = AsyncMock()
        edinet_client = AsyncMock()
        edinet_client.download_xbrl_zip.return_value = "/tmp/xbrl"
        svc = _make_sync_svc(financial_repo=repo, edinet_client=edinet_client)
        with patch(
            "stock_analyze_system.services.financial_sync.EdinetXbrlParser",
        ) as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.detect_accounting_standard.return_value = "jp_gaap"
            parser_inst.parse_xbrl_directory.return_value = {
                "fiscal_year_end": "2024-03-31",
                "revenue": 5000.0,
            }
            await svc._parse_and_upsert_edinet("JP_7203", {"docID": "S100001"})
        lookup_key = repo.upsert.call_args[0][0]
        assert lookup_key.get("accounting_standard") == "JP-GAAP"


class TestFcfDerivation:
    def test_fcf_from_operating_cf_and_capex(self):
        """FCF = operating_cf - abs(capex) で安全に導出されること"""
        record = {"operating_cf": 100.0, "capex": -30.0, "fcf": None}
        derive_fcf(record)
        assert record["fcf"] == 70.0

    def test_fcf_not_overwritten(self):
        """既存 FCF は上書きしない"""
        record = {"operating_cf": 100.0, "capex": -30.0, "fcf": 80.0}
        derive_fcf(record)
        assert record["fcf"] == 80.0
