"""Health and readiness endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AppSettings
from app.db.session import get_db

router = APIRouter(tags=["health"])
logger = logging.getLogger("guesstheframe.health")


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    settings = get_settings()
    database = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        database = "error"

    emby_url = settings.emby_url
    emby_configured = False
    emby_server_name: str | None = None
    try:
        row = (
            await db.execute(select(AppSettings).where(AppSettings.id == 1))
        ).scalar_one_or_none()
        if row:
            emby_url = row.emby_url or emby_url
            emby_server_name = row.emby_server_name
            emby_configured = bool(row.emby_url and row.emby_api_key_enc)
    except Exception:
        # The health endpoint must stay usable even before the first migration.
        pass

    return {
        "status": "ok" if database == "ok" else "degraded",
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.env,
        "database": database,
        "emby": {
            "url": emby_url,
            "name": emby_server_name,
            "configured": emby_configured,
        },
    }
