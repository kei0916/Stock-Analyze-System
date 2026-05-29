"""FastAPI dependencies — engine, session, services, config, clients."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from stock_analyze_system.cli.container import ServiceContainer, setup_services
from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.base import create_db_engine, get_session
from stock_analyze_system.services.analysis_queue import AnalysisQueueService
from stock_analyze_system.shared.clients import ClientBundle

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Application-wide state held on app.state."""

    config: AppConfig
    engine: AsyncEngine
    clients: ClientBundle
    session_factory: async_sessionmaker
    analysis_queue: AnalysisQueueService

    @classmethod
    async def create(cls, config: AppConfig) -> "AppState":
        from stock_analyze_system.shared.clients import build_client_bundle

        engine = await create_db_engine(config.database.path)
        bundle = build_client_bundle(config)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        analysis_queue = AnalysisQueueService(
            session_factory=session_factory,
        )
        return cls(
            config=config,
            engine=engine,
            clients=bundle,
            session_factory=session_factory,
            analysis_queue=analysis_queue,
        )

    async def dispose(self) -> None:
        """全 client + DB engine を close する。"""
        from stock_analyze_system.shared.clients import dispose_clients

        await dispose_clients(self.clients)
        try:
            await self.engine.dispose()
        except Exception as exc:
            logger.warning("dispose: engine close failed: %s", exc, exc_info=exc)


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def get_config(state: AppState = Depends(get_app_state)) -> AppConfig:
    return state.config


def get_engine(state: AppState = Depends(get_app_state)) -> AsyncEngine:
    return state.engine


async def get_session_dep(
    state: AppState = Depends(get_app_state),
) -> AsyncIterator[AsyncSession]:
    async with get_session(state.engine) as session:
        yield session


async def get_services(
    session: AsyncSession = Depends(get_session_dep),
    state: AppState = Depends(get_app_state),
) -> ServiceContainer:
    return await setup_services(session, state.config, clients=state.clients)


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template, context or {}, **kwargs)
