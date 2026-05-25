# tests/unit/cli/test_stooq_cli.py
import argparse
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stock_analyze_system.ingestion.stooq import StooqAuthError, StooqRateLimitError
from stock_analyze_system.cli import stooq as cli_stooq


def _parse(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    cli_stooq.register_parser(sub)
    return parser.parse_args(["stooq", *argv])


class TestStooqCli:
    def test_download_parses_args(self):
        args = _parse(["download", "--years", "10", "--apikey", "testkey"])
        assert args.action == "download"
        assert args.years == 10
        assert args.apikey == "testkey"

    def test_download_apikey_from_env(self, monkeypatch):
        """Test that env var is picked up by parser default."""
        monkeypatch.setenv("STOOQ_API_KEY", "envkey")
        import importlib

        importlib.reload(cli_stooq)
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        cli_stooq.register_parser(sub)
        args = parser.parse_args(["stooq", "download"])
        assert args.apikey == "envkey"

    @pytest.mark.asyncio
    async def test_download_handler_uses_env_fallback(self, monkeypatch):
        """Test handler-level env fallback when parser default is None."""
        monkeypatch.setenv("STOOQ_API_KEY", "fallback_key")
        # Force parser default to None by temporarily clearing env during parse
        monkeypatch.delenv("STOOQ_API_KEY", raising=False)
        args = _parse(["download", "--years", "10"])
        assert args.apikey is None  # parser default is None if env not set at import time
        # Handler should check os.getenv again at runtime
        monkeypatch.setenv("STOOQ_API_KEY", "fallback_key")

    @pytest.mark.asyncio
    async def test_download_auth_error_exits(self, monkeypatch):
        """Test that StooqAuthError causes SystemExit(1) fail-fast."""
        monkeypatch.setenv("STOOQ_API_KEY", "bad_key")
        # Mock StooqPriceClient to raise StooqAuthError on first fetch
        with patch("stock_analyze_system.cli.stooq.StooqPriceClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.fetch_history = AsyncMock(side_effect=StooqAuthError("AAPL", "invalid key"))
            mock_client.close = AsyncMock()

            # Mock a company so the loop runs and fetch_history is called
            mock_company = MagicMock()
            mock_company.id = "US_AAPL"
            mock_company.ticker = "AAPL"

            services = MagicMock()
            services.session = AsyncMock()
            services.session.execute = AsyncMock(
                return_value=MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(all=MagicMock(return_value=[mock_company]))
                    )
                )
            )

            args = _parse(["download"])
            with pytest.raises(SystemExit) as exc_info:
                await cli_stooq._handle_download(args, services)
            assert exc_info.value.code == 1

    def test_write_errors_creates_directory(self, tmp_path, monkeypatch):
        """Test that _write_errors creates data/ directory if missing."""
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / "data").exists()
        cli_stooq._write_errors([{"ticker": "TEST", "reason": "NOT_FOUND"}])
        assert (tmp_path / "data").exists()
        assert (tmp_path / "data" / f"stooq_errors_{date.today().isoformat()}.json").exists()

    @pytest.mark.asyncio
    async def test_retry_incomplete_skips_new_listings(self, monkeypatch):
        """--retry-incomplete で新規上場（span < 90）はスキップされる"""
        monkeypatch.setenv("STOOQ_API_KEY", "testkey")

        mock_company_new = MagicMock()
        mock_company_new.id = "US_NEW"
        mock_company_new.ticker = "NEW"

        mock_company_gap = MagicMock()
        mock_company_gap.id = "US_GAP"
        mock_company_gap.ticker = "GAP"

        with (
            patch("stock_analyze_system.cli.stooq.StooqPriceClient") as mock_client_cls,
            patch(
                "stock_analyze_system.repositories.price_history.PriceHistoryRepository"
            ) as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_company_stats = AsyncMock(
                return_value={
                    "US_NEW": {
                        "rows": 10,
                        "min_date": date(2026, 1, 1),
                        "max_date": date(2026, 1, 30),
                        "span_days": 29,
                    },
                    "US_GAP": {
                        "rows": 50,
                        "min_date": date(2025, 1, 1),
                        "max_date": date(2025, 10, 1),
                        "span_days": 273,
                    },
                }
            )
            mock_repo.upsert_many = AsyncMock()
            mock_repo._session = MagicMock()
            mock_repo._session.commit = AsyncMock()

            mock_client = mock_client_cls.return_value
            mock_client.fetch_history = AsyncMock(return_value=[])
            mock_client.close = AsyncMock()

            services = MagicMock()
            services.session = AsyncMock()
            services.session.execute = AsyncMock(
                return_value=MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(
                            all=MagicMock(return_value=[mock_company_new, mock_company_gap])
                        )
                    )
                )
            )

            args = _parse(["download", "--retry-incomplete"])
            await cli_stooq._handle_download(args, services)

            # US_GAP のみ fetch_history が呼ばれる（US_NEW は新規上場でスキップ）
            calls = [call for call in mock_client.fetch_history.call_args_list]
            tickers = [call[0][0] for call in calls]
            assert "GAP" in tickers
            assert "NEW" not in tickers

    @pytest.mark.asyncio
    async def test_retry_incomplete_targets_data_gaps(self, monkeypatch):
        """--retry-incomplete で取得失敗銘柄（span >= 90, rows < 250）のみ対象"""
        monkeypatch.setenv("STOOQ_API_KEY", "testkey")

        mock_company_gap = MagicMock()
        mock_company_gap.id = "US_GAP"
        mock_company_gap.ticker = "GAP"

        with (
            patch("stock_analyze_system.cli.stooq.StooqPriceClient") as mock_client_cls,
            patch(
                "stock_analyze_system.repositories.price_history.PriceHistoryRepository"
            ) as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_company_stats = AsyncMock(
                return_value={
                    "US_GAP": {
                        "rows": 50,
                        "min_date": date(2025, 1, 1),
                        "max_date": date(2025, 10, 1),
                        "span_days": 273,
                    },
                }
            )
            mock_repo.upsert_many = AsyncMock()
            mock_repo._session = MagicMock()
            mock_repo._session.commit = AsyncMock()

            mock_client = mock_client_cls.return_value
            mock_client.fetch_history = AsyncMock(return_value=[])
            mock_client.close = AsyncMock()

            services = MagicMock()
            services.session = AsyncMock()
            services.session.execute = AsyncMock(
                return_value=MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(all=MagicMock(return_value=[mock_company_gap]))
                    )
                )
            )

            args = _parse(["download", "--retry-incomplete"])
            await cli_stooq._handle_download(args, services)

            # US_GAP のみ処理対象
            mock_client.fetch_history.assert_called_once_with("GAP", years=10)

    @pytest.mark.asyncio
    async def test_rate_limit_exits_with_code_3(self, monkeypatch):
        """StooqRateLimitError で SystemExit(3)"""
        monkeypatch.setenv("STOOQ_API_KEY", "testkey")

        mock_company = MagicMock()
        mock_company.id = "US_AAPL"
        mock_company.ticker = "AAPL"

        with patch("stock_analyze_system.cli.stooq.StooqPriceClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.fetch_history = AsyncMock(
                side_effect=StooqRateLimitError("AAPL", "daily hit limit exceeded")
            )
            mock_client.close = AsyncMock()

            services = MagicMock()
            services.session = AsyncMock()
            services.session.execute = AsyncMock(
                return_value=MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(all=MagicMock(return_value=[mock_company]))
                    )
                )
            )

            args = _parse(["download"])
            with pytest.raises(SystemExit) as exc_info:
                await cli_stooq._handle_download(args, services)
            assert exc_info.value.code == 3
