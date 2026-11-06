"""Authentication service: Emby login, user upsert, session creation."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    clear_session_cookie,
    set_session_cookie,
    settings,
)
from app.core.crypto import encrypt_secret, hash_token, new_opaque_token
from app.core.errors import AppError
from app.db.base import utcnow
from app.db.models import AppSettings, User, UserSession
from app.emby.client import EmbyAuthError, EmbyClient, EmbyError


def _policy(auth_payload: dict[str, Any]) -> dict[str, Any]:
    user = auth_payload.get("User") or {}
    policy = user.get("Policy") or {}
    return policy if isinstance(policy, dict) else {}


async def upsert_emby_user(
    db: AsyncSession,
    auth_payload: dict[str, Any],
    *,
    server_id: str,
    admin_usernames: set[str],
) -> User:
    user_data = auth_payload.get("User") or {}
    emby_user_id = user_data.get("Id")
    username = user_data.get("Name")
    if not emby_user_id or not username:
        raise EmbyAuthError("Réponse d'authentification Emby incomplète.")

    policy = _policy(auth_payload)
    if policy.get("IsDisabled"):
        raise EmbyAuthError("Ce compte Emby est désactivé.")

    username_norm = username.casefold()
    statement = select(User).where(
        User.emby_server_id == server_id,
        User.emby_user_id == emby_user_id,
    )
    user = (await db.execute(statement)).scalar_one_or_none()

    is_admin = username_norm in admin_usernames
    if not admin_usernames and bool(policy.get("IsAdministrator")):
        is_admin = True

    if user is None:
        user = User(
            emby_user_id=emby_user_id,
            emby_server_id=server_id,
            username=username,
            username_norm=username_norm,
            is_admin=is_admin,
            is_active=True,
        )
        db.add(user)
        await db.flush()
    else:
        user.username = username
        user.username_norm = username_norm
        user.is_active = True
        user.is_admin = user.is_admin or is_admin

    user.last_login_at = utcnow()
    user.last_seen_at = utcnow()
    return user


async def create_user_session(
    db: AsyncSession,
    *,
    user: User,
    emby_access_token: str,
    request: Request,
) -> tuple[UserSession, str]:
    raw_token = new_opaque_token()
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=new_opaque_token(24),
        emby_token_enc=encrypt_secret(emby_access_token),
        created_at=now,
        last_seen_at=now,
        emby_checked_at=now,
        expires_at=now + timedelta(days=settings.session_idle_days),
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, raw_token


async def revoke_session(
    db: AsyncSession, session: UserSession, *, call_emby: bool = True
) -> None:
    if session.revoked_at is not None:
        return
    session.revoked_at = utcnow()
    await db.commit()

    if call_emby and session.emby_token_enc:
        from app.core.crypto import decrypt_secret

        token = decrypt_secret(session.emby_token_enc)
        if token:
            # Best effort; the token may already be expired.
            try:
                settings_row = (
                    await db.execute(select(AppSettings).where(AppSettings.id == 1))
                ).scalar_one_or_none()
                if settings_row:
                    client = EmbyClient(
                        settings_row.emby_url,
                        token=token,
                        verify_tls=settings_row.emby_verify_tls,
                    )
                    await client.logout(token)
            except EmbyError:
                pass


async def revoke_session_by_cookie(
    db: AsyncSession, raw_cookie: str | None
) -> None:
    if not raw_cookie:
        return
    statement = select(UserSession).where(
        UserSession.token_hash == hash_token(raw_cookie)
    )
    session = (await db.execute(statement)).scalar_one_or_none()
    if session:
        await revoke_session(db, session)


def login_error(exc: EmbyError) -> AppError:
    if isinstance(exc, EmbyAuthError):
        return AppError("EMBY_AUTH_FAILED", exc.user_message, status_code=401)
    return AppError(
        exc.code,
        exc.user_message,
        status_code=502 if exc.code == "EMBY_UNAVAILABLE" else 502,
    )


def response_for_login(response: Response, raw_token: str) -> None:
    set_session_cookie(response, raw_token)


def response_for_logout(response: Response) -> None:
    clear_session_cookie(response)
