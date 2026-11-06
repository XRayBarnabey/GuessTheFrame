"""1v1 duel domain: lobby, dice, settings, exchange and simultaneous play."""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.base import utcnow
from app.db.models import (
    DuelFrame,
    DuelGuess,
    DuelHint,
    DuelMatch,
    DuelParticipant,
    MediaItem,
    User,
)
from app.games.answers import accepted_answers, match_answer, normalize
from app.games.hints import build_hint, hint_options
from app.games.selection import pick_duel_media
from app.games.service import build_franchise_hint, snapshot_media

logger = logging.getLogger("guesstheframe.duels")

CODE_ALPHABET = string.digits
CODE_LENGTH = 4
DUEL_FRAMES_PER_PLAYER = 5
DEFAULT_DUEL_DURATION = 600
DEFAULT_HINT_TIME_PENALTY = 20
PROPOSAL_FINISH = "finish"
PROPOSAL_CANCEL = "cancel"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _hint_penalty_seconds(config: Any) -> int:
    return max(
        0,
        int((config.game_config or {}).get("duel_hint_penalty_seconds", DEFAULT_HINT_TIME_PENALTY)),
    )


def _media_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    media_type = snapshot.get("type")
    if media_type == "episode":
        season = snapshot.get("season_number")
        number = snapshot.get("episode_number")
        suffix = ""
        if season is not None and number is not None:
            suffix = f" S{int(season):02d}E{int(number):02d}"
        display = f"{snapshot.get('series_name') or snapshot.get('title') or ''}{suffix}".strip()
        answer = snapshot.get("series_name") or snapshot.get("title")
    else:
        display = str(snapshot.get("title") or "")
        answer = snapshot.get("title")
    return {
        "type": media_type,
        "title": snapshot.get("title"),
        "original_title": snapshot.get("original_title"),
        "answer_label": answer,
        "display_title": display,
        "year": snapshot.get("year"),
        "series_name": snapshot.get("series_name"),
        "season_number": snapshot.get("season_number"),
        "episode_number": snapshot.get("episode_number"),
        "episode_title": snapshot.get("episode_title"),
    }


async def _get_match(db: AsyncSession, match_id: str) -> DuelMatch:
    match = await db.get(DuelMatch, match_id)
    if match is None:
        raise AppError("DUEL_NOT_FOUND", "Duel introuvable.", status_code=404)
    return match


async def _participants(db: AsyncSession, match_id: str) -> list[DuelParticipant]:
    return list(
        (
            await db.execute(
                select(DuelParticipant)
                .where(DuelParticipant.match_id == match_id)
                .order_by(DuelParticipant.seat)
            )
        ).scalars().all()
    )


async def _participant_for(
    db: AsyncSession, match: DuelMatch, user_id: int, *, lock: bool = False
) -> DuelParticipant:
    statement = select(DuelParticipant).where(
        DuelParticipant.match_id == match.id,
        DuelParticipant.user_id == user_id,
    )
    if lock:
        statement = statement.with_for_update()
    participant = (await db.execute(statement)).scalar_one_or_none()
    if participant is None:
        raise AppError(
            "DUEL_ACCESS_DENIED",
            "Vous ne participez pas à ce duel.",
            status_code=403,
        )
    return participant


async def _usernames(db: AsyncSession, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(
                User.id,
                func.coalesce(User.display_name, User.username),
            ).where(User.id.in_(user_ids))
        )
    ).all()
    return {user_id: username for user_id, username in rows}


async def _new_code(db: AsyncSession) -> str:
    for _ in range(40):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        exists = (
            await db.execute(select(DuelMatch.id).where(DuelMatch.code == code))
        ).scalar_one_or_none()
        if exists is None:
            return code
    raise AppError(
        "DUEL_CODE_ERROR",
        "Impossible de générer un code de duel.",
        status_code=500,
    )


