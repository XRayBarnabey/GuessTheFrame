"""Answer normalisation and matching.

All validation happens on the backend. Accepted answers are built only from
titles and episode identifiers, never from hint values (director, actors, date).
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from app.core.text import normalize

LEADING_ARTICLES = (
    "le ",
    "la ",
    "les ",
    "l ",
    "un ",
    "une ",
    "des ",
    "du ",
    "the ",
    "a ",
    "an ",
)


def title_variants(value: str | None) -> set[str]:
    if not value:
        return set()
    text = str(value).strip()
    raw: set[str] = {text}
    raw.add(re.sub(r"\(\s*(?:19|20)\d{2}\s*\)", "", text))
    if ":" in text:
        raw.add(text.split(":", 1)[0])
    if "&" in text:
        raw.add(text.replace("&", "and"))
    if "," in text:
        left, right = text.rsplit(",", 1)
        if left.strip() and right.strip():
            raw.add(f"{right.strip()} {left.strip()}")

    variants: set[str] = set()
    for item in raw:
        norm = normalize(item)
        if not norm:
            continue
        variants.add(norm)
        without_year = re.sub(r"\s(?:19|20)\d{2}$", "", norm).strip()
        if without_year:
            variants.add(without_year)
        for article in LEADING_ARTICLES:
            if norm.startswith(article):
                rest = norm[len(article) :].strip()
                if rest:
                    variants.add(rest)
    return {value for value in variants if len(value) >= 2}


def accepted_answers(snapshot: dict[str, Any], game_config: dict[str, Any]) -> set[str]:
    media_type = str(snapshot.get("type") or "movie")
    answers: set[str] = set()

    if media_type == "movie":
        for value in (
            snapshot.get("title"),
            snapshot.get("original_title"),
            snapshot.get("sort_title"),
        ):
            answers |= title_variants(value)
        return answers

    series_variants: set[str] = set()
    for value in (
        snapshot.get("series_name"),
        snapshot.get("series_original_title"),
    ):
        series_variants |= title_variants(value)

    episode_variants: set[str] = set()
    for value in (snapshot.get("episode_title"), snapshot.get("title")):
        episode_variants |= title_variants(value)

    # The episode title is a hint, not the answer: the expected answer for a
    # series is the series name (optionally with season/episode). Accepting the
    # episode title alone would make the "episode name" hint equivalent to the
    # answer, which is explicitly forbidden.
    accept_series = bool(game_config.get("accept_series_name", True))
    if accept_series:
        answers |= series_variants

    season = snapshot.get("season_number")
    number = snapshot.get("episode_number")
    if season is not None and number is not None:
        for series in series_variants:
            for candidate in (
                f"{series} s{int(season):02d}e{int(number):02d}",
                f"{series} {int(season)}x{int(number):02d}",
                f"{series} saison {int(season)} episode {int(number)}",
            ):
                normalized = normalize(candidate)
                if normalized:
                    answers.add(normalized)

    for series in series_variants:
        for episode in episode_variants:
            normalized = normalize(f"{series} {episode}")
            if normalized:
                answers.add(normalized)

    return answers


def match_answer(
    guess: str,
    accepted: set[str],
    *,
    threshold: int = 92,
) -> tuple[bool, str | None]:
    normalized = normalize(guess)
    if not normalized:
        return False, None

    if normalized in accepted:
        return True, normalized

    # Controlled typo tolerance. We deliberately avoid prefix matches so that
    # "Alien" never validates "Aliens" or "Le Thing" never validates "Le Thing 2".
    for candidate in accepted:
        if len(candidate) < 6 or len(normalized) < 6:
            continue
        if abs(len(candidate) - len(normalized)) > max(1, len(candidate) // 8):
            continue
        if candidate.startswith(normalized) or normalized.startswith(candidate):
            continue
        if len(candidate.split()) != len(normalized.split()):
            continue
        if fuzz.ratio(candidate, normalized) >= threshold:
            return True, candidate

    return False, None
