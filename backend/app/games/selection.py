"""Random media selection with real Emby access checks."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.errors import AppError
from app.core.text import normalize
from app.db.models import AppSettings, Game, Genre, Library, MediaGenre, MediaItem, UserSession
from app.emby.client import EmbyAuthError, EmbyClient, EmbyError

logger = logging.getLogger("guesstheframe.selection")

MIN_RUNTIME_TICKS = 120 * 10_000_000  # two minutes


async def _enabled_libraries(db: AsyncSession) -> list[Library]:
    return list(
        (
            await db.execute(
                select(Library).where(Library.is_enabled.is_(True)).order_by(Library.name)
            )
        ).scalars().all()
    )


async def _validate_genres(db: AsyncSession, genres: list[str]) -> list[str]:
    if not genres:
        return []
    rows = (
        await db.execute(
            select(Genre.name).where(
                Genre.name.in_(genres), Genre.is_enabled.is_(True)
            )
        )
    ).scalars().all()
    allowed = set(rows)
    unknown = [genre for genre in genres if genre not in allowed]
    if unknown:
        raise AppError(
            "GENRE_NOT_ALLOWED",
            "Un ou plusieurs genres sélectionnés ne sont pas disponibles.",
            status_code=409,
            details={"genres": unknown},
        )
    return list(allowed)


async def pick_media(
    db: AsyncSession,
    *,
    session: UserSession,
    config: AppSettings,
    media_types: list[str],
    genres: list[str],
    library_ids: list[str] | None,
    exclude_solved: bool,
) -> MediaItem:
    types = [value for value in media_types if value in {"movie", "episode"}]
    if not types:
        raise AppError(
            "NO_MEDIA_TYPE",
            "Sélectionnez au moins un type de média.",
            status_code=422,
        )

    game_config = config.game_config or {}
    allow_library_filter = bool(game_config.get("allow_library_filter", True))

    libraries = await _enabled_libraries(db)
    if not libraries:
        raise AppError(
            "NO_LIBRARY_ENABLED",
            "Aucune bibliothèque Emby n'est activée.",
            status_code=409,
        )

    if library_ids and allow_library_filter:
        allowed_ids = {library.emby_library_id for library in libraries}
        unknown = [value for value in library_ids if value not in allowed_ids]
        if unknown:
            raise AppError(
                "LIBRARY_NOT_ALLOWED",
                "Une ou plusieurs bibliothèques sélectionnées ne sont pas autorisées.",
                status_code=409,
                details={"libraries": unknown},
            )
        selected_library_ids = [
            library.id for library in libraries if library.emby_library_id in library_ids
        ]
    else:
        selected_library_ids = [library.id for library in libraries]

    if not selected_library_ids:
        raise AppError(
            "NO_LIBRARY_SELECTED",
            "Sélectionnez au moins une bibliothèque.",
            status_code=422,
        )

    allowed_genres = await _validate_genres(db, genres)

    conditions: list[Any] = [
        MediaItem.is_active.is_(True),
        MediaItem.type.in_(types),
        MediaItem.library_id.in_(selected_library_ids),
        MediaItem.media_source_id.is_not(None),
        MediaItem.media_source_id != "",
        MediaItem.runtime_ticks >= MIN_RUNTIME_TICKS,
    ]
    if allowed_genres:
        conditions.append(MediaItem.genre_links.any(MediaGenre.genre.in_(allowed_genres)))

    if exclude_solved:
        solved_exists = exists(
            select(Game.id).where(
                Game.user_id == session.user_id,
                Game.status == "won",
                Game.media_id == MediaItem.id,
            )
        )
        conditions.append(~solved_exists)

    count = (
        await db.execute(select(func.count()).select_from(MediaItem).where(*conditions))
    ).scalar_one()
    if count == 0:
        raise AppError(
            "NO_MEDIA_MATCHING_FILTERS",
            "Aucun média ne correspond à ces filtres. Essayez d'élargir les genres, "
            "d'activer un autre type de contenu ou de désactiver l'exclusion des médias déjà devinés.",
            status_code=409,
            details={"candidates": 0, "exclude_solved": exclude_solved},
        )

    candidates = list(
        (
            await db.execute(
                select(MediaItem)
                .where(*conditions)
                .order_by(func.random())
                .limit(12)
            )
        ).scalars().all()
    )

    token = decrypt_secret(session.emby_token_enc)
    if not token:
        raise AppError(
            "EMBY_SESSION_EXPIRED",
            "Votre session Emby a expiré. Reconnectez-vous.",
            status_code=401,
        )

    client = EmbyClient(
        config.emby_url,
        token=token,
        verify_tls=config.emby_verify_tls,
        timeout=15.0,
    )

    for media in candidates:
        try:
            payload = await client.get_items_by_ids(
                [media.emby_item_id], user_id=session.user.emby_user_id
            )
            if payload.get("Items"):
                return media
        except EmbyAuthError as exc:
            raise AppError(
                "EMBY_SESSION_EXPIRED",
                "Votre session Emby a expiré. Reconnectez-vous.",
                status_code=401,
            ) from exc
        except EmbyError as exc:
            logger.warning("Emby access check failed for %s: %s", media.emby_item_id, exc)
            raise AppError(
                "EMBY_UNAVAILABLE",
                "Le serveur Emby n'a pas pu vérifier l'accès au média.",
                status_code=502,
            ) from exc

    raise AppError(
        "NO_ACCESSIBLE_MEDIA",
        "Aucun média accessible n'a été trouvé pour votre compte Emby avec ces filtres.",
        status_code=409,
    )


async def pick_duel_media(
    db: AsyncSession,
    *,
    categories: list[str],
    genres: list[str],
    library_ids: list[str] | None,
    count: int = 10,
) -> list[MediaItem]:
    """Select distinct media for a 1v1 match (no per-user access check)."""
    selected_categories = [
        value for value in categories if value in {"movie", "series", "anime"}
    ]
    if not selected_categories:
        raise AppError(
            "NO_MEDIA_TYPE",
            "Sélectionnez au moins une catégorie de contenu.",
            status_code=422,
        )

    libraries = await _enabled_libraries(db)
    if not libraries:
        raise AppError(
            "NO_LIBRARY_ENABLED",
            "Aucune bibliothèque Emby n'est activée.",
            status_code=409,
        )
    if library_ids:
        allowed_ids = {library.emby_library_id for library in libraries}
        unknown = [value for value in library_ids if value not in allowed_ids]
        if unknown:
            raise AppError(
                "LIBRARY_NOT_ALLOWED",
                "Une ou plusieurs bibliothèques sélectionnées ne sont pas autorisées.",
                status_code=409,
                details={"libraries": unknown},
            )
        selected_library_ids = [
            library.id for library in libraries if library.emby_library_id in library_ids
        ]
    else:
        selected_library_ids = [library.id for library in libraries]

    # Emby libraries explicitly named "Anime(s)" are considered anime libraries.
    # The "Anime" genre is used as a fallback for episodes living elsewhere.
    anime_library_ids = [
        library.id
        for library in libraries
        if library.collection_type == "tvshows"
        and "anime" in normalize(library.name or "")
    ]

    allowed_genres = await _validate_genres(db, genres)
    conditions: list[Any] = [
        MediaItem.is_active.is_(True),
        MediaItem.library_id.in_(selected_library_ids),
        MediaItem.media_source_id.is_not(None),
        MediaItem.media_source_id != "",
        MediaItem.runtime_ticks >= MIN_RUNTIME_TICKS,
    ]

    include_movies = "movie" in selected_categories
    include_series = "series" in selected_categories
    include_anime = "anime" in selected_categories

    category_conditions: list[Any] = []
    if include_movies:
        category_conditions.append(MediaItem.type == "movie")

    anime_episode_conditions = [
        MediaItem.genre_links.any(MediaGenre.genre == "Anime")
    ]
    if anime_library_ids:
        anime_episode_conditions.insert(
            0, MediaItem.library_id.in_(anime_library_ids)
        )
    anime_condition = or_(*anime_episode_conditions)

    if include_series and include_anime:
        category_conditions.append(MediaItem.type == "episode")
    else:
        if include_series:
            category_conditions.append(
                and_(MediaItem.type == "episode", not_(anime_condition))
            )
        if include_anime:
            category_conditions.append(
                and_(MediaItem.type == "episode", anime_condition)
            )

    if not category_conditions:
        raise AppError(
            "NO_MEDIA_TYPE",
            "Sélectionnez au moins une catégorie de contenu.",
            status_code=422,
        )
    conditions.append(or_(*category_conditions))

    if allowed_genres:
        conditions.append(MediaItem.genre_links.any(MediaGenre.genre.in_(allowed_genres)))

    candidates = list(
        (
            await db.execute(
                select(MediaItem)
                .where(*conditions)
                .order_by(func.random())
                .limit(max(count * 8, 40))
            )
        ).scalars().all()
    )

    selected: list[MediaItem] = []
    seen: set[tuple[str, str]] = set()
    for media in candidates:
        if media.type == "episode":
            key = ("episode", normalize(media.series_name or media.title))
        else:
            key = ("movie", normalize(media.title))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        selected.append(media)
        if len(selected) >= count:
            break

    if len(selected) < count:
        raise AppError(
            "NOT_ENOUGH_DUEL_MEDIA",
            f"Il faut au moins {count} contenus distincts pour lancer un duel. "
            "Élargissez les genres, les catégories ou les bibliothèques.",
            status_code=409,
            details={"found": len(selected), "required": count},
        )
    return selected