async def create_duel(
    db: AsyncSession,
    *,
    session: Any,
    config: Any,
    categories: list[str],
    genres: list[str],
    library_ids: list[str] | None,
) -> dict[str, Any]:
    media = await pick_duel_media(
        db,
        categories=categories,
        genres=genres,
        library_ids=library_ids,
        count=DUEL_FRAMES_PER_PLAYER * 2,
    )
    code = await _new_code(db)
    media_types = (
        ["movie", "episode"]
        if "movie" in categories and ({"series", "anime"} & set(categories))
        else ["movie"]
        if "movie" in categories
        else ["episode"]
    )
    match = DuelMatch(
        code=code,
        status="waiting",
        phase="lobby",
        player1_id=session.user_id,
        filters={
            "categories": categories,
            "media_types": media_types,
            "genres": genres,
            "library_ids": library_ids,
        },
    )
    db.add(match)
    await db.flush()

    db.add(
        DuelParticipant(
            match_id=match.id,
            user_id=session.user_id,
            seat=1,
        )
    )
    # All ten frames are created now; the second five are reassigned to player 2
    # when they join. Positions 5..9 are temporary.
    for position, media_item in enumerate(media):
        db.add(
            DuelFrame(
                match_id=match.id,
                original_owner_id=session.user_id,
                holder_id=session.user_id,
                position=position,
                media_id=media_item.id,
                media_snapshot=snapshot_media(media_item),
                frame_keys=[],
            )
        )
    await db.commit()
    await db.refresh(match)
    logger.info("Duel %s created by %s (%s)", match.id, session.user.username, code)
    return await duel_state(db, match, session.user_id, config=config)


async def join_duel(
    db: AsyncSession, *, session: Any, code: str, config: Any
) -> dict[str, Any]:
    match = (
        await db.execute(
            select(DuelMatch).where(DuelMatch.code == code.strip())
        )
    ).scalar_one_or_none()
    if match is None:
        raise AppError("DUEL_NOT_FOUND", "Aucun duel avec ce code.", status_code=404)
    if match.player1_id == session.user_id:
        raise AppError(
            "DUEL_OWN_MATCH",
            "Vous ne pouvez pas rejoindre votre propre duel.",
            status_code=409,
        )
    if match.player2_id is not None:
        raise AppError("DUEL_FULL", "Ce duel est déjà complet.", status_code=409)
    if match.status != "waiting":
        raise AppError("DUEL_ALREADY_STARTED", "Ce duel a déjà commencé.", status_code=409)

    match.player2_id = session.user_id
    match.status = "active"
    match.phase = "dice"
    db.add(
        DuelParticipant(
            match_id=match.id,
            user_id=session.user_id,
            seat=2,
        )
    )
    second_frames = list(
        (
            await db.execute(
                select(DuelFrame)
                .where(DuelFrame.match_id == match.id, DuelFrame.position >= 5)
                .order_by(DuelFrame.position)
            )
        ).scalars().all()
    )
    for frame in second_frames:
        frame.original_owner_id = session.user_id
        frame.holder_id = session.user_id
        frame.position -= 5
    await db.commit()
    logger.info("Duel %s joined by %s", match.id, session.user.username)
    return await duel_state(db, match, session.user_id, config=config)


async def roll_dice(
    db: AsyncSession, *, match_id: str, user_id: int, config: Any
) -> dict[str, Any]:
    match = await _get_match(db, match_id)
    if match.phase != "dice":
        raise AppError("DUEL_WRONG_PHASE", "Les dés ne sont pas disponibles.", status_code=409)
    participant = await _participant_for(db, match, user_id, lock=True)
    if participant.dice_value is not None:
        raise AppError("DUEL_ALREADY_ROLLED", "Vous avez déjà lancé le dé.", status_code=409)

    participant.dice_value = secrets.randbelow(6) + 1
    participant.dice_history = [*(participant.dice_history or []), participant.dice_value]
    participants = await _participants(db, match.id)
    values = {p.user_id: p.dice_value for p in participants}
    if len(participants) == 2 and all(value is not None for value in values.values()):
        first, second = participants
        assert first.dice_value is not None and second.dice_value is not None
        if first.dice_value == second.dice_value:
            match.last_dice = {
                "player1": first.dice_value,
                "player2": second.dice_value,
                "tie": True,
            }
            first.dice_value = None
            second.dice_value = None
        else:
            winner = first if first.dice_value > second.dice_value else second
            match.last_dice = {
                "player1": first.dice_value,
                "player2": second.dice_value,
                "tie": False,
                "winner_id": winner.user_id,
            }
            match.settings_setter_id = winner.user_id
            match.phase = "settings"
    await db.commit()
    return await duel_state(db, match, user_id, config=config)


