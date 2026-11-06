"""Game API routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_csrf, require_session
from app.core.errors import AppError
from app.core.rate_limit import frame_limiter
from app.db.models import Game, Genre, Library, MediaGenre, MediaItem, UserSession
from app.db.session import get_db
from app.frames.service import FRAME_COUNTS, apply_dezoom, ensure_frame
from app.games.service import (
    abandon_game,
    build_result,
    create_game,
    get_owned_game,
    public_state,
    reveal_hint,
    submit_attempt,
    touch_game,
)
from app.services.settings_service import get_or_create_settings

router = APIRouter(tags=["games"])


class CreateGameRequest(BaseModel):
    media_types: list[Literal["movie", "episode"]] = Field(
        default_factory=lambda: ["movie", "episode"]
    )
    genres: list[str] = Field(default_factory=list)
    library_ids: list[str] | None = None
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    mode: Literal["classic", "frames3", "frames5", "dezoom", "daily"] = "classic"
    exclude_solved: bool | None = None

    @field_validator("media_types", "genres")
    @classmethod
    def _dedupe(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class AttemptRequest(BaseModel):
    guess: str = Field(min_length=1, max_length=500)


class HintRequest(BaseModel):
    hint_key: str | None = Field(default=None, max_length=64)


@router.get("/game/options")
async def game_options(
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    game_config = config.game_config or {}
    active = MediaItem.is_active.is_(True)

    type_rows = (
        await db.execute(
            select(MediaItem.type, func.count())
            .where(active)
            .group_by(MediaItem.type)
        )
    ).all()
    type_counts = {media_type: count for media_type, count in type_rows}

    genre_rows = (
        await db.execute(
            select(Genre.name, func.count(func.distinct(MediaGenre.media_id)))
            .join(MediaGenre, MediaGenre.genre == Genre.name)
            .join(MediaItem, MediaItem.id == MediaGenre.media_id)
            .where(Genre.is_enabled.is_(True), active)
            .group_by(Genre.name)
            .order_by(Genre.name)
        )
    ).all()

    library_rows = (
        await db.execute(
            select(
                Library.emby_library_id,
                Library.name,
                Library.collection_type,
                func.count(MediaItem.id).label("count"),
            )
            .join(MediaItem, MediaItem.library_id == Library.id)
            .where(Library.is_enabled.is_(True), active)
            .group_by(
                Library.id,
                Library.emby_library_id,
                Library.name,
                Library.collection_type,
            )
            .order_by(Library.name)
        )
    ).all()

    solved_media = (
        await db.execute(
            select(func.count(func.distinct(Game.media_id))).where(
                Game.user_id == session.user_id, Game.status == "won"
            )
        )
    ).scalar_one()

    difficulties = []
    for key in ("easy", "normal", "hard"):
        diff = (config.difficulty_config or {}).get(key) or {}
        difficulties.append(
            {
                "key": key,
                "max_hints": int(diff.get("max_hints", 0)),
                "score_multiplier": float(diff.get("score_multiplier", 1.0)),
            }
        )

    return {
        "types": [
            {
                "value": "movie",
                "label": "Films",
                "count": int(type_counts.get("movie", 0)),
            },
            {
                "value": "episode",
                "label": "Séries",
                "count": int(type_counts.get("episode", 0)),
            },
        ],
        "genres": [
            {"name": name, "media_count": int(count)} for name, count in genre_rows
        ],
        "libraries": [
            {
                "id": library_id,
                "name": name,
                "collection_type": collection_type,
                "media_count": int(count),
            }
            for library_id, name, collection_type, count in library_rows
        ],
        "difficulties": difficulties,
        "defaults": {
            "media_types": ["movie", "episode"],
            "difficulty": "normal",
            "exclude_solved": bool(game_config.get("exclude_solved_default", True)),
            "allow_library_filter": bool(game_config.get("allow_library_filter", True)),
        },
        "excluded_solved": int(solved_media or 0),
        "min_runtime_seconds": 120,
    }


@router.post("/games", status_code=201)
async def create_game_route(
    payload: CreateGameRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    game = await create_game(
        db,
        session=session,
        config=config,
        media_types=payload.media_types,
        genres=payload.genres,
        library_ids=payload.library_ids,
        difficulty=payload.difficulty,
        exclude_solved=payload.exclude_solved,
        mode=payload.mode,
    )
    return public_state(game, config)


@router.get("/games/{game_id}")
async def get_game_route(
    game_id: str,
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    game = await get_owned_game(db, game_id, session.user_id)
    await touch_game(db, game)
    state = public_state(game, config)
    if game.status != "in_progress":
        state["result"] = await build_result(db, game, config)
    return state


@router.get("/games/{game_id}/frame")
async def game_frame(
    game_id: str,
    index: int = Query(default=0, ge=0, le=4),
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    await frame_limiter.hit(f"frame:{session.user_id}")
    config = await get_or_create_settings(db)
    game = await get_owned_game(db, game_id, session.user_id)
    await touch_game(db, game)
    count = FRAME_COUNTS.get(game.mode or "classic", 1)
    if index >= count:
        raise AppError("FRAME_INDEX_INVALID", "Index d'image invalide.", status_code=404)
    path = await ensure_frame(db, game, config, index)
    zoom_suffix = ""
    if (game.mode or "classic") == "dezoom" and game.status == "in_progress":
        keys = list(game.frame_keys or [])
        if index < len(keys):
            path = await apply_dezoom(path, keys[index], game.attempts_count)
            zoom_suffix = f"-z{game.attempts_count}"
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": f'"frame-{game.frame_cache_key}-{index}{zoom_suffix}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/games/{game_id}/attempts")
async def submit_attempt_route(
    game_id: str,
    payload: AttemptRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    return await submit_attempt(
        db,
        game_id=game_id,
        user_id=session.user_id,
        guess=payload.guess,
        config=config,
    )


@router.post("/games/{game_id}/hints")
async def reveal_hint_route(
    game_id: str,
    payload: HintRequest | None = None,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    return await reveal_hint(
        db,
        game_id=game_id,
        user_id=session.user_id,
        config=config,
        hint_key=payload.hint_key if payload else None,
    )


@router.post("/games/{game_id}/abandon")
async def abandon_game_route(
    game_id: str,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    return await abandon_game(
        db, game_id=game_id, user_id=session.user_id, config=config
    )


@router.get("/games/{game_id}/result")
async def game_result(
    game_id: str,
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await get_or_create_settings(db)
    game = await get_owned_game(db, game_id, session.user_id)
    if game.status == "in_progress":
        raise AppError(
            "GAME_NOT_FINISHED",
            "La partie n'est pas encore terminée.",
            status_code=409,
        )
    return await build_result(db, game, config)
