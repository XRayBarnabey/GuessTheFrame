from __future__ import annotations

from app.games.answers import accepted_answers, match_answer, normalize, title_variants


def test_normalize_accents_apostrophes_and_punctuation() -> None:
    assert normalize("Amélie Poulain") == "amelie poulain"
    assert normalize("L’Odyssée d’Ulysse") == "l odyssee d ulysse"
    assert normalize("  Le   Seigneur, des Anneaux ! ") == "le seigneur des anneaux"
    assert normalize("Fast & Furious") == "fast et furious"
    assert normalize("Spider-Man") == "spider man"


def test_title_variants_remove_articles_and_subtitles() -> None:
    variants = title_variants("Le Seigneur des anneaux : La Communauté de l'anneau")
    assert "le seigneur des anneaux la communaute de l anneau" in variants
    assert "seigneur des anneaux la communaute de l anneau" in variants
    assert "le seigneur des anneaux" in variants


def test_movie_accepts_title_original_and_sort_variants() -> None:
    snapshot = {
        "type": "movie",
        "title": "Le Fabuleux Destin d'Amélie Poulain",
        "original_title": "Amélie",
        "sort_title": "Fabuleux Destin d'Amélie Poulain, Le",
    }
    accepted = accepted_answers(snapshot, {"accept_series_name": True})
    assert match_answer("Amélie", accepted, threshold=92)[0] is True
    assert match_answer("amelie", accepted, threshold=92)[0] is True
    assert match_answer("Le Fabuleux Destin d'Amelie Poulain", accepted, threshold=92)[0] is True


def test_series_name_is_answer_but_episode_title_alone_is_not() -> None:
    snapshot = {
        "type": "episode",
        "title": "The One Where It Rains",
        "episode_title": "The One Where It Rains",
        "series_name": "Friends",
        "series_original_title": "Friends",
        "season_number": 3,
        "episode_number": 8,
    }
    accepted = accepted_answers(snapshot, {"accept_series_name": True})
    assert match_answer("Friends", accepted)[0] is True
    assert match_answer("friends s03e08", accepted)[0] is True
    assert match_answer("Friends 3x08", accepted)[0] is True
    assert match_answer("The One Where It Rains", accepted)[0] is False
    assert match_answer("Friends The One Where It Rains", accepted)[0] is True


def test_fuzzy_tolerance_does_not_accept_plural_or_prefix() -> None:
    accepted = title_variants("Inception")
    assert match_answer("Incepton", accepted, threshold=92)[0] is True
    alien = title_variants("Alien")
    assert match_answer("Aliens", alien, threshold=92)[0] is False


def test_hint_values_are_not_part_of_accepted_answers() -> None:
    snapshot = {
        "type": "movie",
        "title": "Heat",
        "people": [
            {"name": "Michael Mann", "type": "Director"},
            {"name": "Al Pacino", "type": "Actor"},
            {"name": "Robert De Niro", "type": "Actor"},
        ],
        "year": 1995,
    }
    accepted = accepted_answers(snapshot, {})
    assert match_answer("Michael Mann", accepted)[0] is False
    assert match_answer("Al Pacino", accepted)[0] is False
    assert match_answer("1995", accepted)[0] is False
    assert match_answer("Heat", accepted)[0] is True


def test_empty_guess_is_never_correct() -> None:
    accepted = title_variants("Dune")
    assert match_answer("   ", accepted)[0] is False
    assert match_answer("", accepted)[0] is False
