"""Game lifecycle: creation, attempts, hints, abandonment and result."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.errors import AppError
from app.db.base import utcnow
from app.db.models import (
    AppSettings,
    Attempt,
    DailyChallenge,
    Game,
    Hint,
    Library,
    MediaItem,
    UserSession,
)
from app.emby.client import EmbyAuthError, EmbyClient, EmbyError
from app.games.answers import accepted_answers, match_answer, normalize
from app.games.hints import build_hint, hint_options
from app.games.scoring import (
    compute_potential_score,
    difficulty_settings,
    final_score,
)
from app.games.selection import MIN_RUNTIME_TICKS, pick_media

logger = logging.getLogger("guesstheframe.games")

FRAME_COUNTS = {
    "classic": 1,
    "frames3": 3,
    "frames5": 5,
    "dezoom": 1,
    "daily": 1,
}

MODE_LABELS = {
    "classic": "Classique",
    "frames3": "3 frames",
    "frames5": "5 frames",
    "dezoom": "Dézoom",
    "daily": "Journalier",
}


def frame_count_for(mode: str) -> int:
    return FRAME_COUNTS.get(mode or "classic", 1)


def daily_date_str() -> str:
    try:
        tz = ZoneInfo("Europe/Paris")
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).date().isoformat()


def dezoom_level(attempts_count: int) -> float:
    # Starts at 2.8x, then opens up after each wrong attempt.
    return round(max(1.0, 2.8 - 0.35 * max(0, attempts_count)), 2)


def inactivity_minutes(config: AppSettings) -> int:
    return max(
        5,
        int((config.game_config or {}).get("game_inactivity_minutes", 60)),
    )


def ranking_category_for(
    *,
    media_types: list[str] | None,
    genres: list[str] | None,
    library_ids: list[str] | None,
    mode: str,
) -> str | None:
    """Only unfiltered games count in the public leaderboards.

    Daily challenges and games with genre/library restrictions are personal
    and excluded. Difficulty, frame mode and exclusion of already-solved media
    do not change the ranking category.
    """
    if mode == "daily":
        return None
    if genres:
        return None
    if library_ids:
        return None
    types = set(media_types or [])
    if types == {"movie", "episode"}:
        return "general"
    if types == {"movie"}:
        return "movies"
    if types == {"episode"}:
        return "series"
    return None


def _activity_at(game: Game) -> datetime:
    return game.last_activity_at or game.started_at


async def expire_user_inactive_games(
    db: AsyncSession, *, user_id: int, config: AppSettings
) -> int:
    cutoff = utcnow() - timedelta(minutes=inactivity_minutes(config))
    result = await db.execute(
        update(Game)
        .where(
            Game.user_id == user_id,
            Game.status == "in_progress",
            func.coalesce(Game.last_activity_at, Game.started_at) < cutoff,
        )
        .values(
            status="abandoned",
            score=0,
            finished_at=utcnow(),
            score_breakdown={"won": False, "reason": "inactivity"},
        )
    )
    await db.commit()
    return int(result.rowcount or 0)


async def ensure_no_active_game(
    db: AsyncSession, *, user_id: int, config: AppSettings
) -> None:
    await expire_user_inactive_games(db, user_id=user_id, config=config)
    active = (
        await db.execute(
            select(Game)
            .where(Game.user_id == user_id, Game.status == "in_progress")
            .order_by(Game.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is None:
        return
    expires = _activity_at(active) + timedelta(minutes=inactivity_minutes(config))
    raise AppError(
        "ACTIVE_GAME_EXISTS",
        "Vous avez déjà une partie en cours. Reprenez-la ou abandonnez-la avant d'en lancer une nouvelle.",
        status_code=409,
        details={
            "game_id": active.id,
            "mode": active.mode,
            "started_at": _iso(active.started_at),
            "expires_at": _iso(expires),
        },
    )


def config_dict(config: AppSettings) -> dict[str, Any]:
    return {
        "game_config": config.game_config or {},
        "hint_config": config.hint_config or {},
        "difficulty_config": config.difficulty_config or {},
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def snapshot_media(media: MediaItem) -> dict[str, Any]:
    return {
        "type": media.type,
        "title": media.title,
        "original_title": media.original_title,
        "sort_title": media.sort_title,
        "year": media.year,
        "overview": media.overview,
        "runtime_ticks": media.runtime_ticks,
        "genres": list(media.genres or []),
        "people": list(media.people or []),
        "studios": list(media.studios or []),
        "collections": list(media.collections or []),
        "tags": list(media.tags or []),
        "chapters": list(media.chapters or []),
        "series_id": media.series_id,
        "series_name": media.series_name,
        "series_original_title": media.series_original_title,
        "season_number": media.season_number,
        "episode_number": media.episode_number,
        "episode_title": media.episode_title,
        "premiere_date": media.premiere_date.isoformat() if media.premiere_date else None,
        "poster_tag": media.poster_tag,
        "emby_item_id": media.emby_item_id,
        "media_source_id": media.media_source_id,
        "container": media.container,
        "video_range": media.video_range,
        "width": media.width,
        "height": media.height,
    }


def public_state(game: Game, config: AppSettings) -> dict[str, Any]:
    cfg = config_dict(config)
    hints_used = list(game.hints_used or [])
    max_hints = int(
        difficulty_settings(cfg, game.difficulty).get("max_hints", 0)
    )
    potential = compute_potential_score(
        config=cfg,
        difficulty=game.difficulty,
        attempts_count=game.attempts_count,
        hints_used=hints_used,
    )
    mode = game.mode or "classic"
    count = frame_count_for(mode)
    frame_keys = list(game.frame_keys or [])
    if not frame_keys and game.frame_cache_key:
        frame_keys = [game.frame_cache_key]
    used_keys = {str(hint.get("key")) for hint in hints_used}
    revealed_media_type = next(
        (
            str(hint.get("value"))
            for hint in hints_used
            if hint.get("key") == "media_type"
        ),
        None,
    )
    media_types = (game.filters or {}).get("media_types")
    options = hint_options(
        snapshot=game.media_snapshot or {},
        hint_config=config.hint_config or {},
        used_keys=used_keys,
        media_types=media_types,
        revealed_media_type=revealed_media_type,
    )
    activity = _activity_at(game)
    expires = activity + timedelta(minutes=inactivity_minutes(config))
    return {
        "id": game.id,
        "status": game.status,
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "ranking_category": game.ranking_category,
        "difficulty": game.difficulty,
        "attempts_count": game.attempts_count,
        "hints_used": hints_used,
        "hint_options": options,
        "score_potential": potential,
        "score": game.score,
        "max_hints": max_hints,
        "zoom_level": dezoom_level(game.attempts_count) if mode == "dezoom" else 1.0,
        "frame_count": count,
        "frame_urls": [
            f"/api/games/{game.id}/frame?index={index}" for index in range(count)
        ],
        "started_at": _iso(game.started_at),
        "last_activity_at": _iso(activity),
        "expires_at": _iso(expires),
        "inactivity_minutes": inactivity_minutes(config),
        "finished_at": _iso(game.finished_at),
        "frame_url": f"/api/games/{game.id}/frame?index=0",
        "has_frame": bool(frame_keys),
        "filters": game.filters,
        "daily_date": game.daily_date,
    }


async def build_franchise_hint(
    snapshot: dict[str, Any], config: AppSettings
) -> dict[str, Any] | None:
    """Build the saga/series-count hint without ever naming the saga or series."""
    items = (config.hint_config or {}).get("items") or {}
    hint_cfg = items.get("franchise")
    if not hint_cfg or not hint_cfg.get("enabled", True):
        return None
    api_key = decrypt_secret(config.emby_api_key_enc)
    if not api_key:
        return None
    client = EmbyClient(
        config.emby_url, token=api_key, verify_tls=config.emby_verify_tls
    )
    penalty = int(hint_cfg.get("penalty", 0))

    if snapshot.get("type") == "episode":
        series_id = snapshot.get("series_id")
        if not series_id:
            return None
        count: int | None = None
        try:
            seasons = await client.get_seasons(str(series_id))
            # Ignore "Specials" (index 0 / None) when counting real seasons.
            numbered = [
                season
                for season in seasons
                if isinstance(season.get("IndexNumber"), int)
                and int(season["IndexNumber"]) > 0
            ]
            count = len(numbered) or len(seasons) or None
        except EmbyError:
            count = None
        if count:
            value = f"{int(count)} saison" + ("s" if int(count) > 1 else "")
        else:
            value = "Nombre de saisons indisponible"
        return {
            "key": "franchise",
            "label": "Nombre de saisons",
            "value": value,
            "penalty": penalty,
        }

    collections = snapshot.get("collections") or []
    collection = next(
        (
            entry
            for entry in collections
            if isinstance(entry, dict) and entry.get("id")
        ),
        None,
    )
    if not collection:
        return None
    count = None
    try:
        payload = await client.get_items(
            parent_id=str(collection["id"]),
            include_item_types="Movie",
            limit=1,
            fields="Id,Name",
        )
        count = int(payload.get("TotalRecordCount") or 0) or None
    except EmbyError:
        count = None
    if count:
        value = f"Oui — {int(count)} film" + ("s" if int(count) > 1 else "")
    else:
        value = "Oui — nombre de films indisponible"
    return {
        "key": "franchise",
        "label": "Saga",
        "value": value,
        "penalty": penalty,
    }


async def _check_user_access(
    session: UserSession, config: AppSettings, media: MediaItem
) -> None:
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
    try:
        payload = await client.get_items_by_ids(
            [media.emby_item_id], user_id=session.user.emby_user_id
        )
    except EmbyAuthError as exc:
        raise AppError(
            "EMBY_SESSION_EXPIRED",
            "Votre session Emby a expiré. Reconnectez-vous.",
            status_code=401,
        ) from exc
    except EmbyError as exc:
        raise AppError(
            "EMBY_UNAVAILABLE",
            "Le serveur Emby n'a pas pu vérifier l'accès au média.",
            status_code=502,
        ) from exc
    if not payload.get("Items"):
        raise AppError(
            "MEDIA_ACCESS_DENIED",
            "Ce média n'est pas accessible avec votre compte Emby.",
            status_code=403,
        )


async def _daily_challenge_media(
    db: AsyncSession, config: AppSettings
) -> tuple[MediaItem, str]:
    date = daily_date_str()
    challenge = (
        await db.execute(
            select(DailyChallenge).where(DailyChallenge.challenge_date == date)
        )
    ).scalar_one_or_none()
    if challenge:
        media = await db.get(MediaItem, challenge.media_id)
        if media is None or not media.is_active:
            raise AppError(
                "DAILY_MEDIA_UNAVAILABLE",
                "Le média du jour n'est plus disponible sur Emby.",
                status_code=503,
            )
        return media, date

    enabled_libraries = select(Library.id).where(Library.is_enabled.is_(True))
    ids = list(
        (
            await db.execute(
                select(MediaItem.id)
                .where(
                    MediaItem.is_active.is_(True),
                    MediaItem.type == "movie",
                    MediaItem.library_id.in_(enabled_libraries),
                    MediaItem.media_source_id.is_not(None),
                    MediaItem.media_source_id != "",
                    MediaItem.runtime_ticks >= MIN_RUNTIME_TICKS,
                )
                .order_by(MediaItem.id)
            )
        ).scalars().all()
    )
    if not ids:
        raise AppError(
            "DAILY_NO_MEDIA",
            "Aucun film disponible pour le défi journalier.",
            status_code=409,
        )

    rng = random.Random(f"{date}:{config.emby_server_id or 'gtf'}")
    selected_id = rng.choice(ids)
    challenge = DailyChallenge(
        challenge_date=date,
        media_id=selected_id,
        created_at=utcnow(),
    )
    db.add(challenge)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        challenge = (
            await db.execute(
                select(DailyChallenge).where(DailyChallenge.challenge_date == date)
            )
        ).scalar_one()
        selected_id = challenge.media_id

    media = await db.get(MediaItem, selected_id)
    if media is None:
        raise AppError(
            "DAILY_MEDIA_UNAVAILABLE",
            "Le média du jour est introuvable.",
            status_code=503,
        )
    return media, date


async def create_daily_game(
    db: AsyncSession,
    *,
    session: UserSession,
    config: AppSettings,
) -> Game:
    date = daily_date_str()
    existing = (
        await db.execute(
            select(Game).where(
                Game.user_id == session.user_id, Game.daily_date == date
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    await ensure_no_active_game(db, user_id=session.user_id, config=config)
    media, date = await _daily_challenge_media(db, config)
    await _check_user_access(session, config, media)

    game = Game(
        user_id=session.user_id,
        media_id=media.id,
        status="in_progress",
        mode="daily",
        daily_date=date,
        filters={
            "media_types": ["movie"],
            "genres": [],
            "library_ids": None,
            "exclude_solved": False,
            "mode": "daily",
            "date": date,
        },
        difficulty="normal",
        attempts_count=0,
        hints_used=[],
        frame_keys=[],
        media_snapshot=snapshot_media(media),
        started_at=utcnow(),
        last_activity_at=utcnow(),
    )
    db.add(game)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(Game).where(
                    Game.user_id == session.user_id, Game.daily_date == date
                )
            )
        ).scalar_one()
        return existing
    await db.refresh(game)
    logger.info("Daily game %s created for %s", game.id, session.user.username)
    return game


async def create_game(
    db: AsyncSession,
    *,
    session: UserSession,
    config: AppSettings,
    media_types: list[str],
    genres: list[str],
    library_ids: list[str] | None,
    difficulty: str,
    exclude_solved: bool | None,
    mode: str = "classic",
) -> Game:
    if mode == "daily":
        return await create_daily_game(db, session=session, config=config)
    if mode not in FRAME_COUNTS:
        raise AppError("INVALID_MODE", "Mode de jeu inconnu.", status_code=422)

    await ensure_no_active_game(db, user_id=session.user_id, config=config)

    game_config = config.game_config or {}
    if exclude_solved is None:
        exclude_solved = bool(game_config.get("exclude_solved_default", True))
    if difficulty not in {"easy", "normal", "hard"}:
        raise AppError(
            "INVALID_DIFFICULTY",
            "Difficulté inconnue.",
            status_code=422,
        )

    media = await pick_media(
        db,
        session=session,
        config=config,
        media_types=media_types,
        genres=genres,
        library_ids=library_ids,
        exclude_solved=exclude_solved,
    )

    filters = {
        "media_types": media_types,
        "genres": genres,
        "library_ids": library_ids,
        "exclude_solved": exclude_solved,
        "mode": mode,
    }
    game = Game(
        user_id=session.user_id,
        media_id=media.id,
        status="in_progress",
        mode=mode,
        ranking_category=ranking_category_for(
            media_types=media_types,
            genres=genres,
            library_ids=library_ids,
            mode=mode,
        ),
        filters=filters,
        difficulty=difficulty,
        attempts_count=0,
        hints_used=[],
        frame_keys=[],
        media_snapshot=snapshot_media(media),
        started_at=utcnow(),
        last_activity_at=utcnow(),
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)
    logger.info(
        "Game %s created for user %s (mode %s, media %s, difficulty %s)",
        game.id,
        session.user.username,
        mode,
        media.emby_item_id,
        difficulty,
    )
    return game


async def get_owned_game(
    db: AsyncSession, game_id: str, user_id: int, *, lock: bool = False
) -> Game:
    statement = select(Game).where(Game.id == game_id, Game.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    game = (await db.execute(statement)).scalar_one_or_none()
    if game is None:
        raise AppError("GAME_NOT_FOUND", "Partie introuvable.", status_code=404)
    return game


async def backfill_ranking_categories() -> int:
    """Assign a leaderboard category to games created before the column existed."""
    from app.db.session import AsyncSessionLocal

    updated = 0
    async with AsyncSessionLocal() as db:
        games = (
            await db.execute(
                select(Game).where(
                    Game.ranking_category.is_(None),
                    Game.mode != "daily",
                )
            )
        ).scalars().all()
        for game in games:
            filters = game.filters or {}
            category = ranking_category_for(
                media_types=filters.get("media_types"),
                genres=filters.get("genres"),
                library_ids=filters.get("library_ids"),
                mode=game.mode or "classic",
            )
            if category is not None:
                game.ranking_category = category
                updated += 1
        await db.commit()
    return updated


async def touch_game(db: AsyncSession, game: Game) -> None:
    if game.status == "in_progress":
        game.last_activity_at = utcnow()
        await db.commit()


async def _finalize(
    db: AsyncSession,
    game: Game,
    config: AppSettings,
    *,
    won: bool,
) -> None:
    if game.status != "in_progress":
        return
    now = utcnow()
    helped = list(game.hints_used or [])
    cfg = config_dict(config)
    score, breakdown = final_score(
        config=cfg,
        difficulty=game.difficulty,
        attempts_count=game.attempts_count,
        hints_used=helped,
        won=won,
    )
    game.status = "won" if won else "abandoned"
    game.finished_at = now
    game.duration_seconds = max(0, int((now - game.started_at).total_seconds()))
    game.score = score
    game.score_breakdown = breakdown


async def submit_attempt(
    db: AsyncSession,
    *,
    game_id: str,
    user_id: int,
    guess: str,
    config: AppSettings,
) -> dict[str, Any]:
    game = await get_owned_game(db, game_id, user_id, lock=True)
    if game.status != "in_progress":
        raise AppError(
            "GAME_ALREADY_FINISHED",
            "Cette partie est déjà terminée.",
            status_code=409,
            details={"result": await build_result(db, game, config)},
        )

    game.last_activity_at = utcnow()
    max_attempts = int((config.game_config or {}).get("max_attempts", 0))
    if max_attempts and game.attempts_count >= max_attempts:
        raise AppError(
            "GAME_ATTEMPTS_EXHAUSTED",
            "Nombre maximum de tentatives atteint pour cette partie.",
            status_code=409,
        )

    normalized = normalize(guess)
    if not normalized:
        raise AppError(
            "EMPTY_ANSWER",
            "Saisissez une réponse.",
            status_code=422,
        )
    if len(guess) > 500:
        raise AppError("ANSWER_TOO_LONG", "Réponse trop longue.", status_code=422)

    game_config = config.game_config or {}
    accepted = accepted_answers(game.media_snapshot or {}, game_config)
    threshold = int(game_config.get("answer_similarity", 92))
    correct, matched = match_answer(guess, accepted, threshold=threshold)

    game.attempts_count += 1
    db.add(
        Attempt(
            game_id=game.id,
            guess=guess.strip(),
            guess_norm=normalized,
            is_correct=correct,
        )
    )

    if correct:
        await _finalize(db, game, config, won=True)
        await db.commit()
        return {
            "correct": True,
            "matched": matched,
            "attempts_count": game.attempts_count,
            "state": public_state(game, config),
            "result": await build_result(db, game, config),
        }

    await db.commit()
    return {
        "correct": False,
        "attempts_count": game.attempts_count,
        "state": public_state(game, config),
    }


async def reveal_hint(
    db: AsyncSession,
    *,
    game_id: str,
    user_id: int,
    config: AppSettings,
    hint_key: str | None = None,
) -> dict[str, Any]:
    game = await get_owned_game(db, game_id, user_id, lock=True)
    if game.status != "in_progress":
        raise AppError(
            "GAME_ALREADY_FINISHED",
            "Cette partie est déjà terminée.",
            status_code=409,
            details={"result": await build_result(db, game, config)},
        )

    game.last_activity_at = utcnow()
    cfg = config_dict(config)
    game_config = config.game_config or {}
    accepted = accepted_answers(game.media_snapshot or {}, game_config)
    used = list(game.hints_used or [])
    used_keys = {str(hint.get("key")) for hint in used}
    max_hints = int(difficulty_settings(cfg, game.difficulty).get("max_hints", 0))
    if max_hints <= 0 or len(used_keys) >= max_hints:
        raise AppError(
            "HINTS_EXHAUSTED",
            f"Limite de {max_hints} indice(s) atteinte pour cette difficulté.",
            status_code=409,
        )

    revealed_media_type = next(
        (
            str(hint.get("value"))
            for hint in used
            if hint.get("key") == "media_type"
        ),
        None,
    )
    options = hint_options(
        snapshot=game.media_snapshot or {},
        hint_config=config.hint_config or {},
        used_keys=used_keys,
        media_types=(game.filters or {}).get("media_types"),
        revealed_media_type=revealed_media_type,
    )
    allowed_keys = [option["key"] for option in options if not option["used"]]

    if hint_key:
        if hint_key in used_keys:
            raise AppError(
                "HINT_ALREADY_USED",
                "Cet indice a déjà été révélé.",
                status_code=409,
            )
        if hint_key not in allowed_keys:
            raise AppError(
                "HINT_UNAVAILABLE",
                "Cet indice n'est pas disponible pour ce média.",
                status_code=409,
            )
    else:
        hint_key = next(
            (key for key in allowed_keys if key != "franchise"), None
        )
        if hint_key is None and "franchise" in allowed_keys:
            hint_key = "franchise"
        if hint_key is None:
            raise AppError(
                "HINTS_EXHAUSTED",
                "Aucun indice supplémentaire n'est disponible pour ce média.",
                status_code=409,
            )

    if hint_key == "franchise":
        hint = await build_franchise_hint(
            game.media_snapshot or {}, config
        )
    else:
        hint = build_hint(
            snapshot=game.media_snapshot or {},
            hint_key=hint_key,
            hint_config=config.hint_config or {},
            accepted_answers=accepted,
        )
    if hint is None:
        raise AppError(
            "HINT_UNAVAILABLE",
            "Cet indice n'est pas disponible dans les métadonnées de ce média.",
            status_code=409,
        )

    updated = list(used)
    updated.append(hint)
    game.hints_used = updated
    db.add(
        Hint(
            game_id=game.id,
            hint_key=str(hint["key"]),
            payload=hint,
            penalty=int(hint.get("penalty") or 0),
        )
    )
    await db.commit()
    state = public_state(game, config)
    state["hint"] = hint
    return state


async def abandon_game(
    db: AsyncSession,
    *,
    game_id: str,
    user_id: int,
    config: AppSettings,
) -> dict[str, Any]:
    game = await get_owned_game(db, game_id, user_id, lock=True)
    if game.status == "in_progress":
        await _finalize(db, game, config, won=False)
        await db.commit()
    return await build_result(db, game, config)


async def build_result(
    db: AsyncSession, game: Game, config: AppSettings
) -> dict[str, Any]:
    snapshot = dict(game.media_snapshot or {})
    media = await db.get(MediaItem, game.media_id)
    media_type = str(snapshot.get("type") or "movie")
    people = list(snapshot.get("people") or [])
    directors = [
        str(person.get("name"))
        for person in people
        if person.get("type") == "Director" and person.get("name")
    ]
    actors: list[str] = []
    seen_actors: set[str] = set()
    for person in people:
        if person.get("type") != "Actor" or not person.get("name"):
            continue
        name = str(person["name"])
        key = normalize(name)
        if key and key not in seen_actors:
            seen_actors.add(key)
            actors.append(name)
    actors = actors[:5]

    if media_type == "episode":
        answer_label = snapshot.get("series_name") or snapshot.get("title") or ""
        season = snapshot.get("season_number")
        number = snapshot.get("episode_number")
        suffix = ""
        if season is not None and number is not None:
            suffix = f" S{int(season):02d}E{int(number):02d}"
        display_title = f"{answer_label}{suffix}".strip()
    else:
        answer_label = str(snapshot.get("title") or "")
        display_title = answer_label

    emby_url: str | None = None
    if media and media.is_active and config.emby_server_id and snapshot.get("emby_item_id"):
        client = EmbyClient(
            config.emby_url, verify_tls=config.emby_verify_tls
        )
        emby_url = client.web_item_url(
            str(snapshot["emby_item_id"]), config.emby_server_id
        )

    poster_url: str | None = None
    if media and (media.poster_tag or media.series_id or media.type == "episode"):
        poster_url = f"/api/media/{media.id}/poster"

    runtime_ticks = int(snapshot.get("runtime_ticks") or 0)
    runtime_minutes = round(runtime_ticks / 600_000_000) if runtime_ticks else None

    return {
        "game_id": game.id,
        "status": game.status,
        "won": game.status == "won",
        "score": game.score or 0,
        "attempts_count": game.attempts_count,
        "duration_seconds": game.duration_seconds,
        "hints_used": list(game.hints_used or []),
        "score_breakdown": game.score_breakdown or {},
        "finished_at": _iso(game.finished_at),
        "emby_server_name": config.emby_server_name,
        "media": {
            "type": media_type,
            "title": snapshot.get("title"),
            "original_title": snapshot.get("original_title"),
            "answer_label": answer_label,
            "display_title": display_title,
            "year": snapshot.get("year"),
            "overview": snapshot.get("overview"),
            "genres": list(snapshot.get("genres") or []),
            "directors": directors,
            "actors": actors,
            "runtime_minutes": runtime_minutes,
            "poster_url": poster_url,
            "emby_url": emby_url,
            "series_name": snapshot.get("series_name"),
            "series_original_title": snapshot.get("series_original_title"),
            "season_number": snapshot.get("season_number"),
            "episode_number": snapshot.get("episode_number"),
            "episode_title": snapshot.get("episode_title"),
        },
    }
