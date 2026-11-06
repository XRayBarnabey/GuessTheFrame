from __future__ import annotations

from app.games.hints import next_hint

SNAPSHOT = {
    "type": "movie",
    "title": "Heat",
    "year": 1995,
    "people": [
        {"name": "Michael Mann", "type": "Director"},
        {"name": "Al Pacino", "type": "Actor"},
        {"name": "Robert De Niro", "type": "Actor"},
    ],
}

HINT_CONFIG = {
    "order": ["release_date", "director", "actor1", "actor2", "episode_title"],
    "items": {
        "release_date": {"enabled": True, "penalty": 10},
        "director": {"enabled": True, "penalty": 15},
        "actor1": {"enabled": True, "penalty": 10},
        "actor2": {"enabled": True, "penalty": 10},
        "episode_title": {"enabled": True, "penalty": 15},
    },
}


def test_hints_are_progressive_and_skip_used() -> None:
    hint, reason = next_hint(
        snapshot=SNAPSHOT,
        hint_config=HINT_CONFIG,
        used_keys={"release_date"},
        max_hints=4,
        accepted_answers={"heat"},
    )
    assert reason == "ok"
    assert hint is not None
    assert hint["key"] == "director"
    assert hint["value"] == "Michael Mann"


def test_missing_metadata_is_skipped() -> None:
    snapshot = {"type": "movie", "title": "Unknown", "people": [], "year": None}
    hint, reason = next_hint(
        snapshot=snapshot,
        hint_config=HINT_CONFIG,
        used_keys=set(),
        max_hints=4,
        accepted_answers={"unknown"},
    )
    assert hint is None
    assert reason == "exhausted"


def test_hint_cannot_be_the_answer() -> None:
    snapshot = {
        "type": "movie",
        "title": "Napoleon",
        "year": 2023,
        "people": [{"name": "Napoleon", "type": "Director"}],
    }
    hint, _ = next_hint(
        snapshot=snapshot,
        hint_config=HINT_CONFIG,
        used_keys={"release_date"},
        max_hints=4,
        accepted_answers={"napoleon"},
    )
    assert hint is None


def test_max_hints_limit() -> None:
    hint, reason = next_hint(
        snapshot=SNAPSHOT,
        hint_config=HINT_CONFIG,
        used_keys={"release_date", "director"},
        max_hints=2,
        accepted_answers={"heat"},
    )
    assert hint is None
    assert reason == "limit"


def test_episode_title_hint_only_for_episodes() -> None:
    episode = {
        "type": "episode",
        "title": "Pilot",
        "episode_title": "Pilot",
        "year": 2004,
        "people": [{"name": "J. J. Abrams", "type": "Director"}],
    }
    hint, _ = next_hint(
        snapshot=episode,
        hint_config=HINT_CONFIG,
        used_keys={"release_date", "director", "actor1", "actor2"},
        max_hints=10,
        accepted_answers={"lost"},
    )
    assert hint is not None
    assert hint["key"] == "episode_title"
    assert hint["value"] == "Pilot"

    movie_hint, _ = next_hint(
        snapshot=SNAPSHOT,
        hint_config=HINT_CONFIG,
        used_keys={"release_date", "director", "actor1", "actor2"},
        max_hints=10,
        accepted_answers={"heat"},
    )
    assert movie_hint is None


def test_disabled_hint_is_skipped() -> None:
    config = {
        "order": ["release_date", "director"],
        "items": {
            "release_date": {"enabled": False, "penalty": 10},
            "director": {"enabled": True, "penalty": 15},
        },
    }
    hint, _ = next_hint(
        snapshot=SNAPSHOT,
        hint_config=config,
        used_keys=set(),
        max_hints=2,
        accepted_answers={"heat"},
    )
    assert hint is not None
    assert hint["key"] == "director"
