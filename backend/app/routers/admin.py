"""Administration routes: sync, libraries, genres, settings, diagnostics."""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin, require_csrf
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.errors import AppError
from app.db.base import utcnow
from app.db.models import (
    DuelMatch,
    FrameCache,
    Game,
    Genre,
    Library,
    MediaGenre,
    MediaItem,
    SyncRun,
    User,
    UserSession,
)
from app.db.session import get_db
from app.emby.client import EmbyClient, EmbyError, normalize_emby_url
from app.emby.sync import is_sync_running, start_background_sync
from app.services.settings_service import get_or_create_settings

logger = logging.getLogger("guesstheframe.admin")
router = APIRouter(prefix="/admin", tags=["admin"])


class LibraryUpdate(BaseModel):
    is_enabled: bool


class GenreUpdate(BaseModel):
    is_enabled: bool


class GameConfig(BaseModel):
    base_points: int = Field(ge=0, le=1000)
    wrong_attempt_penalty: int = Field(ge=0, le=100)
    max_wrong_penalty: int = Field(ge=0, le=500)
    accept_series_name: bool
    frame_width: int = Field(ge=320, le=3840)
    max_attempts: int = Field(ge=0, le=100)
    answer_similarity: int = Field(default=92, ge=70, le=100)
    allow_library_filter: bool = True
    exclude_solved_default: bool = True
    game_expiry_hours: int = Field(default=24, ge=1, le=720)
    game_inactivity_minutes: int = Field(default=60, ge=5, le=1440)
    duel_hint_penalty_seconds: int = Field(default=20, ge=0, le=300)


class HintItem(BaseModel):
    enabled: bool
    penalty: int = Field(ge=0, le=100)


class HintConfig(BaseModel):
    order: list[str]
    items: dict[str, HintItem]

    @field_validator("order")
    @classmethod
    def _allowed_hints(cls, value: list[str]) -> list[str]:
        allowed = {
            "release_date",
            "director",
            "actor1",
            "actor2",
            "character",
            "studio",
            "media_type",
            "franchise",
            "episode_title",
        }
        if not set(value).issubset(allowed):
            raise ValueError("Type d'indice inconnu.")
        return value


class DifficultyItem(BaseModel):
    max_hints: int = Field(ge=0, le=10)
    wrong_penalty_multiplier: float = Field(ge=0, le=5)
    score_multiplier: float = Field(ge=0, le=5)


class DifficultyConfig(BaseModel):
    easy: DifficultyItem
    normal: DifficultyItem
    hard: DifficultyItem


class SettingsUpdate(BaseModel):
    sync_enabled: bool | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    emby_verify_tls: bool | None = None
    game_config: GameConfig | None = None
    hint_config: HintConfig | None = None
    difficulty_config: DifficultyConfig | None = None


class AdminUserUpdate(BaseModel):
    is_admin: bool
    is_active: bool


