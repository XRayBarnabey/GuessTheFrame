"""Personal statistics and game history."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    require_csrf,
    require_session,
    serialize_user,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.text import normalize
from app.db.models import Game, Library, MediaItem, UserSession
from app.db.session import get_db

router = APIRouter(prefix="/users/me", tags=["profile"])

MAX_SHOWCASE_ITEMS = 5
MAX_AVATAR_BYTES = 5 * 1024 * 1024


class PreferencesUpdate(BaseModel):
    show_in_leaderboard: bool


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=40)


class ShowcaseUpdate(BaseModel):
    media_ids: list[int] = Field(default_factory=list, max_length=MAX_SHOWCASE_ITEMS)


def _iso(value):  # type: ignore[no-untyped-def]
    return value.isoformat() + "Z" if value else None


def _is_anime(media: MediaItem, library_name: str | None) -> bool:
    if "anime" in normalize(library_name or ""):
        return True
    return any(normalize(genre or "") == "anime" for genre in (media.genres or []))


def _poster_url(media: MediaItem) -> str | None:
    if media.poster_tag or media.series_id:
        return f"/api/media/{media.id}/poster"
    return None


def _showcase_item(
    media: MediaItem, library_name: str | None
) -> dict[str, Any]:
    if media.type == "episode":
        title = media.series_name or media.title
        kind = "anime" if _is_anime(media, library_name) else "series"
        subtitle = media.episode_title
        if media.season_number is not None and media.episode_number is not None:
            subtitle = (
                f"S{int(media.season_number):02d}E{int(media.episode_number):02d} "
                f"· {subtitle or ''}"
            ).strip(" ·")
    else:
        title = media.title
        kind = "movie"
        subtitle = None
    return {
        "media_id": media.id,
        "title": title,
        "kind": kind,
        "year": media.year,
        "subtitle": subtitle,
        "poster_url": _poster_url(media),
    }


async def _showcase_items(
    db: AsyncSession, media_ids: list[int]
) -> list[dict[str, Any]]:
    if not media_ids:
        return []
    rows = (
        await db.execute(
            select(MediaItem, Library.name)
            .outerjoin(Library, Library.id == MediaItem.library_id)
            .where(MediaItem.id.in_(media_ids), MediaItem.is_active.is_(True))
        )
    ).all()
    by_id = {media.id: (media, library_name) for media, library_name in rows}
    items: list[dict[str, Any]] = []
    for media_id in media_ids:
        entry = by_id.get(media_id)
        if entry is not None:
            items.append(_showcase_item(*entry))
    return items


@router.get("/stats")
async def my_stats(
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    finished = Game.user_id == session.user_id
    total = (
        await db.execute(select(func.count()).select_from(Game).where(finished))
    ).scalar_one()
    won = (
        await db.execute(
            select(func.count())
            .select_from(Game)
            .where(finished, Game.status == "won")
        )
    ).scalar_one()
    total_score = (
        await db.execute(
            select(func.coalesce(func.sum(Game.score), 0)).where(
                finished, Game.status == "won"
            )
        )
    ).scalar_one()
    best_score = (
        await db.execute(
            select(func.max(Game.score)).where(finished, Game.status == "won")
        )
    ).scalar_one()
    avg_attempts = (
        await db.execute(
            select(func.avg(Game.attempts_count)).where(
                finished, Game.status == "won"
            )
        )
    ).scalar_one()
    avg_duration = (
        await db.execute(
            select(func.avg(Game.duration_seconds)).where(
                finished, Game.status == "won"
            )
        )
    ).scalar_one()

    return {
        "games": int(total or 0),
        "wins": int(won or 0),
        "win_rate": round((int(won or 0) / int(total)) * 100, 1) if total else 0.0,
        "score": int(total_score or 0),
        "best_score": int(best_score or 0),
        "avg_attempts": round(float(avg_attempts), 1) if avg_attempts else 0.0,
        "avg_duration_seconds": round(float(avg_duration)) if avg_duration else 0,
        "show_in_leaderboard": session.user.show_in_leaderboard,
    }


@router.put("/preferences")
async def update_preferences(
    payload: PreferencesUpdate,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session.user.show_in_leaderboard = payload.show_in_leaderboard
    await db.commit()
    return serialize_user(session.user)


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdate,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    display_name = (payload.display_name or "").strip()
    if display_name and len(display_name) < 2:
        raise AppError(
            "DISPLAY_NAME_TOO_SHORT",
            "Le pseudo doit contenir au moins 2 caractères.",
            status_code=422,
        )
    session.user.display_name = display_name or None
    await db.commit()
    return serialize_user(session.user)


@router.post("/avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    content = await avatar.read(MAX_AVATAR_BYTES + 1)
    if not content:
        raise AppError("AVATAR_EMPTY", "Le fichier image est vide.", status_code=422)
    if len(content) > MAX_AVATAR_BYTES:
        raise AppError(
            "AVATAR_TOO_LARGE",
            "L'image ne doit pas dépasser 5 Mo.",
            status_code=413,
        )
    try:
        with Image.open(BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image = ImageOps.fit(
                image,
                (256, 256),
                method=Image.Resampling.LANCZOS,
            )
            target_dir = get_settings().data_dir / "avatars"
            target_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{uuid4().hex[:12]}.jpg"
            target = target_dir / f"user-{session.user_id}-{filename}"
            image.save(target, format="JPEG", quality=88, optimize=True)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "AVATAR_INVALID",
            "Le fichier envoyé n'est pas une image valide.",
            status_code=422,
        ) from exc

    previous = session.user.avatar_path
    session.user.avatar_path = target.name
    session.user.avatar_version += 1
    await db.commit()
    if previous:
        old_path = get_settings().data_dir / "avatars" / previous
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            pass
    return serialize_user(session.user)


@router.get("/avatar")
async def avatar_image(
    session: UserSession = Depends(require_session),
) -> FileResponse:
    if not session.user.avatar_path:
        raise AppError("AVATAR_NOT_FOUND", "Aucune image de profil.", status_code=404)
    target = get_settings().data_dir / "avatars" / session.user.avatar_path
    if not target.is_file():
        raise AppError("AVATAR_NOT_FOUND", "Aucune image de profil.", status_code=404)
    return FileResponse(
        target,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/avatar")
async def delete_avatar(
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = session.user.avatar_path
    session.user.avatar_path = None
    session.user.avatar_version += 1
    await db.commit()
    if previous:
        old_path = get_settings().data_dir / "avatars" / previous
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            pass
    return serialize_user(session.user)


@router.get("/showcase/search")
async def search_showcase(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
    _: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    needle = normalize(q)
    if len(needle) < 2:
        return {"items": []}
    rows = (
        await db.execute(
            select(MediaItem, Library.name)
            .outerjoin(Library, Library.id == MediaItem.library_id)
            .where(
                MediaItem.is_active.is_(True),
                MediaItem.search_text.contains(needle),
            )
            .limit(240)
        )
    ).all()
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for media, library_name in rows:
        item = _showcase_item(media, library_name)
        key = (item["kind"], normalize(item["title"] or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        items.append(item)
    items.sort(
        key=lambda item: (
            0 if normalize(item["title"]).startswith(needle) else 1,
            normalize(item["title"]),
        )
    )
    return {"items": items[:limit]}


@router.get("/showcase")
async def get_showcase(
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return {
        "items": await _showcase_items(
            db, list(session.user.showcase_media_ids or [])
        )
    }


@router.put("/showcase")
async def update_showcase(
    payload: ShowcaseUpdate,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    media_ids = list(dict.fromkeys(payload.media_ids))
    if len(media_ids) > MAX_SHOWCASE_ITEMS:
        raise AppError(
            "SHOWCASE_TOO_MANY",
            f"La vitrine est limitée à {MAX_SHOWCASE_ITEMS} contenus.",
            status_code=422,
        )
    if media_ids:
        found = set(
            (
                await db.execute(
                    select(MediaItem.id).where(
                        MediaItem.id.in_(media_ids),
                        MediaItem.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )
        missing = [media_id for media_id in media_ids if media_id not in found]
        if missing:
            raise AppError(
                "SHOWCASE_MEDIA_NOT_FOUND",
                "Un des contenus sélectionnés n'existe plus dans le catalogue.",
                status_code=404,
                details={"media_ids": missing},
            )
    session.user.showcase_media_ids = media_ids
    await db.commit()
    return {"items": await _showcase_items(db, media_ids)}


@router.get("/games")
async def my_games(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    base = (
        Game.user_id == session.user_id,
        Game.status.in_(["won", "abandoned", "expired"]),
    )
    total = (
        await db.execute(select(func.count()).select_from(Game).where(*base))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Game, MediaItem)
            .outerjoin(MediaItem, MediaItem.id == Game.media_id)
            .where(*base)
            .order_by(Game.finished_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = []
    for game, media in rows:
        snapshot = game.media_snapshot or {}
        media_type = snapshot.get("type")
        if media_type == "episode":
            title = snapshot.get("series_name") or snapshot.get("title")
            subtitle = snapshot.get("episode_title")
            season = snapshot.get("season_number")
            number = snapshot.get("episode_number")
            if season is not None and number is not None:
                subtitle = f"S{int(season):02d}E{int(number):02d} · {subtitle or ''}".strip()
        else:
            title = snapshot.get("title")
            subtitle = None

        poster_url = None
        if media and (media.poster_tag or media.series_id or media.type == "episode"):
            poster_url = f"/api/media/{media.id}/poster"

        items.append(
            {
                "id": game.id,
                "status": game.status,
                "score": game.score or 0,
                "attempts_count": game.attempts_count,
                "duration_seconds": game.duration_seconds,
                "finished_at": _iso(game.finished_at),
                "media_type": media_type,
                "title": title,
                "subtitle": subtitle,
                "year": snapshot.get("year"),
                "poster_url": poster_url,
            }
        )

    return {
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
        "items": items,
    }
