"""GuessTheFrame FastAPI application."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.emby.sync import backfill_search_text, stop_background_sync, sync_scheduler
from app.duels.router import router as duels_router
from app.games.service import backfill_ranking_categories
from app.routers import admin, auth, catalogue, health, leaderboard, media, profile, setup
from app.games.router import router as games_router

configure_logging()
logger = logging.getLogger("guesstheframe.main")
settings = get_settings()

FRONTEND_DIST = settings.project_root / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.frame_cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "%s %s starting (env=%s, frontend=%s)",
        settings.app_name,
        settings.version,
        settings.env,
        settings.frontend_url,
    )
    if not settings.secrets_ready:
        logger.warning(
            "GTF_ENCRYPTION_KEY is not configured. Run scripts/setup.ps1 before using Emby."
        )

    # A previous process may have been killed during a sync.
    try:
        from sqlalchemy import update

        from app.db.base import utcnow
        from app.db.models import SyncRun
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(SyncRun)
                .where(SyncRun.status == "running")
                .values(
                    status="failed",
                    finished_at=utcnow(),
                    error_message="Synchronisation interrompue par un redémarrage.",
                )
            )
            await db.commit()
    except Exception:
        logger.warning("Could not reset interrupted sync runs", exc_info=True)

    try:
        await backfill_search_text()
    except Exception:
        logger.warning("Could not backfill media search text", exc_info=True)

    try:
        await backfill_ranking_categories()
    except Exception:
        logger.warning("Could not backfill ranking categories", exc_info=True)

    app.state.started_at = time.time()
    scheduler_task = asyncio.create_task(sync_scheduler(), name="gtf-scheduler")
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await stop_background_sync()
    logger.info("GuessTheFrame stopped")


app = FastAPI(
    title="GuessTheFrame API",
    version=settings.version,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

install_exception_handlers(app)

if not settings.is_production:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            settings.frontend_url,
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    path = request.url.path
    if path.startswith("/api/") and not path.endswith(("/frame", "/poster")):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.is_production:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'",
        )
    if settings.is_production and settings.session_cookie_secure:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.include_router(health.router, prefix="/api")
app.include_router(setup.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(catalogue.router, prefix="/api")
app.include_router(games_router, prefix="/api")
app.include_router(duels_router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(leaderboard.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "NOT_FOUND", "message": "Route inconnue."}},
            )
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

else:

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "app": settings.app_name,
            "message": "API GuessTheFrame. Le frontend est servi par Vite en développement.",
            "docs": "/api/docs",
        }



