"""Background analysis worker subcommand."""
from __future__ import annotations

import argparse
import math

from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.base import create_db_engine
from stock_analyze_system.services.analysis_worker import AnalysisWorker
from stock_analyze_system.shared.clients import build_client_bundle, dispose_clients


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError(
            f"poll interval must be positive, got {value}",
        )
    return parsed


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the `worker` subcommand."""
    parser = subparsers.add_parser("worker", help="Background analysis worker")
    parser.add_argument(
        "--poll-interval",
        type=_positive_float,
        default=2.0,
        help="Seconds to wait between polling for pending jobs",
    )
    parser.set_defaults(handler=handle)


async def handle(args: argparse.Namespace, config: AppConfig) -> None:
    """Run the background analysis worker until interrupted."""
    engine = await create_db_engine(config.database.path)
    clients = None
    try:
        clients = build_client_bundle(config)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        worker = AnalysisWorker(
            session_factory=session_factory,
            config=config,
            clients=clients,
            poll_interval=args.poll_interval,
        )
        worker.install_signal_handlers()
        await worker.run_forever()
    finally:
        try:
            if clients is not None:
                await dispose_clients(clients)
        finally:
            await engine.dispose()
