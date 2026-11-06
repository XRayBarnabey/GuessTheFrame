"""First-run Emby configuration routes."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.core.errors import AppError
from app.core.rate_limit import setup_limiter
from app.db.base import utcnow
from app.db.models import Library
from app.db.session import get_db
from app.emby.client import EmbyClient, EmbyError, normalize_emby_url
from app.services.settings_service import get_or_create_settings, is_setup_complete

logger = logging.getLogger("guesstheframe.setup")
router = APIRouter(prefix="/setup", tags=["setup"])
settings = get_settings()


class SetupRequest(BaseModel):
    url: str = Field(min_length=1, max_length=512)
    api_key: str = Field(min_length=1, max_length=512)
    verify_tls: bool = True
    setup_token: str = Field(min_length=1, max_length=256)


class SetupLibrary(BaseModel):
    id: str
    name: str
    collection_type: str | None = None
    item_count: int = 0
    enabled: bool = False


class SetupResponse(BaseModel):
    ok: bool
    server_name: str
    server_version: str
    server_id: str
    libraries: list[SetupLibrary]


class SetupStatus(BaseModel):
    setup_complete: bool
    secrets_ready: bool
    setup_token_required: bool
    emby_url: str
    server_name: str | None = None
    server_version: str | None = None
    libraries: list[SetupLibrary] = []
    ffmpeg: dict[str, Any] = {}


def _check_setup_token(provided: str) -> None:
    if not settings.setup_token_ready:
        raise AppError(
            "SETUP_TOKEN_NOT_CONFIGURED",
            "GTF_SETUP_TOKEN n'est pas configuré. Relancez scripts/setup.ps1.",
            status_code=500,
        )
    if not secrets.compare_digest(provided, settings.setup_token):
        raise AppError(
            "SETUP_TOKEN_INVALID",
            "Jeton d'installation invalide.",
            status_code=403,
        )


async def _validate_connection(
    url: str, api_key: str, verify_tls: bool
) -> tuple[EmbyClient, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    normalized = normalize_emby_url(url)
    client = EmbyClient(normalized, token=api_key.strip(), verify_tls=verify_tls)
    public = await client.get_public_info()
    system = await client.get_system_info()
    folders = await client.get_media_folders()
    return client, public, system, folders


def _library_payload(folder: dict[str, Any]) -> SetupLibrary:
    collection = folder.get("CollectionType")
    return SetupLibrary(
        id=str(folder.get("Id", "")),
        name=str(folder.get("Name", "Bibliothèque")),
        collection_type=collection,
        item_count=int(
            folder.get("RecursiveItemCount") or folder.get("ChildCount") or 0
        ),
        enabled=collection in {"movies", "tvshows"},
    )


@router.get("/status", response_model=SetupStatus)
async def setup_status(db: AsyncSession = Depends(get_db)) -> SetupStatus:
    config = await get_or_create_settings(db)
    libraries = (
        await db.execute(select(Library).order_by(Library.name))
    ).scalars().all()
    complete = is_setup_complete(config)

    ffmpeg_path = settings.ffmpeg_path or ""
    ffmpeg_available = False
    if ffmpeg_path:
        from pathlib import Path

        ffmpeg_available = Path(ffmpeg_path).is_file()
    else:
        from shutil import which

        ffmpeg_available = bool(which("ffmpeg"))

    return SetupStatus(
        setup_complete=complete,
        secrets_ready=settings.secrets_ready,
        setup_token_required=not complete,
        emby_url=config.emby_url,
        server_name=config.emby_server_name,
        server_version=config.emby_version,
        libraries=[
            SetupLibrary(
                id=lib.emby_library_id,
                name=lib.name,
                collection_type=lib.collection_type,
                item_count=lib.item_count,
                enabled=lib.is_enabled,
            )
            for lib in libraries
        ],
        ffmpeg={
            "available": ffmpeg_available,
            "path": ffmpeg_path or "ffmpeg (PATH)",
        },
    )


@router.post("/test", response_model=SetupResponse)
async def test_connection(
    payload: SetupRequest,
    request: Request,
) -> SetupResponse:
    await setup_limiter.hit(
        f"setup:{(request.client.host if request.client else 'unknown')}"
    )
    _check_setup_token(payload.setup_token)
    try:
        _, public, _, folders = await _validate_connection(
            payload.url, payload.api_key, payload.verify_tls
        )
    except EmbyError as exc:
        raise AppError(
            exc.code,
            exc.user_message,
            status_code=401 if exc.code == "EMBY_AUTH_FAILED" else 502,
        ) from exc

    return SetupResponse(
        ok=True,
        server_name=str(public.get("ServerName", "Emby")),
        server_version=str(public.get("Version", "")),
        server_id=str(public.get("Id", "")),
        libraries=[_library_payload(folder) for folder in folders],
    )


@router.post("/emby", response_model=SetupResponse)
async def configure_emby(
    payload: SetupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SetupResponse:
    await setup_limiter.hit(
        f"setup:{(request.client.host if request.client else 'unknown')}"
    )
    _check_setup_token(payload.setup_token)

    config = await get_or_create_settings(db)
    if is_setup_complete(config):
        raise AppError(
            "SETUP_ALREADY_COMPLETE",
            "GuessTheFrame est déjà configuré. Utilisez l'administration.",
            status_code=409,
        )

    try:
        _, public, system, folders = await _validate_connection(
            payload.url, payload.api_key, payload.verify_tls
        )
    except EmbyError as exc:
        raise AppError(
            exc.code,
            exc.user_message,
            status_code=401 if exc.code == "EMBY_AUTH_FAILED" else 502,
        ) from exc

    server_id = str(public.get("Id") or system.get("Id") or "")
    if not server_id:
        raise AppError(
            "EMBY_SERVER_ID_MISSING",
            "Le serveur Emby n'a pas fourni son identifiant.",
            status_code=502,
        )

    config.emby_url = normalize_emby_url(payload.url)
    config.emby_api_key_enc = encrypt_secret(payload.api_key.strip())
    config.emby_verify_tls = payload.verify_tls
    config.emby_server_id = server_id
    config.emby_server_name = str(public.get("ServerName", "Emby"))
    config.emby_version = str(public.get("Version", ""))
    config.setup_completed_at = utcnow()
    config.updated_at = utcnow()
    await db.commit()

    libraries: list[SetupLibrary] = []
    for folder in folders:
        item = _library_payload(folder)
        existing = (
            await db.execute(
                select(Library).where(Library.emby_library_id == item.id)
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = Library(
                emby_library_id=item.id,
                name=item.name,
                collection_type=item.collection_type,
                is_enabled=item.enabled,
                item_count=item.item_count,
                last_synced_at=None,
            )
            db.add(existing)
        else:
            existing.name = item.name
            existing.collection_type = item.collection_type
            existing.item_count = item.item_count
        libraries.append(item)

    await db.commit()
    logger.info(
        "Emby configured: %s (%s) with %d libraries",
        config.emby_server_name,
        config.emby_version,
        len(folders),
    )

    return SetupResponse(
        ok=True,
        server_name=config.emby_server_name or "Emby",
        server_version=config.emby_version or "",
        server_id=server_id,
        libraries=libraries,
    )
