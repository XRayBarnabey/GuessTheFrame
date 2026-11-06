"""Authentication dependencies and session helpers."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.crypto import hash_token
from app.core.errors import AppError
from app.db.base import utcnow
from app.db.models import AppSettings, User, UserSession
from app.db.session import get_db
from app.services.settings_service import get_or_create_settings, is_setup_complete

settings = get_settings()


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_idle_days * 24 * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


async def get_session_optional(
    request: Request, db: AsyncSession = Depends(get_db)
) -> UserSession | None:
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None

    statement = (
        select(UserSession)
        .options(selectinload(UserSession.user))
        .where(UserSession.token_hash == hash_token(raw))
    )
    session = (await db.execute(statement)).scalar_one_or_none()
    if session is None:
        return None
    now = utcnow()
    if session.revoked_at is not None or session.expires_at <= now:
        return None
    if not session.user.is_active:
        return None

    # Sliding expiration, throttled to avoid a write on every request.
    if (now - session.last_seen_at).total_seconds() > 60:
        session.last_seen_at = now
        absolute_limit = session.created_at + timedelta(
            days=settings.session_absolute_days
        )
        idle_limit = now + timedelta(days=settings.session_idle_days)
        session.expires_at = min(absolute_limit, idle_limit)
        session.user.last_seen_at = now
        await db.commit()

    # Emby accounts can be disabled or deleted after login. Revalidate
    # periodically with the server-side API key; never block on an outage.
    if session.emby_checked_at is None or (
        now - session.emby_checked_at
    ).total_seconds() > 15 * 60:
        config = (
            await db.execute(select(AppSettings).where(AppSettings.id == 1))
        ).scalar_one_or_none()
        if config and config.emby_api_key_enc:
            from app.core.crypto import decrypt_secret
            from app.emby.client import EmbyClient, EmbyError

            api_key = decrypt_secret(config.emby_api_key_enc)
            if api_key:
                try:
                    client = EmbyClient(
                        config.emby_url,
                        token=api_key,
                        verify_tls=config.emby_verify_tls,
                        timeout=8.0,
                    )
                    emby_user = await client.get_user(session.user.emby_user_id)
                    policy = emby_user.get("Policy") or {}
                    if policy.get("IsDisabled"):
                        session.revoked_at = now
                        await db.commit()
                        return None
                    session.emby_checked_at = now
                    await db.commit()
                except EmbyError:
                    # Keep the session alive during a temporary Emby outage.
                    session.emby_checked_at = now
                    await db.commit()

    return session


async def require_session(
    session: UserSession | None = Depends(get_session_optional),
) -> UserSession:
    if session is None:
        raise AppError(
            "AUTH_REQUIRED",
            "Vous devez être connecté pour accéder à cette page.",
            status_code=401,
        )
    return session


async def require_admin(session: UserSession = Depends(require_session)) -> UserSession:
    if not session.user.is_admin:
        raise AppError(
            "ADMIN_REQUIRED",
            "Cette action est réservée aux administrateurs.",
            status_code=403,
        )
    return session


def require_csrf(request: Request, session: UserSession = Depends(require_session)) -> None:
    provided = request.headers.get(settings.csrf_header_name, "")
    if not provided or not secrets.compare_digest(provided, session.csrf_token):
        raise AppError(
            "CSRF_INVALID",
            "Jeton CSRF invalide ou expiré. Rechargez la page.",
            status_code=403,
        )


async def require_setup(
    db: AsyncSession = Depends(get_db),
) -> AppSettings:
    row = await get_or_create_settings(db)
    if not is_setup_complete(row):
        raise AppError(
            "SETUP_REQUIRED",
            "GuessTheFrame n'est pas encore connecté à un serveur Emby.",
            status_code=409,
        )
    return row


def serialize_user(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "emby_user_id": user.emby_user_id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "avatar_url": (
            f"/api/users/me/avatar?v={user.avatar_version}"
            if user.avatar_path
            else None
        ),
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "show_in_leaderboard": user.show_in_leaderboard,
        "last_login_at": user.last_login_at.isoformat() + "Z" if user.last_login_at else None,
    }