class EmbyConfigUpdate(BaseModel):
    url: str = Field(min_length=1, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    verify_tls: bool = True


def _sync_run_payload(run: SyncRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "mode": run.mode,
        "status": run.status,
        "started_at": run.started_at.isoformat() + "Z",
        "finished_at": run.finished_at.isoformat() + "Z" if run.finished_at else None,
        "libraries": run.libraries,
        "items_seen": run.items_seen,
        "added": run.added,
        "updated": run.updated,
        "deactivated": run.deactivated,
        "errors": run.errors,
        "error_message": run.error_message,
    }


@router.get("/sync/status")
async def sync_status(
    _: UserSession = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = (
        await db.execute(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))
    ).scalar_one_or_none()
    total_media = (
        await db.execute(
            select(func.count()).select_from(MediaItem).where(MediaItem.is_active.is_(True))
        )
    ).scalar_one()
    movies = (
        await db.execute(
            select(func.count())
            .select_from(MediaItem)
            .where(MediaItem.is_active.is_(True), MediaItem.type == "movie")
        )
    ).scalar_one()
    episodes = (
        await db.execute(
            select(func.count())
            .select_from(MediaItem)
            .where(MediaItem.is_active.is_(True), MediaItem.type == "episode")
        )
    ).scalar_one()
    config = await get_or_create_settings(db)
    return {
        "running": is_sync_running(),
        "last_sync_at": config.last_sync_at.isoformat() + "Z"
        if config.last_sync_at
        else None,
        "sync_enabled": config.sync_enabled,
        "sync_interval_minutes": config.sync_interval_minutes,
        "last_run": _sync_run_payload(run),
        "catalogue": {
            "media": total_media,
            "movies": movies,
            "episodes": episodes,
        },
    }


@router.post("/sync", status_code=202)
async def trigger_sync(
    _: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    if not config.emby_api_key_enc:
        raise AppError(
            "EMBY_NOT_CONFIGURED",
            "Configurez d'abord le serveur Emby.",
            status_code=409,
        )
    if is_sync_running():
        raise AppError(
            "SYNC_ALREADY_RUNNING",
            "Une synchronisation est déjà en cours.",
            status_code=409,
        )
    await start_background_sync("manual")
    return {"started": True}


@router.get("/libraries")
async def list_libraries(
    _: UserSession = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    libraries = (await db.execute(select(Library).order_by(Library.name))).scalars().all()
    return {
        "libraries": [
            {
                "id": lib.emby_library_id,
                "name": lib.name,
                "collection_type": lib.collection_type,
                "is_enabled": lib.is_enabled,
                "item_count": lib.item_count,
                "last_synced_at": lib.last_synced_at.isoformat() + "Z"
                if lib.last_synced_at
                else None,
            }
            for lib in libraries
        ]
    }


@router.put("/libraries/{library_id}")
async def update_library(
    library_id: str,
    payload: LibraryUpdate,
    _: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    library = (
        await db.execute(select(Library).where(Library.emby_library_id == library_id))
    ).scalar_one_or_none()
    if library is None:
        raise AppError("LIBRARY_NOT_FOUND", "Bibliothèque introuvable.", status_code=404)
    library.is_enabled = payload.is_enabled
    await db.commit()
    return {"ok": True, "id": library_id, "is_enabled": library.is_enabled}


@router.get("/genres")
async def list_genres(
    _: UserSession = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(
                Genre.name,
                Genre.is_enabled,
                func.count(MediaGenre.media_id).label("media_count"),
            )
            .outerjoin(MediaGenre, MediaGenre.genre == Genre.name)
            .group_by(Genre.name, Genre.is_enabled)
            .order_by(Genre.name)
        )
    ).all()
    return {
        "genres": [
            {"name": name, "is_enabled": enabled, "media_count": count}
            for name, enabled, count in rows
        ]
    }


@router.put("/genres/{name}")
async def update_genre(
    name: str,
    payload: GenreUpdate,
    _: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    genre = await db.get(Genre, name)
    if genre is None:
        raise AppError("GENRE_NOT_FOUND", "Genre introuvable.", status_code=404)
    genre.is_enabled = payload.is_enabled
    await db.commit()
    return {"ok": True, "name": name, "is_enabled": genre.is_enabled}


@router.get("/overview")
async def overview(
    _: UserSession = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    games = (await db.execute(select(func.count()).select_from(Game))).scalar_one()
    won = (
        await db.execute(
            select(func.count()).select_from(Game).where(Game.status == "won")
        )
    ).scalar_one()
    config = await get_or_create_settings(db)
    return {
        "users": users,
        "games": games,
        "won": won,
        "setup_complete": bool(config.setup_completed_at),
        "emby": {
            "url": config.emby_url,
            "server_name": config.emby_server_name,
            "version": config.emby_version,
        },
    }


@router.get("/users")
async def list_users(
    _: UserSession = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    games_count = (
        select(Game.user_id, func.count(Game.id).label("games"))
        .group_by(Game.user_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(User, func.coalesce(games_count.c.games, 0))
            .outerjoin(games_count, games_count.c.user_id == User.id)
            .order_by(User.username)
        )
    ).all()
    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "emby_user_id": user.emby_user_id,
                "is_admin": user.is_admin,
                "is_active": user.is_active,
                "games": int(games),
                "last_login_at": user.last_login_at.isoformat() + "Z"
                if user.last_login_at
                else None,
            }
            for user, games in rows
        ]
    }


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "Utilisateur introuvable.", status_code=404)

    if user.id == admin.user_id and not payload.is_active:
        raise AppError(
            "SELF_DEACTIVATION",
            "Vous ne pouvez pas désactiver votre propre compte.",
            status_code=409,
        )

    if user.is_admin and not payload.is_admin:
        admins = (
            await db.execute(
                select(func.count()).select_from(User).where(User.is_admin.is_(True))
            )
        ).scalar_one()
        if admins <= 1:
            raise AppError(
                "LAST_ADMIN",
                "Impossible de retirer le dernier administrateur.",
                status_code=409,
            )

    user.is_admin = payload.is_admin
    user.is_active = payload.is_active
    if not payload.is_active:
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    await db.commit()
    logger.info("User %s updated by %s", user.username, admin.user.username)
    return {
        "ok": True,
        "id": user.id,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
    }


@router.delete("/users/{user_id}/history")
async def reset_user_history(
    user_id: int,
    admin: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "Utilisateur introuvable.", status_code=404)

    await db.execute(
        delete(DuelMatch).where(
            or_(
                DuelMatch.player1_id == user_id,
                DuelMatch.player2_id == user_id,
            )
        )
    )
    result = await db.execute(delete(Game).where(Game.user_id == user_id))
    deleted = int(result.rowcount or 0)
    await db.commit()
    logger.info(
        "History of %s reset by %s (%d games)",
        user.username,
        admin.user.username,
        deleted,
    )
    return {"ok": True, "deleted_games": deleted}


@router.get("/settings")
async def get_settings_route(
    _: UserSession = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    return {
        "emby_url": config.emby_url,
        "emby_verify_tls": config.emby_verify_tls,
        "emby_server_name": config.emby_server_name,
        "emby_version": config.emby_version,
        "emby_api_key_configured": bool(config.emby_api_key_enc),
        "sync_enabled": config.sync_enabled,
        "sync_interval_minutes": config.sync_interval_minutes,
        "last_sync_at": config.last_sync_at.isoformat() + "Z"
        if config.last_sync_at
        else None,
        "game_config": config.game_config,
        "hint_config": config.hint_config,
        "difficulty_config": config.difficulty_config,
    }


@router.put("/settings")
async def update_settings(
    payload: SettingsUpdate,
    admin: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    if payload.sync_enabled is not None:
        config.sync_enabled = payload.sync_enabled
    if payload.sync_interval_minutes is not None:
        config.sync_interval_minutes = payload.sync_interval_minutes
    if payload.emby_verify_tls is not None:
        config.emby_verify_tls = payload.emby_verify_tls
    if payload.game_config is not None:
        config.game_config = payload.game_config.model_dump()
    if payload.hint_config is not None:
        config.hint_config = payload.hint_config.model_dump()
    if payload.difficulty_config is not None:
        config.difficulty_config = payload.difficulty_config.model_dump()
    config.updated_at = utcnow()
    await db.commit()
    logger.info("Settings updated by %s", admin.user.username)
    return {"ok": True}


@router.post("/emby/test")
async def test_emby(
    _: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    api_key = decrypt_secret(config.emby_api_key_enc)
    if not api_key:
        raise AppError(
            "EMBY_NOT_CONFIGURED",
            "Aucune clé API Emby configurée.",
            status_code=409,
        )
    client = EmbyClient(
        config.emby_url, token=api_key, verify_tls=config.emby_verify_tls
    )
    try:
        public = await client.get_public_info()
        system = await client.get_system_info()
    except EmbyError as exc:
        raise AppError(exc.code, exc.user_message, status_code=502) from exc
    return {
        "ok": True,
        "server_name": public.get("ServerName"),
        "version": public.get("Version"),
        "id": public.get("Id"),
        "operating_system": system.get("OperatingSystem"),
    }


def _cache_stats() -> dict[str, Any]:
    env = get_settings()
    directory = env.frame_cache_dir
    files = list(directory.rglob("*.jpg")) if directory.is_dir() else []
    total = sum(path.stat().st_size for path in files if path.is_file())
    return {
        "path": str(directory),
        "files": len(files),
        "bytes": total,
        "megabytes": round(total / (1024 * 1024), 2),
        "max_megabytes": env.frame_cache_max_mb,
    }


@router.get("/cache")
async def cache_status(
    _: UserSession = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.execute(select(func.count()).select_from(FrameCache))
    ).scalar_one()
    return {**_cache_stats(), "db_entries": int(rows or 0)}


@router.post("/cache/purge")
async def purge_cache(
    _: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    env = get_settings()
    before = _cache_stats()

    def _purge() -> None:
        if env.frame_cache_dir.is_dir():
            shutil.rmtree(env.frame_cache_dir)
        env.frame_cache_dir.mkdir(parents=True, exist_ok=True)

    await asyncio.to_thread(_purge)
    await db.execute(delete(FrameCache))
    await db.commit()
    logger.info("Frame cache purged by admin (%s MB)", before["megabytes"])
    return {"ok": True, "freed_megabytes": before["megabytes"]}


@router.put("/emby")
async def update_emby_config(
    payload: EmbyConfigUpdate,
    admin: UserSession = Depends(require_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    api_key = payload.api_key.strip() if payload.api_key else None
    if not api_key:
        api_key = decrypt_secret(config.emby_api_key_enc)
    if not api_key:
        raise AppError(
            "EMBY_KEY_REQUIRED",
            "Une clé API est requise pour configurer Emby.",
            status_code=422,
        )

    client = EmbyClient(
        payload.url, token=api_key, verify_tls=payload.verify_tls, timeout=20.0
    )
    try:
        public = await client.get_public_info()
        system = await client.get_system_info()
        folders = await client.get_media_folders()
    except EmbyError as exc:
        raise AppError(
            exc.code,
            exc.user_message,
            status_code=401 if exc.code == "EMBY_AUTH_FAILED" else 502,
        ) from exc

    config.emby_url = normalize_emby_url(payload.url)
    config.emby_api_key_enc = encrypt_secret(api_key)
    config.emby_verify_tls = payload.verify_tls
    config.emby_server_id = str(public.get("Id") or system.get("Id") or "")
    config.emby_server_name = str(public.get("ServerName", "Emby"))
    config.emby_version = str(public.get("Version", ""))

    for folder in folders:
        collection = folder.get("CollectionType")
        library = (
            await db.execute(
                select(Library).where(
                    Library.emby_library_id == str(folder.get("Id", ""))
                )
            )
        ).scalar_one_or_none()
        if library is None:
            db.add(
                Library(
                    emby_library_id=str(folder.get("Id", "")),
                    name=str(folder.get("Name", "Bibliothèque")),
                    collection_type=collection,
                    is_enabled=collection in {"movies", "tvshows"},
                    item_count=int(
                        folder.get("RecursiveItemCount")
                        or folder.get("ChildCount")
                        or 0
                    ),
                )
            )
        else:
            library.name = str(folder.get("Name", library.name))
            library.collection_type = collection
            library.item_count = int(
                folder.get("RecursiveItemCount") or folder.get("ChildCount") or 0
            )

    await db.commit()
    logger.info("Emby configuration updated by %s", admin.user.username)
    return {
        "ok": True,
        "server_name": config.emby_server_name,
        "version": config.emby_version,
        "id": config.emby_server_id,
        "libraries": len(folders),
    }
