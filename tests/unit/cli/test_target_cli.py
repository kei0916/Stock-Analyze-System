"""target CLI のテスト"""
import argparse
from unittest.mock import MagicMock

import pytest

from stock_analyze_system.cli.target import handle
from stock_analyze_system.exceptions import NotFoundError
from tests.unit.cli.conftest import make_services as _make_services


class TestTargetList:
    async def test_list(self, capsys):
        svc = _make_services()
        t1 = MagicMock()
        t1.company_id = "US_AAPL"
        t1.source = "manual"
        t1.criteria = None
        svc.target_service.list_targets.return_value = [t1]

        args = argparse.Namespace(action="list", json=False)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "US_AAPL" in out

    async def test_list_empty(self, capsys):
        svc = _make_services()
        svc.target_service.list_targets.return_value = []

        args = argparse.Namespace(action="list", json=False)
        await handle(args, svc)
        out = capsys.readouterr().out
        assert "No" in out


class TestTargetAdd:
    async def test_add(self, capsys):
        svc = _make_services()
        svc.target_service.add_target.return_value = MagicMock()

        args = argparse.Namespace(
            action="add", json=False, company_id="US_AAPL",
        )
        await handle(args, svc)
        svc.target_service.add_target.assert_called_once_with("US_AAPL")
        out = capsys.readouterr().out
        assert "US_AAPL" in out


class TestTargetRemove:
    async def test_remove(self, capsys):
        svc = _make_services()

        args = argparse.Namespace(
            action="remove", json=False, company_id="US_AAPL",
        )
        await handle(args, svc)
        svc.target_service.remove_target.assert_called_once_with("US_AAPL")

    async def test_remove_not_found(self):
        svc = _make_services()
        svc.target_service.remove_target.side_effect = NotFoundError("not found")

        args = argparse.Namespace(
            action="remove", json=False, company_id="US_XXXX",
        )
        with pytest.raises(SystemExit):
            await handle(args, svc)
