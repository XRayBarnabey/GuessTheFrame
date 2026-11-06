"""1v1 duel HTTP routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_csrf, require_session
from app.core.errors import AppError
from app.db.models import DuelFrame, DuelMatch, DuelParticipant, UserSession
from app.db.session import get_db
from app.duels.service import (
    abandon_duel,
    create_duel,
    duel_state,
    finish_duel_now,
    guess_duel_frame,
    join_duel,
    list_my_duels,
    propose_duel_action,
    request_duel_hint,
    respond_duel_proposal,
    roll_dice,
    set_duel_settings,
    submit_exchange,
)
from app.frames.service import apply_blur, ensure_frame
from app.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/duels", tags=["duels"])


class DuelCreateRequest(BaseModel):
    categories: list[Literal["movie", "series", "anime"]] = Field(
        default_factory=lambda: ["movie", "series", "anime"]
    )
    genres: list[str] = Field(default_factory=list)
    library_ids: list[str] | None = None


class DuelJoinRequest(BaseModel):
    code: str = Field(min_length=4, max_length=4, pattern=r"^[0-9]{4}$")


class DuelProposalRequest(BaseModel):
    type: Literal["finish", "cancel"]


class DuelProposalResponse(BaseModel):
    accept: bool


class DuelSettingsRequest(BaseModel):
    exchange_count: int = Field(ge=0, le=5)
    duration_seconds: int = Field(default=600, ge=300, le=3600)


class DuelExchangeRequest(BaseModel):
    frame_ids: list[str] = Field(default_factory=list, max_length=5)


class DuelGuessRequest(BaseModel):
    guess: str = Field(min_length=1, max_length=500)


class DuelHintRequest(BaseModel):
    hint_key: str = Field(min_length=1, max_length=64)


async def _match_for_user(
    db: AsyncSession, match_id: str, user_id: int
) -> tuple[DuelMatch, DuelParticipant]:
    match = await db.get(DuelMatch, match_id)
    if match is None:
        raise AppError("DUEL_NOT_FOUND", "Duel introuvable.", status_code=404)
    participant = (
        await db.execute(
            select(DuelParticipant).where(
                DuelParticipant.match_id == match.id,
                DuelParticipant.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if participant is None:
        raise AppError(
            "DUEL_ACCESS_DENIED", "Vous ne participez pas à ce duel.", status_code=403
        )
    return match, participant


@router.post("", status_code=201)
async def create_duel_route(
    payload: DuelCreateRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await create_duel(
        db,
        session=session,
        config=config,
        categories=payload.categories,
        genres=payload.genres,
        library_ids=payload.library_ids,
    )


@router.post("/join")
async def join_duel_route(
    payload: DuelJoinRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await join_duel(
        db, session=session, code=payload.code, config=config
    )


@router.get("/mine")
async def my_duels(
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return {"duels": await list_my_duels(db, user_id=session.user_id, config=config)}


@router.get("/{match_id}")
async def get_duel(
    match_id: str,
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    match, _participant = await _match_for_user(db, match_id, session.user_id)
    return await duel_state(db, match, session.user_id, config=config)


@router.post("/{match_id}/abandon")
async def abandon_duel_route(
    match_id: str,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await abandon_duel(
        db, match_id=match_id, user_id=session.user_id, config=config
    )


@router.post("/{match_id}/finish")
async def finish_duel_route(
    match_id: str,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await finish_duel_now(
        db, match_id=match_id, user_id=session.user_id, config=config
    )


@router.post("/{match_id}/proposal")
async def propose_duel_action_route(
    match_id: str,
    payload: DuelProposalRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await propose_duel_action(
        db,
        match_id=match_id,
        user_id=session.user_id,
        action=payload.type,
        config=config,
    )


@router.post("/{match_id}/proposal/respond")
async def respond_duel_proposal_route(
    match_id: str,
    payload: DuelProposalResponse,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await respond_duel_proposal(
        db,
        match_id=match_id,
        user_id=session.user_id,
        accept=payload.accept,
        config=config,
    )


@router.post("/{match_id}/roll")
async def roll_duel_dice(
    match_id: str,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await roll_dice(
        db, match_id=match_id, user_id=session.user_id, config=config
    )


@router.post("/{match_id}/settings")
async def duel_settings(
    match_id: str,
    payload: DuelSettingsRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await set_duel_settings(
        db,
        match_id=match_id,
        user_id=session.user_id,
        exchange_count=payload.exchange_count,
        duration_seconds=payload.duration_seconds,
        config=config,
    )


@router.post("/{match_id}/exchange")
async def duel_exchange(
    match_id: str,
    payload: DuelExchangeRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await submit_exchange(
        db,
        match_id=match_id,
        user_id=session.user_id,
        frame_ids=payload.frame_ids,
        config=config,
    )


@router.post("/{match_id}/frames/{frame_id}/guess")
async def duel_guess(
    match_id: str,
    frame_id: str,
    payload: DuelGuessRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await guess_duel_frame(
        db,
        match_id=match_id,
        user_id=session.user_id,
        frame_id=frame_id,
        guess=payload.guess,
        config=config,
    )


@router.post("/{match_id}/frames/{frame_id}/hints")
async def duel_hint(
    match_id: str,
    frame_id: str,
    payload: DuelHintRequest,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await get_or_create_settings(db)
    return await request_duel_hint(
        db,
        match_id=match_id,
        user_id=session.user_id,
        frame_id=frame_id,
        hint_key=payload.hint_key,
        config=config,
    )


@router.get("/{match_id}/frames/{frame_id}")
async def duel_frame_image(
    match_id: str,
    frame_id: str,
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    config = await get_or_create_settings(db)
    match, _participant = await _match_for_user(db, match_id, session.user_id)
    frame = await db.get(DuelFrame, frame_id)
    if frame is None or frame.match_id != match.id:
        raise AppError("DUEL_FRAME_NOT_FOUND", "Frame introuvable.", status_code=404)
    if match.phase == "lobby":
        raise AppError(
            "DUEL_NOT_STARTED",
            "Les frames seront visibles dès que l'adversaire aura rejoint.",
            status_code=409,
        )
    if match.phase in {"exchange", "playing"} and frame.holder_id != session.user_id:
        raise AppError(
            "DUEL_FRAME_ACCESS_DENIED", "Cette frame ne vous appartient pas.", status_code=403
        )
    path = await ensure_frame(db, frame, config, 0)
    clear = (
        match.phase in {"finished", "playing"}
        or (match.phase == "exchange" and frame.holder_id == session.user_id)
    )
    if not clear:
        path = await apply_blur(path, frame.frame_cache_key or frame.id, radius=18)
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "ETag": f'"duel-{frame.id}-{match.phase}-{frame.solved_by_user_id or 0}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