async def _start_playing(db: AsyncSession, match: DuelMatch) -> None:
    now = utcnow()
    match.status = "active"
    match.phase = "playing"
    match.started_at = now
    match.ends_at = now + timedelta(seconds=max(60, int(match.duration_seconds)))
    await db.commit()


async def set_duel_settings(
    db: AsyncSession,
    *,
    match_id: str,
    user_id: int,
    exchange_count: int,
    duration_seconds: int,
    config: Any,
) -> dict[str, Any]:
    match = await _get_match(db, match_id)
    if match.phase != "settings":
        raise AppError("DUEL_WRONG_PHASE", "Le réglage n'est pas disponible.", status_code=409)
    if match.settings_setter_id != user_id:
        raise AppError(
            "DUEL_NOT_SETTER",
            "Seul le joueur ayant gagné le lancer de dé peut régler la partie.",
            status_code=403,
        )
    if not 0 <= exchange_count <= DUEL_FRAMES_PER_PLAYER:
        raise AppError("DUEL_INVALID_EXCHANGE", "Nombre d'échanges invalide.", status_code=422)
    if not 300 <= duration_seconds <= 3600:
        raise AppError("DUEL_INVALID_DURATION", "Durée invalide (5 à 60 minutes).", status_code=422)

    match.exchange_count = exchange_count
    match.duration_seconds = duration_seconds
    if exchange_count == 0:
        await _start_playing(db, match)
    else:
        match.phase = "exchange"
        await db.commit()
    return await duel_state(db, match, user_id, config=config)


async def submit_exchange(
    db: AsyncSession,
    *,
    match_id: str,
    user_id: int,
    frame_ids: list[str],
    config: Any,
) -> dict[str, Any]:
    match = await _get_match(db, match_id)
    if match.phase != "exchange":
        raise AppError("DUEL_WRONG_PHASE", "L'échange n'est pas disponible.", status_code=409)
    participant = await _participant_for(db, match, user_id, lock=True)
    if participant.submitted_exchange:
        raise AppError("DUEL_EXCHANGE_SUBMITTED", "Votre sélection est déjà envoyée.", status_code=409)
    unique_ids = list(dict.fromkeys(frame_ids))
    if len(unique_ids) != match.exchange_count:
        raise AppError(
            "DUEL_INVALID_EXCHANGE",
            f"Sélectionnez exactement {match.exchange_count} frame(s).",
            status_code=422,
        )
    frames = list(
        (
            await db.execute(
                select(DuelFrame).where(
                    DuelFrame.match_id == match.id,
                    DuelFrame.id.in_(unique_ids),
                )
            )
        ).scalars().all()
    )
    if len(frames) != match.exchange_count or any(
        frame.holder_id != user_id for frame in frames
    ):
        raise AppError(
            "DUEL_INVALID_FRAME",
            "Une des frames sélectionnées ne vous appartient pas.",
            status_code=403,
        )
    participant.selected_frame_ids = unique_ids
    participant.submitted_exchange = True
    await db.commit()

    participants = await _participants(db, match.id)
    if len(participants) == 2 and all(p.submitted_exchange for p in participants):
        first, second = participants
        first_frames = list(
            (
                await db.execute(
                    select(DuelFrame).where(
                        DuelFrame.match_id == match.id,
                        DuelFrame.id.in_(first.selected_frame_ids or []),
                    )
                )
            ).scalars().all()
        )
        second_frames = list(
            (
                await db.execute(
                    select(DuelFrame).where(
                        DuelFrame.match_id == match.id,
                        DuelFrame.id.in_(second.selected_frame_ids or []),
                    )
                )
            ).scalars().all()
        )
        for frame in first_frames:
            frame.holder_id = second.user_id
        for frame in second_frames:
            frame.holder_id = first.user_id
        await _start_playing(db, match)
    return await duel_state(db, match, user_id, config=config)


