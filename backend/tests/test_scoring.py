from __future__ import annotations

from app.games.scoring import compute_potential_score, final_score

CONFIG = {
    "game_config": {
        "base_points": 100,
        "wrong_attempt_penalty": 5,
        "max_wrong_penalty": 25,
        "accept_series_name": True,
    },
    "difficulty_config": {
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
    },
}


def test_perfect_score() -> None:
    assert (
        compute_potential_score(
            config=CONFIG, difficulty="normal", attempts_count=0, hints_used=[]
        )
        == 100
    )


def test_hint_penalties() -> None:
    hints = [
        {"key": "release_date", "penalty": 10},
        {"key": "director", "penalty": 15},
    ]
    assert (
        compute_potential_score(
            config=CONFIG, difficulty="normal", attempts_count=0, hints_used=hints
        )
        == 75
    )


def test_wrong_attempts_are_capped() -> None:
    score = compute_potential_score(
        config=CONFIG, difficulty="normal", attempts_count=20, hints_used=[]
    )
    assert score == 75  # 100 - cap(25)


def test_easy_ignores_wrong_attempts_and_applies_multiplier() -> None:
    score = compute_potential_score(
        config=CONFIG, difficulty="easy", attempts_count=5, hints_used=[]
    )
    assert score == 80


def test_final_score_discounts_correct_attempt() -> None:
    score, breakdown = final_score(
        config=CONFIG,
        difficulty="normal",
        attempts_count=3,
        hints_used=[],
        won=True,
    )
    assert score == 90
    assert breakdown["wrong_attempts"] == 2


def test_hard_multiplier_and_penalty() -> None:
    score, _ = final_score(
        config=CONFIG,
        difficulty="hard",
        attempts_count=2,
        hints_used=[{"key": "actor1", "penalty": 10}],
        won=True,
    )
    # 100 - 10 hint - (1 error * 5 * 1.5 = 7.5) = 82.5, * 1.3 = 107.25 -> 107
    assert score == 107


def test_score_never_negative() -> None:
    score, _ = final_score(
        config=CONFIG,
        difficulty="hard",
        attempts_count=50,
        hints_used=[
            {"key": "release_date", "penalty": 100},
            {"key": "director", "penalty": 100},
        ],
        won=True,
    )
    assert score == 0


def test_abandon_is_zero() -> None:
    score, breakdown = final_score(
        config=CONFIG,
        difficulty="normal",
        attempts_count=2,
        hints_used=[{"key": "director", "penalty": 15}],
        won=False,
    )
    assert score == 0
    assert breakdown["won"] is False
