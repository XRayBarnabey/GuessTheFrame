"""Score calculation, always on the backend."""

from __future__ import annotations

from typing import Any


def difficulty_settings(config: dict[str, Any], difficulty: str) -> dict[str, Any]:
    difficulty_config = config.get("difficulty_config") or {}
    return (
        difficulty_config.get(difficulty)
        or difficulty_config.get("normal")
        or {
            "max_hints": 3,
            "wrong_penalty_multiplier": 1.0,
            "score_multiplier": 1.0,
        }
    )


def hint_penalty(hints_used: list[dict[str, Any]]) -> int:
    return sum(int(hint.get("penalty") or 0) for hint in hints_used)


def compute_potential_score(
    *,
    config: dict[str, Any],
    difficulty: str,
    attempts_count: int,
    hints_used: list[dict[str, Any]],
) -> int:
    game_config = config.get("game_config") or {}
    diff = difficulty_settings(config, difficulty)
    base = int(game_config.get("base_points", 100))
    per_error = int(game_config.get("wrong_attempt_penalty", 5))
    cap = int(game_config.get("max_wrong_penalty", 25))
    multiplier = float(diff.get("score_multiplier", 1.0))
    error_multiplier = float(diff.get("wrong_penalty_multiplier", 1.0))

    wrong_penalty = min(
        max(0, attempts_count) * per_error * error_multiplier,
        cap,
    )
    raw = base - hint_penalty(hints_used) - wrong_penalty
    return max(0, int(round(raw * multiplier)))


def final_score(
    *,
    config: dict[str, Any],
    difficulty: str,
    attempts_count: int,
    hints_used: list[dict[str, Any]],
    won: bool,
) -> tuple[int, dict[str, Any]]:
    if not won:
        return 0, {"won": False, "reason": "abandoned"}

    game_config = config.get("game_config") or {}
    diff = difficulty_settings(config, difficulty)
    base = int(game_config.get("base_points", 100))
    per_error = int(game_config.get("wrong_attempt_penalty", 5))
    cap = int(game_config.get("max_wrong_penalty", 25))
    multiplier = float(diff.get("score_multiplier", 1.0))
    error_multiplier = float(diff.get("wrong_penalty_multiplier", 1.0))

    wrong_attempts = max(0, attempts_count - 1)
    wrong_penalty = min(wrong_attempts * per_error * error_multiplier, cap)
    hints_total = hint_penalty(hints_used)
    raw = base - hints_total - wrong_penalty
    score = max(0, int(round(raw * multiplier)))

    return score, {
        "won": True,
        "base": base,
        "hint_penalty": hints_total,
        "wrong_attempts": wrong_attempts,
        "wrong_penalty": wrong_penalty,
        "multiplier": multiplier,
        "final": score,
    }