def _personal_deadline(
    match: DuelMatch, participant: DuelParticipant
) -> datetime | None:
    if match.ends_at is None:
        return None
    return match.ends_at - timedelta(seconds=max(0, participant.time_penalty_seconds))


async def _finish_match(
    db: AsyncSession,
    match: DuelMatch,
    *,
    reason: str = "time",
    forced_winner_id: int | None = None,
    force_draw: bool = False,
    status: str = "finished",
) -> None:
    if match.phase == "finished":
        return
    participants = await _participants(db, match.id)
    if len(participants) < 2:
        return
    names = await _usernames(db, {match.player1_id, match.player2_id or 0})

    def rank_key(participant: DuelParticipant) -> tuple:
        finished = participant.finished_at or datetime.max
        return (
            -participant.found_count,
            finished,
            participant.attempts_count,
            participant.time_penalty_seconds,
        )

    winner_id: int | None
    if force_draw:
        winner_id = None
    elif forced_winner_id is not None:
        winner_id = forced_winner_id
    else:
        ordered = sorted(participants, key=rank_key)
        first = ordered[0]
        second = ordered[1]
        # A draw is possible when every metric is identical.
        winner_id = first.user_id if rank_key(first) != rank_key(second) else None

    match.status = status
    match.phase = "finished"
    match.finished_at = utcnow()
    match.winner_id = winner_id
    match.proposal = {}

    frames = list(
        (
            await db.execute(
                select(DuelFrame)
                .where(DuelFrame.match_id == match.id)
                .order_by(DuelFrame.position)
            )
        ).scalars().all()
    )
    hint_rows = list(
        (
            await db.execute(
                select(DuelHint)
                .where(DuelHint.match_id == match.id)
                .order_by(DuelHint.created_at, DuelHint.id)
            )
        ).scalars().all()
    )
    hints_by_frame: dict[str, list[dict[str, Any]]] = {}
    for hint in hint_rows:
        payload = hint.payload or {}
        hints_by_frame.setdefault(hint.frame_id, []).append(
            {
                "user_id": hint.user_id,
                "username": names.get(hint.user_id, "Joueur"),
                "key": hint.hint_key,
                "label": payload.get("label") or hint.hint_key,
                "value": payload.get("value"),
                "penalty": payload.get("penalty", 0),
            }
        )
    match.result = {
        "winner_id": winner_id,
        "winner_username": names.get(winner_id) if winner_id else None,
        "draw": winner_id is None,
        "reason": reason,
        "cancelled": status == "cancelled",
        "ranked": status == "finished",
        "players": [
            {
                "user_id": participant.user_id,
                "username": names.get(participant.user_id, "Joueur"),
                "seat": participant.seat,
                "found": participant.found_count,
                "attempts": participant.attempts_count,
                "hints": participant.hints_count,
                "time_penalty_seconds": participant.time_penalty_seconds,
                "finished_at": _iso(participant.finished_at),
                "winner": participant.user_id == winner_id,
            }
            for participant in participants
        ],
        "frames": [
            {
                "id": frame.id,
                "original_owner_id": frame.original_owner_id,
                "original_owner_username": names.get(
                    frame.original_owner_id, "Joueur"
                ),
                "holder_id": frame.holder_id,
                "holder_username": names.get(frame.holder_id, "Joueur"),
                "exchanged": frame.original_owner_id != frame.holder_id,
                "position": frame.position,
                "media": _media_summary(frame.media_snapshot or {}),
                "solved_by_user_id": frame.solved_by_user_id,
                "solved_by_username": names.get(frame.solved_by_user_id)
                if frame.solved_by_user_id
                else None,
                "hints": hints_by_frame.get(frame.id, []),
            }
            for frame in frames
        ],
    }
    await db.commit()


