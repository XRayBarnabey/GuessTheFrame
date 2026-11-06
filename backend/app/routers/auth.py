"""Authentication routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_session_optional,
    require_csrf,
    require_session,
    serialize_user,
    settings,
)
from app.auth.service import (
    create_user_session,
    login_error,
    response_for_login,
    response_for_logout,
    revoke_session,
    upsert_emby_user,
)
from app.core.crypto import decrypt_secret
from app.core.errors import AppError
from app.core.rate_limit import login_limiter
from app.db.models import UserSession
from app.db.session import get_db
from app.emby.client import EmbyClient, EmbyError
from app.services.settings_service import get_or_create_settings, is_setup_complete

logger = logging.getLogger("guesstheframe.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=0, max_length=1024)


class AuthUser(BaseModel):
    id: int
    emby_user_id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    is_admin: bool
    is_active: bool
    show_in_leaderboard: bool = True
    last_login_at: str | None = None


class LoginResponse(BaseModel):
    user: AuthUser
    csrf_token: str


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    rate_key = f"{(request.client.host if request.client else 'unknown')}:{payload.username.casefold()}"
    await login_limiter.hit(rate_key)

    config = await get_or_create_settings(db)
    if not is_setup_complete(config):
        raise AppError(
            "SETUP_REQUIRED",
            "Le serveur Emby n'est pas encore configuré.",
            status_code=409,
        )

    client = EmbyClient(
        config.emby_url,
        verify_tls=config.emby_verify_tls,
        timeout=15.0,
    )
    try:
        auth_payload = await client.authenticate(payload.username, payload.password)
    except EmbyError as exc:
        logger.info("Emby login failed for %s: %s", payload.username, exc.code)
        raise login_error(exc) from exc

    server_id = str(auth_payload.get("ServerId") or config.emby_server_id or "")
    if not server_id:
        raise AppError(
            "EMBY_SERVER_ID_MISSING",
            "Le serveur Emby n'a pas fourni son identifiant.",
            status_code=502,
        )

    user = await upsert_emby_user(
        db,
        auth_payload,
        server_id=server_id,
        admin_usernames=settings.admin_usernames,
    )

    # If a previous session cookie exists, revoke it before creating a new one.
    previous = request.cookies.get(settings.session_cookie_name)
    if previous:
        from app.core.crypto import hash_token
        from app.db.models import UserSession as SessionModel

        old = (
            await db.execute(
                select(SessionModel).where(SessionModel.token_hash == hash_token(previous))
            )
        ).scalar_one_or_none()
        if old and old.revoked_at is None:
            await revoke_session(db, old, call_emby=False)

    session, raw_token = await create_user_session(
        db,
        user=user,
        emby_access_token=str(auth_payload["AccessToken"]),
        request=request,
    )
    await login_limiter.reset(rate_key)
    response_for_login(response, raw_token)
    logger.info("User %s logged in", user.username)

    return LoginResponse(
        user=AuthUser(**serialize_user(user)),
        csrf_token=session.csrf_token,
    )


@router.get("/me", response_model=LoginResponse)
async def me(
    session: UserSession = Depends(require_session),
) -> LoginResponse:
    return LoginResponse(
        user=AuthUser(**serialize_user(session.user)),
        csrf_token=session.csrf_token,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: UserSession = Depends(require_session),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    await revoke_session(db, session)
    response_for_logout(response)
    logger.info("User %s logged out", session.user.username)
    return {"ok": True}
