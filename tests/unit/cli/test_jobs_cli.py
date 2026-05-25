# tests/unit/cli/test_jobs_cli.py
"""jobs CLI のテスト (Bug #3 修正含む)"""
import argparse
from datetime import date

import pytest

from stock_analyze_system.cli.jobs import handle, register_parser
from stock_analyze_system.services.job import DailyUpdateResult, SyncResult
from tests.unit.cli.conftest import make_services as _make_services


class TestBug3NoTypeOption:
    """Bug #3: --type オプションが存在しないこと"""

    def test_no_type_argument(self):
        """--type 引数が定義されていないこと"""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)

        # --type を渡すとエラーになること
        with pytest.raises(SystemExit):
            parser.parse_args(["jobs", "sync", "US_AAPL", "--type", "daily"])

    def test_sync_subcommand(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args(["jobs", "sync", "US_AAPL"])
        assert args.action == "sync"
        assert args.company_id == "US_AAPL"

    def test_daily_subcommand(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args(["jobs", "daily", "--market", "us"])
        assert args.action == "daily"
        assert args.market == "us"

    def test_daily_accepts_filing_date(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args([
            "jobs",
            "daily",
            "--market",
            "us",
            "--filing-date",
            "2026-04-28",
        ])
        assert args.action == "daily"
        assert args.market == "us"
        assert args.filing_date == date(2026, 4, 28)

    def test_daily_rejects_invalid_filing_date(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        with pytest.raises(SystemExit):
            parser.parse_args(["jobs", "daily", "--filing-date", "20260428"])

    def test_valuations_subcommand_accepts_market(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)

        args = parser.parse_args(["jobs", "valuations", "--market", "jp"])

        assert args.action == "valuations"
        assert args.market == "jp"

    def test_valuations_subcommand_accepts_quote_provider(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)

        args = parser.parse_args([
            "jobs",
            "valuations",
            "--market",
            "us",
            "--quote-provider",
            "google_sheets",
        ])

        assert args.action == "valuations"
        assert args.quote_provider == "google_sheets"


class TestJobsSync:
    async def test_sync(self, capsys):
        svc = _make_services()
        result = SyncResult(
            company_id="US_AAPL",
            financials_count=5,
            filings_count=3,
            valuations_count=1,
        )
        svc.job_service.sync_company.return_value = result

        args = argparse.Namespace(action="sync", json=False, company_id="US_AAPL")
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "US_AAPL" in out
        assert "5" in out


class TestJobsDaily:
    async def test_daily(self, capsys):
        svc = _make_services()
        result = DailyUpdateResult(market="us", total_companies=2)
        result.results = [
            SyncResult(company_id="US_AAPL", financials_count=5),
            SyncResult(company_id="US_MSFT", financials_count=3),
        ]
        svc.job_service.run_daily_update.return_value = result

        args = argparse.Namespace(action="daily", json=False, market="us")
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "us" in out.lower() or "US" in out

    async def test_daily_passes_filing_date(self, capsys):
        svc = _make_services()
        result = DailyUpdateResult(market="us", total_companies=1)
        result.results = [SyncResult(company_id="US_AAPL", filings_count=1)]
        svc.job_service.run_daily_update.return_value = result

        args = argparse.Namespace(
            action="daily",
            json=False,
            market="us",
            filing_date=date(2026, 4, 28),
        )

        await handle(args, svc)

        svc.job_service.run_daily_update.assert_awaited_once_with(
            market="us",
            target_date=date(2026, 4, 28),
        )
        assert "Daily update complete" in capsys.readouterr().out


class TestJobsValuations:
    async def test_valuations_passes_market(self, capsys):
        svc = _make_services()
        result = DailyUpdateResult(market="jp", total_companies=1)
        result.results = [SyncResult(company_id="JP_7203", valuations_count=1)]
        svc.job_service.run_target_valuation_update.return_value = result

        args = argparse.Namespace(
            action="valuations",
            json=False,
            market="jp",
            quote_provider="google_sheets",
        )

        await handle(args, svc)

        svc.job_service.run_target_valuation_update.assert_awaited_once_with(
            market="jp",
            quote_provider="google_sheets",
        )
        out = capsys.readouterr().out
        assert "valuation" in out.lower()
        assert "JP_7203" in out

    async def test_valuations_reports_skipped_reasons(self, capsys):
        svc = _make_services()
        result = DailyUpdateResult(market="us", total_companies=1)
        result.results = [
            SyncResult(
                company_id="US_AAPL",
                valuations_count=0,
                skipped_reasons=["No usable quote for US_AAPL from google_sheets"],
            ),
        ]
        svc.job_service.run_target_valuation_update.return_value = result

        args = argparse.Namespace(
            action="valuations",
            json=False,
            market="us",
            quote_provider="google_sheets",
        )

        await handle(args, svc)

        out = capsys.readouterr().out
        assert "Succeeded: 0" in out
        assert "Skipped:   1" in out
        assert "No usable quote" in out

    async def test_valuations_json_includes_skipped_reasons(self, capsys):
        svc = _make_services()
        result = DailyUpdateResult(market="us", total_companies=1)
        result.results = [
            SyncResult(
                company_id="US_AAPL",
                valuations_count=0,
                skipped_reasons=["No usable quote for US_AAPL from google_sheets"],
            ),
        ]
        svc.job_service.run_target_valuation_update.return_value = result

        args = argparse.Namespace(
            action="valuations",
            json=True,
            market="us",
            quote_provider="google_sheets",
        )

        await handle(args, svc)

        out = capsys.readouterr().out
        assert '"skipped_reasons": [' in out
        assert "No usable quote" in out