async def _maybe_finish(db: AsyncSession, match: DuelMatch) -> None:
    if match.phase != "playing":
        return
    participants = await _participants(db, match.id)
    if len(participants) < 2:
        return
    now = utcnow()
    if all(p.finished_at is not None for p in participants):
        await _finish_match(db, match, reason="completed")
        return
    deadlines = [
        _personal_deadline(match, participant) for participant in participants
    ]
    no_one_can_play = all(
        participant.finished_at is not None
        or (deadline is not None and now >= deadline)
        for participant, deadline in zip(participants, deadlines)
    )
    if no_one_can_play:
        await _finish_match(db, match, reason="time")
        return
    if match.ends_at and now >= match.ends_at:
        await _finish_match(db, match, reason="time")


async def abandon_duel(
    db: AsyncSession, *, match_id: str, user_id: int, config: Any
) -> dict[str, Any]:
    """Abandon immediately: the opponent wins and the result is recorded."""
    match = await _get_match(db, match_id)
    if match.phase == "finished":
        return await duel_state(db, match, user_id, config=config)
    if match.player2_id is None:
        raise AppError(
            "DUEL_NO_OPPONENT",
            "Aucun adversaire n'a encore rejoint ce duel.",
            status_code=409,
        )
    await _participant_for(db, match, user_id, lock=True)
    participants = await _participants(db, match.id)
    opponent = next(
        (participant for participant in participants if participant.user_id != user_id),
        None,
    )
    if opponent is None:
        raise AppError(
            "DUEL_NO_OPPONENT",
            "Aucun adversaire n'a encore rejoint ce duel.",
            status_code=409,
        )
    await _finish_match(
        db,
        match,
        reason="abandon",
        forced_winner_id=opponent.user_id,
    )
    logger.info("Duel %s abandoned by %s", match.id, user_id)
    return await duel_state(db, match, user_id, config=config)


async def finish_duel_now(
    db: AsyncSession, *, match_id: str, user_id: int, config: Any
) -> dict[str, Any]:
    """End the duel immediately and keep the current score as the result."""
    match = await _get_match(db, match_id)
    if match.phase == "finished":
        return await duel_state(db, match, user_id, config=config)
    if match.player2_id is None:
        raise AppError(
            "DUEL_NO_OPPONENT",
            "Aucun adversaire n'a encore rejoint ce duel.",
            status_code=409,
        )
    await _participant_for(db, match, user_id, lock=True)
    await _finish_match(db, match, reason="early_end")
    logger.info("Duel %s ended early by %s", match.id, user_id)
    return await duel_state(db, match, user_id, config=config)


async def propose_duel_action(
    db: AsyncSession,
    *,
    match_id: str,
    user_id: int,
    action: str,
    config: Any,
) -> dict[str, Any]:
    """Propose to end now or to cancel the duel as a draw."""
    if action not in {PROPOSAL_FINISH, PROPOSAL_CANCEL}:
        raise AppError(
            "DUEL_INVALID_PROPOSAL",
            "Proposition invalide.",
            status_code=422,
        )
    match = await _get_match(db, match_id)
    if match.phase == "finished":
        return await duel_state(db, match, user_id, config=config)
    if match.player2_id is None:
        raise AppError(
            "DUEL_NO_OPPONENT",
            "Aucun adversaire n'a encore rejoint ce duel.",
            status_code=409,
        )
    await _participant_for(db, match, user_id, lock=True)
    if match.proposal:
        raise AppError(
            "DUEL_PROPOSAL_PENDING",
            "Une proposition est déjà en attente de réponse.",
            status_code=409,
        )
    match.proposal = {
        "type": action,
        "by": user_id,
        "created_at": _iso(utcnow()),
    }
    await db.commit()
    return await duel_state(db, match, user_id, config=config)


