"""Progressive and selectable hints built from real Emby metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.text import normalize

HINT_LABELS = {
    "release_date": "Date de sortie",
    "director": "Réalisateur",
    "actor1": "Acteur principal",
    "actor2": "Second acteur",
    "character": "Personnage principal",
    "studio": "Studio",
    "media_type": "Type de contenu",
    "franchise": "Saga / nombre de films ou saisons",
    "episode_title": "Nom de l'épisode",
}


def _directors(snapshot: dict[str, Any]) -> list[str]:
    people = snapshot.get("people") or []
    return [
        str(person.get("name"))
        for person in people
        if person.get("type") == "Director" and person.get("name")
    ]


def _actors(snapshot: dict[str, Any]) -> list[str]:
    people = snapshot.get("people") or []
    seen: set[str] = set()
    actors: list[str] = []
    for person in people:
        if person.get("type") != "Actor" or not person.get("name"):
            continue
        name = str(person["name"])
        key = normalize(name)
        if key and key not in seen:
            seen.add(key)
            actors.append(name)
    return actors


def _character(snapshot: dict[str, Any]) -> str | None:
    people = snapshot.get("people") or []
    for person in people:
        if person.get("type") != "Actor":
            continue
        role = person.get("role")
        if role and normalize(str(role)):
            return str(role)
    return None


def _release_date(snapshot: dict[str, Any]) -> str | None:
    year = snapshot.get("year")
    if year:
        return str(year)
    premiere = snapshot.get("premiere_date")
    if not premiere:
        return None
    try:
        parsed = datetime.fromisoformat(str(premiere).replace("Z", "+00:00"))
        return str(parsed.year)
    except ValueError:
        return None


def _franchise_available(snapshot: dict[str, Any]) -> bool:
    if snapshot.get("type") == "episode":
        return bool(snapshot.get("series_id"))
    collections = snapshot.get("collections") or []
    return any(
        isinstance(collection, dict) and collection.get("id")
        for collection in collections
    )


def _value(snapshot: dict[str, Any], key: str) -> str | None:
    if key == "release_date":
        return _release_date(snapshot)
    if key == "director":
        directors = _directors(snapshot)
        return directors[0] if directors else None
    if key == "actor1":
        actors = _actors(snapshot)
        return actors[0] if actors else None
    if key == "actor2":
        actors = _actors(snapshot)
        return actors[1] if len(actors) > 1 else None
    if key == "character":
        return _character(snapshot)
    if key == "studio":
        studios = snapshot.get("studios") or []
        return str(studios[0]) if studios else None
    if key == "media_type":
        media_type = snapshot.get("type")
        if media_type == "movie":
            return "Film"
        if media_type == "episode":
            return "Série"
        return None
    if key == "franchise":
        # Resolved asynchronously by the game service: the collection/series
        # name must never be revealed, only the number of films or seasons.
        return None
    if key == "episode_title":
        if snapshot.get("type") != "episode":
            return None
        return snapshot.get("episode_title") or snapshot.get("title")
    return None


def build_hint(
    *,
    snapshot: dict[str, Any],
    hint_key: str,
    hint_config: dict[str, Any],
    accepted_answers: set[str],
) -> dict[str, Any] | None:
    if hint_key == "franchise":
        return None
    items = hint_config.get("items") or {}
    config = items.get(hint_key)
    if not config or not config.get("enabled", True):
        return None
    value = _value(snapshot, hint_key)
    if not value:
        return None
    # A hint must never be the answer or one of its accepted variants.
    if normalize(value) in accepted_answers:
        return None
    return {
        "key": hint_key,
        "label": HINT_LABELS.get(hint_key, hint_key),
        "value": value,
        "penalty": int(config.get("penalty", 0)),
    }


def next_hint(
    *,
    snapshot: dict[str, Any],
    hint_config: dict[str, Any],
    used_keys: set[str],
    max_hints: int,
    accepted_answers: set[str],
) -> tuple[dict[str, Any] | None, str]:
    if max_hints <= 0:
        return None, "limit"
    if len(used_keys) >= max_hints:
        return None, "limit"

    order = hint_config.get("order") or list(HINT_LABELS)
    for key in order:
        if key in used_keys or key == "franchise":
            continue
        hint = build_hint(
            snapshot=snapshot,
            hint_key=key,
            hint_config=hint_config,
            accepted_answers=accepted_answers,
        )
        if hint:
            return hint, "ok"
    return None, "exhausted"


def hint_options(
    *,
    snapshot: dict[str, Any],
    hint_config: dict[str, Any],
    used_keys: set[str],
    media_types: list[str] | None,
    revealed_media_type: str | None = None,
) -> list[dict[str, Any]]:
    """Hint choices exposed to the client.

    Availability is deliberately not exposed: it could reveal whether the
    current media is a movie or an episode for free. The backend answers
    HINT_UNAVAILABLE (without charging) if the metadata is missing.
    """
    items = hint_config.get("items") or {}
    order = hint_config.get("order") or list(HINT_LABELS)
    both_types = set(media_types or []) == {"movie", "episode"}
    snap_type = snapshot.get("type")

    options: list[dict[str, Any]] = []
    for key in order:
        config = items.get(key)
        if not config or not config.get("enabled", True):
            continue
        if key == "media_type" and not both_types:
            continue
        if key == "episode_title":
            if snap_type != "episode":
                continue
            if both_types and revealed_media_type != "Série":
                # Hide it until the type hint (or an episode-only filter) tells
                # the player they are dealing with a series.
                continue
        if key == "franchise":
            if not _franchise_available(snapshot):
                continue
            label = "Nombre de saisons" if snap_type == "episode" else "Saga"
        else:
            label = HINT_LABELS.get(key, key)
            if key not in used_keys and _value(snapshot, key) is None:
                continue
        options.append(
            {
                "key": key,
                "label": label,
                "penalty": int(config.get("penalty", 0)),
                "used": key in used_keys,
            }
        )
    return options
