"""screening CLI のテスト."""
from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli import screening as cli_screening
from stock_analyze_system.cli.container import ServiceContainer
from stock_analyze_system.services.screening import (
    AddToTargetsResult,
    ScreenResult,
    ScreenResultItem,
    ScreenSpec,
)
from stock_analyze_system.services.screening_metrics import RefreshMetricsResult
from stock_analyze_system.services.screening_universe import (
    EnrichResult,
    RefreshUniverseResult,
)


def _parse(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    cli_screening.register_parser(sub)
    return parser.parse_args(["screening", *argv])


def _make_services(
    *,
    universe=None,
    screen=None,
    screening_metrics_service=AsyncMock(),
) -> ServiceContainer:
    return ServiceContainer(
        company_service=MagicMock(), financial_service=MagicMock(),
        valuation_service=MagicMock(), filing_service=MagicMock(),
        watchlist_service=MagicMock(), target_service=MagicMock(),
        job_service=MagicMock(), financial_sync=MagicMock(),
        filing_sync=MagicMock(),
        filing_content_service=MagicMock(),
        screening_universe_service=universe,
        screening_service=screen,
        screening_metrics_service=screening_metrics_service,
    )


class TestCli:
    @pytest.mark.asyncio
    async def test_screening_service_none_exits_1(self, capsys):
        # fields は services 不要なので、 services 必須の run で確認
        args = _parse(["run"])
        with pytest.raises(SystemExit) as ei:
            await cli_screening.handle(args, _make_services())
        assert ei.value.code == 1
        err = capsys.readouterr().err
        assert "unavailable" in err

    @pytest.mark.asyncio
    async def test_fields_works_without_services(self, capsys):
        await cli_screening.handle(_parse(["fields"]), _make_services())
        out = capsys.readouterr().out
        assert "trailing_per" in out
        assert "sector" in out

    @pytest.mark.asyncio
    async def test_universe_refresh_calls_service(self, capsys):
        univ = MagicMock()
        univ.refresh_universe = AsyncMock(return_value=RefreshUniverseResult(
            fetched=10, inserted=8, updated=2, skipped=0,
        ))
        screen = MagicMock()
        await cli_screening.handle(
            _parse(["universe", "refresh"]),
            _make_services(universe=univ, screen=screen),
        )
        out = capsys.readouterr().out
        assert "fetched: 10" in out
        assert "inserted: 8, updated: 2" in out

    @pytest.mark.asyncio
    async def test_refresh_calls_enrich(self):
        univ = MagicMock()
        univ.refresh_universe = AsyncMock(return_value=RefreshUniverseResult(
            fetched=2, inserted=1, updated=1, skipped=0,
        ))
        univ.enrich_with_yahoo = AsyncMock(return_value=EnrichResult(
            eligible=5, attempted=5, succeeded=4, failed=1, skipped=0,
            elapsed_seconds=1.2,
        ))
        screen = MagicMock()
        await cli_screening.handle(
            _parse(["refresh", "--limit", "5", "--concurrency", "2"]),
            _make_services(universe=univ, screen=screen),
        )
        univ.enrich_with_yahoo.assert_awaited_with(
            limit=5, stale_hours=24, max_concurrency=2,
        )

    @pytest.mark.asyncio
    async def test_refresh_yahoo_refreshes_universe_before_enrich(self, capsys):
        calls = []
        univ = MagicMock()

        async def refresh_universe():
            calls.append("universe")
            return RefreshUniverseResult(
                fetched=2, inserted=1, updated=1, skipped=0,
            )

        async def enrich_with_yahoo(**_kwargs):
            calls.append("enrich")
            return EnrichResult(
                eligible=1, attempted=1, succeeded=1, failed=0, skipped=0,
                elapsed_seconds=0.1,
            )

        univ.refresh_universe = AsyncMock(side_effect=refresh_universe)
        univ.enrich_with_yahoo = AsyncMock(side_effect=enrich_with_yahoo)
        await cli_screening.handle(
            _parse(["refresh", "--source", "yahoo"]),
            _make_services(universe=univ, screen=MagicMock()),
        )

        assert calls == ["universe", "enrich"]
        out = capsys.readouterr().out
        assert "Universe refresh" in out

    @pytest.mark.asyncio
    async def test_run_parses_filters_and_calls_run_screen(self):
        univ = MagicMock()
        screen = MagicMock()
        screen.run_screen = AsyncMock(return_value=ScreenResult(
            items=[], total_matched=0, spec=ScreenSpec(), limit=50, offset=0,
        ))
        await cli_screening.handle(
            _parse([
                "run",
                "--gte", "roe=0.15",
                "--lte", "trailing_per=15",
                "--between", "market_cap=1e9,1e12",
                "--in", "exchange=Nasdaq,NYSE",
                "--sort", "market_cap",
            ]),
            _make_services(universe=univ, screen=screen),
        )
        spec = screen.run_screen.await_args.args[0]
        ops = [(c.field, c.op) for c in spec.filters]
        assert ("roe", "gte") in ops
        assert ("trailing_per", "lte") in ops
        assert ("market_cap", "between") in ops
        assert ("exchange", "in") in ops
        assert spec.sort.field == "market_cap"
        assert spec.sort.desc is True

    def test_run_accepts_desc_flag(self):
        args = _parse(["run", "--desc"])
        assert args.desc is True

    def test_run_asc_sets_desc_false(self):
        args = _parse(["run", "--asc"])
        assert args.desc is False

    def test_run_rejects_asc_and_desc_together(self):
        with pytest.raises(SystemExit):
            _parse(["run", "--asc", "--desc"])

    @pytest.mark.asyncio
    async def test_run_json_emits_json(self, capsys):
        univ = MagicMock()
        screen = MagicMock()
        screen.run_screen = AsyncMock(return_value=ScreenResult(
            items=[
                ScreenResultItem(
                    company_id="US_AAPL", ticker="AAPL", name="Apple",
                    sector="Tech", market="Nasdaq",
                    metrics={"roe": 1.45, "market_cap": 3.5e12},
                ),
            ],
            total_matched=1, spec=ScreenSpec(), limit=50, offset=0,
        ))
        await cli_screening.handle(
            _parse(["run", "--json"]),
            _make_services(universe=univ, screen=screen),
        )
        out = capsys.readouterr().out.strip()
        import json
        body = json.loads(out)
        assert body["items"][0]["company_id"] == "US_AAPL"
        assert body["total_matched"] == 1

    @pytest.mark.asyncio
    async def test_add_targets_calls_service(self, capsys):
        univ = MagicMock()
        screen = MagicMock()
        screen.add_to_targets = AsyncMock(return_value=AddToTargetsResult(
            requested=2, added=1, already_present=1, skipped=0,
        ))
        await cli_screening.handle(
            _parse(["add-targets", "US_AAPL", "US_MSFT"]),
            _make_services(universe=univ, screen=screen),
        )
        out = capsys.readouterr().out
        assert "added=1 already_present=1" in out


class TestScreeningRefreshSource:
    def test_refresh_accepts_sec_google_source(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        cli_screening.register_parser(sub)

        args = parser.parse_args(["screening", "refresh", "--source", "sec-google"])
        assert args.source == "sec-google"

    @pytest.mark.asyncio
    async def test_refresh_sec_google_runs_metrics_service(self, capsys):
        univ = MagicMock()
        univ.refresh_universe = AsyncMock(return_value=RefreshUniverseResult(
            fetched=2, inserted=1, updated=1, skipped=0,
        ))
        svc = _make_services(universe=univ, screen=MagicMock())
        result = RefreshMetricsResult(
            eligible=10, processed=10, succeeded=8,
            skipped_no_financials=1, skipped_no_quote=1, failed=0,
        )
        svc.screening_metrics_service.refresh_from_sec_google.return_value = result

        args = _parse(["refresh", "--source", "sec-google"])
        await cli_screening.handle(args, svc)

        svc.screening_metrics_service.refresh_from_sec_google.assert_awaited_once_with(
            limit=None,
            refresh_universe=False,
        )
        out = capsys.readouterr().out
        assert "sec-google" in out
        assert "succeeded: 8" in out

    @pytest.mark.asyncio
    async def test_refresh_sec_google_refreshes_universe_first(self):
        calls = []
        univ = MagicMock()

        async def refresh_universe():
            calls.append("universe")
            return RefreshUniverseResult(
                fetched=2, inserted=1, updated=1, skipped=0,
            )

        async def refresh_metrics(*, limit=None, refresh_universe=True):
            assert limit is None
            assert refresh_universe is False
            calls.append("metrics")
            return RefreshMetricsResult(
                eligible=1, processed=1, succeeded=1,
                skipped_no_financials=0, skipped_no_quote=0, failed=0,
            )

        univ.refresh_universe = AsyncMock(side_effect=refresh_universe)
        metrics = AsyncMock()
        metrics.refresh_from_sec_google = AsyncMock(side_effect=refresh_metrics)
        svc = _make_services(
            universe=univ,
            screen=MagicMock(),
            screening_metrics_service=metrics,
        )

        args = _parse(["refresh", "--source", "sec-google"])
        await cli_screening.handle(args, svc)

        assert calls == ["universe", "metrics"]

    @pytest.mark.asyncio
    async def test_refresh_sec_google_exits_when_service_unavailable(self, capsys):
        svc = _make_services(screening_metrics_service=None)
        args = _parse(["refresh", "--source", "sec-google"])
        with pytest.raises(SystemExit) as exc_info:
            await cli_screening.handle(args, svc)
        assert exc_info.value.code == 1
        assert "unavailable" in capsys.readouterr().err.lower()