async def respond_duel_proposal(
    db: AsyncSession,
    *,
    match_id: str,
    user_id: int,
    accept: bool,
    config: Any,
) -> dict[str, Any]:
    """Accept or refuse the opponent's finish/cancel proposal."""
    match = await _get_match(db, match_id)
    if match.phase == "finished":
        return await duel_state(db, match, user_id, config=config)
    proposal = match.proposal or {}
    if not proposal:
        raise AppError(
            "DUEL_NO_PROPOSAL",
            "Aucune proposition n'est en attente.",
            status_code=409,
        )
    if proposal.get("by") == user_id:
        raise AppError(
            "DUEL_OWN_PROPOSAL",
            "Vous ne pouvez pas répondre à votre propre proposition.",
            status_code=409,
        )
    await _participant_for(db, match, user_id, lock=True)
    if not accept:
        match.proposal = {}
        await db.commit()
        return await duel_state(db, match, user_id, config=config)

    if proposal.get("type") == PROPOSAL_CANCEL:
        await _finish_match(
            db,
            match,
            reason="cancelled",
            force_draw=True,
            status="cancelled",
        )
    else:
        await _finish_match(db, match, reason="early_end")
    return await duel_state(db, match, user_id, config=config)


async def duel_state(
    db: AsyncSession, match: DuelMatch, user_id: int, *, config: Any
) -> dict[str, Any]:
    await _maybe_finish(db, match)
    participant = await _participant_for(db, match, user_id)
    participants = await _participants(db, match.id)
    opponent = next((p for p in participants if p.user_id != user_id), None)
    names = await _usernames(db, {match.player1_id, match.player2_id or 0})
    now = utcnow()

    frames = (
        []
        if match.phase == "lobby"
        else list(
            (
                await db.execute(
                    select(DuelFrame)
                    .where(
                        DuelFrame.match_id == match.id,
                        DuelFrame.holder_id == user_id,
                        DuelFrame.position < DUEL_FRAMES_PER_PLAYER,
                    )
                    .order_by(DuelFrame.position)
                )
            ).scalars().all()
        )
    )
    hints = list(
        (
            await db.execute(
                select(DuelHint).where(
                    DuelHint.match_id == match.id, DuelHint.user_id == user_id
                )
            )
        ).scalars().all()
    )
    hints_by_frame: dict[str, list[DuelHint]] = {}
    for hint in hints:
        hints_by_frame.setdefault(hint.frame_id, []).append(hint)

    frames_data = []
    for frame in frames:
        used_hints = hints_by_frame.get(frame.id, [])
        used_keys = {hint.hint_key for hint in used_hints}
        revealed_type = next(
            (
                str(hint.payload.get("value"))
                for hint in used_hints
                if hint.hint_key == "media_type"
            ),
            None,
        )
        options = hint_options(
            snapshot=frame.media_snapshot or {},
            hint_config=config.hint_config or {},
            used_keys=used_keys,
            media_types=(match.filters or {}).get("media_types"),
            revealed_media_type=revealed_type,
        )
        solved = frame.solved_by_user_id == user_id
        frames_data.append(
            {
                "id": frame.id,
                "position": frame.position,
                "solved": solved,
                "image_url": f"/api/duels/{match.id}/frames/{frame.id}",
                "hint_options": options,
                "hints_used": [hint.payload for hint in used_hints],
                "media": _media_summary(frame.media_snapshot or {})
                if solved or match.phase == "finished"
                else None,
            }
        )

    deadline = _personal_deadline(match, participant)
    remaining = (
        max(0, int((deadline - now).total_seconds()))
        if deadline is not None and match.phase == "playing"
        else None
    )

    def participant_payload(item: DuelParticipant) -> dict[str, Any]:
        item_deadline = _personal_deadline(match, item)
        remaining_seconds = (
            max(0, int((item_deadline - now).total_seconds()))
            if item_deadline and match.phase == "playing"
            else None
        )
        return {
            "user_id": item.user_id,
            "username": names.get(item.user_id, "Joueur"),
            "seat": item.seat,
            "dice_value": item.dice_value,
            "dice_history": item.dice_history or [],
            "found": item.found_count,
            "attempts": item.attempts_count,
            "hints": item.hints_count,
            "submitted_exchange": item.submitted_exchange,
            "finished": item.finished_at is not None,
            "deadline_at": _iso(item_deadline),
            "remaining_seconds": remaining_seconds,
            "timed_out": remaining_seconds == 0,
        }

    return {
        "id": match.id,
        "code": match.code,
        "status": match.status,
        "phase": match.phase,
        "server_time": _iso(now),
        "player1": {
            "user_id": match.player1_id,
            "username": names.get(match.player1_id, "Joueur"),
        },
        "player2": {
            "user_id": match.player2_id,
            "username": names.get(match.player2_id) if match.player2_id else None,
        },
        "settings_setter_id": match.settings_setter_id,
        "winner_id": match.winner_id,
        "exchange_count": match.exchange_count,
        "duration_seconds": match.duration_seconds,
        "hint_penalty_seconds": _hint_penalty_seconds(config),
        "last_dice": match.last_dice or {},
        "proposal": match.proposal or None,
        "started_at": _iso(match.started_at),
        "ends_at": _iso(match.ends_at),
        "finished_at": _iso(match.finished_at),
        "filters": match.filters,
        "you": participant_payload(participant),
        "opponent": participant_payload(opponent) if opponent else None,
        "frames": frames_data,
        "result": match.result if match.phase == "finished" else {},
    }


