"""Application settings stored in the database."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AppSettings

DEFAULT_GAME_CONFIG: dict[str, Any] = {
    "base_points": 100,
    "wrong_attempt_penalty": 5,
    "max_wrong_penalty": 25,
    "accept_series_name": True,
    "frame_width": 1280,
    "max_attempts": 0,
    "answer_similarity": 92,
    "allow_library_filter": True,
    "exclude_solved_default": True,
    "game_expiry_hours": 24,
    "game_inactivity_minutes": 60,
    "duel_hint_penalty_seconds": 20,
}

DEFAULT_HINT_CONFIG: dict[str, Any] = {
    "order": [
        "release_date",
        "director",
        "actor1",
        "actor2",
        "character",
        "studio",
        "media_type",
        "franchise",
        "episode_title",
    ],
    "items": {
        "release_date": {"enabled": True, "penalty": 10},
        "director": {"enabled": True, "penalty": 15},
        "actor1": {"enabled": True, "penalty": 10},
        "actor2": {"enabled": True, "penalty": 10},
        "character": {"enabled": True, "penalty": 15},
        "studio": {"enabled": True, "penalty": 10},
        "media_type": {"enabled": True, "penalty": 10},
        "franchise": {"enabled": True, "penalty": 15},
        "episode_title": {"enabled": True, "penalty": 15},
    },
}

DEFAULT_DIFFICULTY_CONFIG: dict[str, Any] = {
    "easy": {
        "max_hints": 4,
        "wrong_penalty_multiplier": 0.0,
        "score_multiplier": 0.8,
    },
    "normal": {
        "max_hints": 3,
        "wrong_penalty_multiplier": 1.0,
        "score_multiplier": 1.0,
    },
    "hard": {
        "max_hints": 2,
        "wrong_penalty_multiplier": 1.5,
        "score_multiplier": 1.3,
    },
}


async def get_or_create_settings(db: AsyncSession) -> AppSettings:
    row = (
        await db.execute(select(AppSettings).where(AppSettings.id == 1))
    ).scalar_one_or_none()
    if row:
        changed = _merge_defaults(row)
        if changed:
            await db.commit()
            await db.refresh(row)
        return row

    env = get_settings()
    row = AppSettings(
        id=1,
        emby_url=env.emby_url,
        emby_verify_tls=env.emby_verify_tls,
        sync_enabled=True,
        sync_interval_minutes=env.sync_interval_minutes,
        game_config=dict(DEFAULT_GAME_CONFIG),
        hint_config={
            "order": list(DEFAULT_HINT_CONFIG["order"]),
            "items": {k: dict(v) for k, v in DEFAULT_HINT_CONFIG["items"].items()},
        },
        difficulty_config={
            k: dict(v) for k, v in DEFAULT_DIFFICULTY_CONFIG.items()
        },
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def is_setup_complete(row: AppSettings) -> bool:
    return bool(row.setup_completed_at and row.emby_url and row.emby_api_key_enc)


def _merge_dict(current: dict[str, Any], defaults: dict[str, Any]) -> bool:
    changed = False
    for key, value in defaults.items():
        if key not in current:
            current[key] = value
            changed = True
        elif isinstance(value, dict) and isinstance(current.get(key), dict):
            if _merge_dict(current[key], value):
                changed = True
    return changed


def _merge_defaults(row: AppSettings) -> bool:
    game = dict(row.game_config or {})
    hints = dict(row.hint_config or {})
    difficulty = dict(row.difficulty_config or {})

    changed = False
    if _merge_dict(game, DEFAULT_GAME_CONFIG):
        changed = True
    if _merge_dict(
        hints,
        {
            "order": list(DEFAULT_HINT_CONFIG["order"]),
            "items": {k: dict(v) for k, v in DEFAULT_HINT_CONFIG["items"].items()},
        },
    ):
        changed = True
    order = list(hints.get("order") or [])
    for key in DEFAULT_HINT_CONFIG["order"]:
        if key not in order:
            order.append(key)
            changed = True
    hints["order"] = order
    if _merge_dict(
        difficulty,
        {k: dict(v) for k, v in DEFAULT_DIFFICULTY_CONFIG.items()},
    ):
        changed = True

    if changed:
        row.game_config = game
        row.hint_config = hints
        row.difficulty_config = difficulty
    return changed
