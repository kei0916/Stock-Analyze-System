"""worker CLI tests."""
from __future__ import annotations

import argparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from stock_analyze_system.cli import worker as worker_module
from stock_analyze_system.config import AppConfig


def test_register_parser_adds_worker_defaults():
    parser = argparse.ArgumentParser(prog="stock-analyze")
    subparsers = parser.add_subparsers(dest="command")

    worker_module.register_parser(subparsers)

    args = parser.parse_args(["worker"])
    assert args.command == "worker"
    assert args.poll_interval == 2.0
    assert args.handler is worker_module.handle


def test_register_parser_accepts_poll_interval():
    parser = argparse.ArgumentParser(prog="stock-analyze")
    subparsers = parser.add_subparsers(dest="command")

    worker_module.register_parser(subparsers)

    args = parser.parse_args(["worker", "--poll-interval", "0.25"])
    assert args.poll_interval == 0.25


@pytest.mark.parametrize("value", ["0", "-1", "-0.25", "nan", "inf"])
def test_register_parser_rejects_non_positive_poll_interval(value):
    parser = argparse.ArgumentParser(prog="stock-analyze")
    subparsers = parser.add_subparsers(dest="command")

    worker_module.register_parser(subparsers)

    with pytest.raises(SystemExit):
        parser.parse_args(["worker", "--poll-interval", value])


@pytest.mark.asyncio
async def test_handle_runs_worker_and_disposes_resources(monkeypatch):
    config = AppConfig()
    config.database.path = "/tmp/test-worker.db"
    args = argparse.Namespace(poll_interval=0.5)
    engine = SimpleNamespace(dispose=AsyncMock())
    clients = object()
    session_factory = object()
    worker = SimpleNamespace(
        install_signal_handlers=Mock(),
        run_forever=AsyncMock(),
    )
    worker_cls = Mock(return_value=worker)
    async_sessionmaker = Mock(return_value=session_factory)

    create_db_engine = AsyncMock(return_value=engine)
    build_client_bundle = Mock(return_value=clients)
    dispose_clients = AsyncMock()

    monkeypatch.setattr(worker_module, "create_db_engine", create_db_engine)
    monkeypatch.setattr(worker_module, "async_sessionmaker", async_sessionmaker)
    monkeypatch.setattr(worker_module, "build_client_bundle", build_client_bundle)
    monkeypatch.setattr(worker_module, "AnalysisWorker", worker_cls)
    monkeypatch.setattr(worker_module, "dispose_clients", dispose_clients)

    await worker_module.handle(args, config)

    create_db_engine.assert_awaited_once_with(config.database.path)
    async_sessionmaker.assert_called_once_with(engine, expire_on_commit=False)
    build_client_bundle.assert_called_once_with(config)
    worker_cls.assert_called_once_with(
        session_factory=session_factory,
        config=config,
        clients=clients,
        poll_interval=0.5,
    )
    worker.install_signal_handlers.assert_called_once_with()
    worker.run_forever.assert_awaited_once_with()
    dispose_clients.assert_awaited_once_with(clients)
    engine.dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_handle_disposes_engine_when_client_build_fails(monkeypatch):
    config = AppConfig()
    args = argparse.Namespace(poll_interval=2.0)
    engine = SimpleNamespace(dispose=AsyncMock())

    monkeypatch.setattr(worker_module, "create_db_engine", AsyncMock(return_value=engine))
    monkeypatch.setattr(
        worker_module,
        "build_client_bundle",
        Mock(side_effect=RuntimeError("client boom")),
    )
    dispose_clients = AsyncMock()
    monkeypatch.setattr(worker_module, "dispose_clients", dispose_clients)

    with pytest.raises(RuntimeError, match="client boom"):
        await worker_module.handle(args, config)

    dispose_clients.assert_not_awaited()
    engine.dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_handle_disposes_resources_when_worker_raises(monkeypatch):
    config = AppConfig()
    args = argparse.Namespace(poll_interval=2.0)
    engine = SimpleNamespace(dispose=AsyncMock())
    clients = object()
    worker = SimpleNamespace(
        install_signal_handlers=Mock(),
        run_forever=AsyncMock(side_effect=RuntimeError("stop")),
    )

    monkeypatch.setattr(worker_module, "create_db_engine", AsyncMock(return_value=engine))
    monkeypatch.setattr(worker_module, "async_sessionmaker", Mock(return_value=object()))
    monkeypatch.setattr(worker_module, "build_client_bundle", Mock(return_value=clients))
    monkeypatch.setattr(worker_module, "AnalysisWorker", Mock(return_value=worker))
    dispose_clients = AsyncMock()
    monkeypatch.setattr(worker_module, "dispose_clients", dispose_clients)

    with pytest.raises(RuntimeError, match="stop"):
        await worker_module.handle(args, config)

    dispose_clients.assert_awaited_once_with(clients)
    engine.dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_handle_disposes_engine_when_client_dispose_raises(monkeypatch):
    config = AppConfig()
    args = argparse.Namespace(poll_interval=2.0)
    engine = SimpleNamespace(dispose=AsyncMock())
    clients = object()
    worker = SimpleNamespace(
        install_signal_handlers=Mock(),
        run_forever=AsyncMock(),
    )

    monkeypatch.setattr(worker_module, "create_db_engine", AsyncMock(return_value=engine))
    monkeypatch.setattr(worker_module, "async_sessionmaker", Mock(return_value=object()))
    monkeypatch.setattr(worker_module, "build_client_bundle", Mock(return_value=clients))
    monkeypatch.setattr(worker_module, "AnalysisWorker", Mock(return_value=worker))
    monkeypatch.setattr(
        worker_module,
        "dispose_clients",
        AsyncMock(side_effect=RuntimeError("dispose boom")),
    )

    with pytest.raises(RuntimeError, match="dispose boom"):
        await worker_module.handle(args, config)

    engine.dispose.assert_awaited_once_with()