async def guess_duel_frame(
    db: AsyncSession,
    *,
    match_id: str,
    user_id: int,
    frame_id: str,
    guess: str,
    config: Any,
) -> dict[str, Any]:
    match = await _get_match(db, match_id)
    if match.phase != "playing":
        raise AppError("DUEL_NOT_PLAYING", "La partie n'est pas en cours.", status_code=409)
    participant = await _participant_for(db, match, user_id, lock=True)
    frame = await db.get(DuelFrame, frame_id)
    if frame is None or frame.match_id != match.id or frame.holder_id != user_id:
        raise AppError("DUEL_FRAME_NOT_FOUND", "Frame introuvable.", status_code=404)
    if frame.solved_by_user_id is not None:
        raise AppError("DUEL_FRAME_SOLVED", "Cette frame est déjà trouvée.", status_code=409)
    deadline = _personal_deadline(match, participant)
    if deadline is not None and utcnow() >= deadline:
        await _maybe_finish(db, match)
        raise AppError("DUEL_TIME_UP", "Votre temps est écoulé.", status_code=409)

    accepted = accepted_answers(
        frame.media_snapshot or {}, config.game_config or {}
    )
    correct, _matched = match_answer(
        guess,
        accepted,
        threshold=int((config.game_config or {}).get("answer_similarity", 92)),
    )
    participant.attempts_count += 1
    db.add(
        DuelGuess(
            match_id=match.id,
            frame_id=frame.id,
            user_id=user_id,
            guess=guess.strip()[:500],
            is_correct=correct,
        )
    )
    if correct:
        frame.solved_by_user_id = user_id
        frame.solved_at = utcnow()
        participant.found_count += 1
        if participant.found_count >= DUEL_FRAMES_PER_PLAYER:
            participant.finished_at = utcnow()
    await db.commit()
    await _maybe_finish(db, match)
    state = await duel_state(db, match, user_id, config=config)
    return {"correct": correct, "state": state}


