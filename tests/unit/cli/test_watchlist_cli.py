# tests/unit/cli/test_watchlist_cli.py
"""watchlist CLI のテスト (Bug #17 修正含む)"""
import argparse
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli.watchlist import handle
from stock_analyze_system.exceptions import DuplicateError, NotFoundError
from tests.unit.cli.conftest import make_services as _make_services


class TestBug17HandlerSignature:
    """Bug #17: 全ハンドラが services を受け取ること"""

    async def test_create_uses_services(self, capsys):
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "My List"
        svc.watchlist_service.create_watchlist.return_value = wl

        args = argparse.Namespace(
            action="create", json=False,
            name="My List", description=None,
        )
        await handle(args, svc)
        svc.watchlist_service.create_watchlist.assert_called_once()

    async def test_list_uses_services(self, capsys):
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "My List"
        wl.description = "Test"
        svc.watchlist_service.list_watchlists.return_value = [wl]

        args = argparse.Namespace(action="list", json=False)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "My List" in out


class TestWatchlistCreate:
    async def test_create(self, capsys):
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "Growth"
        svc.watchlist_service.create_watchlist.return_value = wl

        args = argparse.Namespace(
            action="create", json=False,
            name="Growth", description="Growth stocks",
        )
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "Growth" in out

    async def test_create_duplicate(self, capsys):
        svc = _make_services()
        svc.watchlist_service.create_watchlist.side_effect = DuplicateError("exists")

        args = argparse.Namespace(
            action="create", json=False,
            name="Growth", description=None,
        )
        with pytest.raises(SystemExit):
            await handle(args, svc)


class TestWatchlistShow:
    async def test_show(self, capsys):
        svc = _make_services()
        item = MagicMock()
        item.company_id = "US_AAPL"
        item.status = "monitoring"
        wl = MagicMock()
        wl.id = 1
        wl.name = "My List"
        wl.description = "Test"
        wl.items = [item]
        svc.watchlist_service.get_with_items = AsyncMock(return_value=wl)

        args = argparse.Namespace(action="show", json=False, watchlist_id=1)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "US_AAPL" in out


class TestWatchlistAddRemove:
    async def test_add(self, capsys):
        svc = _make_services()
        svc.watchlist_service.add_item.return_value = MagicMock()

        args = argparse.Namespace(
            action="add", json=False,
            watchlist_id=1, company_id="US_AAPL",
        )
        await handle(args, svc)
        svc.watchlist_service.add_item.assert_called_once_with(1, "US_AAPL")

    async def test_remove(self, capsys):
        svc = _make_services()

        args = argparse.Namespace(
            action="remove", json=False,
            watchlist_id=1, company_id="US_AAPL",
        )
        await handle(args, svc)
        svc.watchlist_service.remove_item.assert_called_once_with(1, "US_AAPL")

    async def test_remove_not_found(self):
        svc = _make_services()
        svc.watchlist_service.remove_item.side_effect = NotFoundError("not found")

        args = argparse.Namespace(
            action="remove", json=False,
            watchlist_id=1, company_id="US_XXXX",
        )
        with pytest.raises(SystemExit):
            await handle(args, svc)


class TestWatchlistCliErrorPaths:
    async def test_no_action_exits(self):
        """action 未指定時は sys.exit(1)"""
        svc = _make_services()
        args = argparse.Namespace(json=False)
        with pytest.raises(SystemExit):
            await handle(args, svc)

    async def test_create_json_output(self, capsys):
        """_handle_create の json 分岐"""
        svc = _make_services()
        wl = MagicMock()
        wl.id = 7
        wl.name = "Growth"
        svc.watchlist_service.create_watchlist.return_value = wl
        args = argparse.Namespace(
            action="create", json=True, name="Growth", description=None,
        )
        await handle(args, svc)
        out = capsys.readouterr().out
        assert '"id": 7' in out

    async def test_list_empty(self, capsys):
        """_handle_list: 0件時のメッセージ"""
        svc = _make_services()
        svc.watchlist_service.list_watchlists.return_value = []
        args = argparse.Namespace(action="list", json=False)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "No watchlists found" in out

    async def test_list_json_output(self, capsys):
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "L"
        wl.description = None
        svc.watchlist_service.list_watchlists.return_value = [wl]
        args = argparse.Namespace(action="list", json=True)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert '"ID": 1' in out

    async def test_show_unknown_exits(self):
        """_handle_show: get_with_items が None なら exit(1)"""
        svc = _make_services()
        svc.watchlist_service.get_with_items = AsyncMock(return_value=None)
        args = argparse.Namespace(action="show", json=False, watchlist_id=999)
        with pytest.raises(SystemExit):
            await handle(args, svc)

    async def test_show_json_empty_items(self, capsys):
        """_handle_show: items=0 & json=True"""
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "L"
        wl.description = None
        wl.items = []
        svc.watchlist_service.get_with_items = AsyncMock(return_value=wl)
        args = argparse.Namespace(action="show", json=True, watchlist_id=1)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert '"items": []' in out

    async def test_show_empty_items_text(self, capsys):
        """_handle_show: items=0 & json=False → (empty) 表示"""
        svc = _make_services()
        wl = MagicMock()
        wl.id = 1
        wl.name = "L"
        wl.description = None
        wl.items = []
        svc.watchlist_service.get_with_items = AsyncMock(return_value=wl)
        args = argparse.Namespace(action="show", json=False, watchlist_id=1)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "(empty)" in out

    async def test_add_not_found_exits(self):
        """_handle_add: add_item が NotFoundError を出したら exit(1)"""
        svc = _make_services()
        svc.watchlist_service.add_item.side_effect = NotFoundError("not found")
        args = argparse.Namespace(
            action="add", json=False, watchlist_id=1, company_id="US_X",
        )
        with pytest.raises(SystemExit):
            await handle(args, svc)
