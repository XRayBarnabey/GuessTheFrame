"""Read-only catalogue endpoints used by the game client."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_session
from app.core.text import normalize
from app.db.models import (
    Game,
    Genre,
    Library,
    MediaGenre,
    MediaItem,
    UserSession,
)
from app.db.session import get_db

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


@router.get("/summary")
async def summary(    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    active = MediaItem.is_active.is_(True)
    total = (
        await db.execute(
            select(func.count()).select_from(MediaItem).where(active)
        )
    ).scalar_one()
    movies = (
        await db.execute(
            select(func.count())
            .select_from(MediaItem)
            .where(active, MediaItem.type == "movie")
        )
    ).scalar_one()
    episodes = (
        await db.execute(
            select(func.count())
            .select_from(MediaItem)
            .where(active, MediaItem.type == "episode")
        )
    ).scalar_one()

    libraries = (
        await db.execute(
            select(Library)
            .where(Library.is_enabled.is_(True))
            .order_by(Library.name)
        )
    ).scalars().all()

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

    user_id = session.user_id
    games = (
        await db.execute(
            select(func.count()).select_from(Game).where(Game.user_id == user_id)
        )
    ).scalar_one()
    won = (
        await db.execute(
            select(func.count())
            .select_from(Game)
            .where(Game.user_id == user_id, Game.status == "won")
        )
    ).scalar_one()
    score = (
        await db.execute(
            select(func.coalesce(func.sum(Game.score), 0)).where(
                Game.user_id == user_id, Game.status == "won"
            )
        )
    ).scalar_one()

    return {
        "media": {"total": total, "movies": movies, "episodes": episodes},
        "libraries": [
            {
                "id": library.emby_library_id,
                "name": library.name,
                "collection_type": library.collection_type,
            }
            for library in libraries
        ],
        "genres": [
            {"name": name, "media_count": count} for name, count in genre_rows
        ],
        "user_stats": {"games": games, "won": won, "score": int(score or 0)},
    }


@router.get("/titles")
async def search_titles(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
    _: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return title suggestions for autocomplete, never media IDs or answers."""
    needle = normalize(q)
    if len(needle) < 2:
        return {"items": []}

    rows = (
        await db.execute(
            select(
                MediaItem.title,
                MediaItem.type,
                MediaItem.series_name,
                MediaItem.year,
            )
            .where(
                MediaItem.is_active.is_(True),
                MediaItem.search_text.contains(needle),
            )
            .limit(120)
        )
    ).all()

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for title, media_type, series_name, year in rows:
        display = series_name if media_type == "episode" and series_name else title
        if not display:
            continue
        key = (str(media_type), normalize(display))
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "title": str(display),
                "type": str(media_type),
                "year": year,
            }
        )

    items.sort(
        key=lambda item: (
            0 if normalize(item["title"]).startswith(needle) else 1,
            normalize(item["title"]),
        )
    )
    return {"items": items[:limit]}