async def request_duel_hint(
    db: AsyncSession,
    *,
    match_id: str,
    user_id: int,
    frame_id: str,
    hint_key: str,
    config: Any,
) -> dict[str, Any]:
    match = await _get_match(db, match_id)
    if match.phase != "playing":
        raise AppError("DUEL_NOT_PLAYING", "La partie n'est pas en cours.", status_code=409)
    participant = await _participant_for(db, match, user_id, lock=True)
    frame = await db.get(DuelFrame, frame_id)
    if frame is None or frame.match_id != match.id or frame.holder_id != user_id:
        raise AppError("DUEL_FRAME_NOT_FOUND", "Frame introuvable.", status_code=404)
    if frame.solved_by_user_id is not None:
        raise AppError("DUEL_FRAME_SOLVED", "Cette frame est déjà trouvée.", status_code=409)
    deadline = _personal_deadline(match, participant)
    if deadline is not None and utcnow() >= deadline:
        raise AppError("DUEL_TIME_UP", "Votre temps est écoulé.", status_code=409)

    used_hints = list(
        (
            await db.execute(
                select(DuelHint).where(
                    DuelHint.match_id == match.id,
                    DuelHint.user_id == user_id,
                    DuelHint.frame_id == frame.id,
                )
            )
        ).scalars().all()
    )
    used_keys = {hint.hint_key for hint in used_hints}
    if hint_key in used_keys:
        raise AppError("HINT_ALREADY_USED", "Cet indice a déjà été utilisé.", status_code=409)
    revealed_type = next(
        (
            str(hint.payload.get("value"))
            for hint in used_hints
            if hint.hint_key == "media_type"
        ),
        None,
    )
    allowed = {
        option["key"]
        for option in hint_options(
            snapshot=frame.media_snapshot or {},
            hint_config=config.hint_config or {},
            used_keys=used_keys,
            media_types=(match.filters or {}).get("media_types"),
            revealed_media_type=revealed_type,
        )
    }
    if hint_key not in allowed:
        raise AppError("HINT_UNAVAILABLE", "Cet indice n'est pas disponible.", status_code=409)
    accepted = accepted_answers(frame.media_snapshot or {}, config.game_config or {})
    if hint_key == "franchise":
        hint = await build_franchise_hint(frame.media_snapshot or {}, config)
    else:
        hint = build_hint(
            snapshot=frame.media_snapshot or {},
            hint_key=hint_key,
            hint_config=config.hint_config or {},
            accepted_answers=accepted,
        )
    if hint is None:
        raise AppError("HINT_UNAVAILABLE", "Cet indice n'est pas disponible.", status_code=409)

    penalty = _hint_penalty_seconds(config)
    db.add(
        DuelHint(
            match_id=match.id,
            frame_id=frame.id,
            user_id=user_id,
            hint_key=hint_key,
            payload=hint,
        )
    )
    participant.hints_count += 1
    participant.time_penalty_seconds += penalty
    await db.commit()
    state = await duel_state(db, match, user_id, config=config)
    state["hint"] = hint
    return state


async def list_my_duels(
    db: AsyncSession, *, user_id: int, config: Any
) -> list[dict[str, Any]]:
    matches = list(
        (
            await db.execute(
                select(DuelMatch)
                .where(
                    (DuelMatch.player1_id == user_id)
                    | (DuelMatch.player2_id == user_id)
                )
                .order_by(DuelMatch.created_at.desc())
                .limit(20)
            )
        ).scalars().all()
    )
    result = []
    for match in matches:
        result.append(
            {
                "id": match.id,
                "code": match.code,
                "phase": match.phase,
                "status": match.status,
                "created_at": _iso(match.created_at),
                "player1_id": match.player1_id,
                "player2_id": match.player2_id,
                "winner_id": match.winner_id,
            }
        )
    return result


async def finish_expired_duels() -> int:
    from app.db.session import AsyncSessionLocal

    finished = 0
    async with AsyncSessionLocal() as db:
        matches = list(
            (
                await db.execute(
                    select(DuelMatch).where(
                        DuelMatch.phase == "playing",
                        DuelMatch.ends_at.is_not(None),
                        DuelMatch.ends_at <= utcnow(),
                    )
                )
            ).scalars().all()
        )
        for match in matches:
            await _finish_match(db, match)
            finished += 1
    return finished
