from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from mathmaster_server.achievements import router as achievements_router
from mathmaster_server.authentication import router as auth_router
from mathmaster_server.battles import BattleManager
from mathmaster_server.config import Settings, get_settings
from mathmaster_server.database import Base, build_engine, build_session_factory
from mathmaster_server.leaderboard import router as leaderboard_router
from mathmaster_server.players import router as players_router
from mathmaster_server.rate_limit import InMemoryRateLimiter
from mathmaster_server.websocket import router as websocket_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = build_engine(app_settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_settings.require_secrets()
        Base.metadata.create_all(bind=engine)
        app.state.battle_manager = BattleManager(
            session_factory=session_factory,
            settings=app_settings,
        )
        app.state.battle_manager.start()
        yield
        await app.state.battle_manager.shutdown()
        engine.dispose()

    app = FastAPI(
        title="MathMaster Quiz Battle API",
        version="1.0.0",
        description="Authoritative real-player multiplayer service for MathMaster.",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.rate_limiter = InMemoryRateLimiter()

    origins = [origin.strip() for origin in app_settings.cors_origins.split(",") if origin.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(auth_router)
    app.include_router(players_router)
    app.include_router(achievements_router)
    app.include_router(leaderboard_router)
    app.include_router(websocket_router)

    @app.get("/health", tags=["system"])
    def health():
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/v1/metadata", tags=["system"])
    def metadata():
        manager: BattleManager = app.state.battle_manager
        return {
            "protocol_version": 1,
            "websocket_path": "/v1/ws",
            "result_signature_algorithm": "Ed25519",
            "result_public_key": manager.public_key(),
        }

    return app


app = create_app()

