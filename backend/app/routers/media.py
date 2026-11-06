"""Protected media image proxy (posters for finished games only)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_session
from app.core.crypto import decrypt_secret
from app.core.errors import AppError
from app.db.models import Game, MediaItem, UserSession
from app.db.session import get_db
from app.emby.client import EmbyClient
from app.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{media_id}/poster")
async def media_poster(
    media_id: int,
    session: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    accessible = (
        await db.execute(
            select(Game.id)
            .where(
                Game.user_id == session.user_id,
                Game.media_id == media_id,
                Game.status.in_(["won", "abandoned", "expired"]),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    showcase_ids = set(session.user.showcase_media_ids or [])
    if accessible is None and media_id not in showcase_ids and not session.user.is_admin:
        raise AppError(
            "MEDIA_ACCESS_DENIED",
            "Cette image n'est pas accessible.",
            status_code=403,
        )

    media = await db.get(MediaItem, media_id)
    if media is None:
        raise AppError("MEDIA_NOT_FOUND", "Média introuvable.", status_code=404)

    config = await get_or_create_settings(db)
    api_key = decrypt_secret(config.emby_api_key_enc)
    if not api_key:
        raise AppError(
            "EMBY_NOT_CONFIGURED",
            "La clé API Emby n'est pas configurée.",
            status_code=409,
        )

    client = EmbyClient(
        config.emby_url, token=api_key, verify_tls=config.emby_verify_tls
    )

    candidates: list[str] = []
    if media.poster_tag:
        candidates.append(
            client.image_url(
                media.emby_item_id,
                "Primary",
                max_width=600,
                tag=media.poster_tag,
            )
        )
    if media.series_id:
        candidates.append(
            client.image_url(media.series_id, "Primary", max_width=600)
        )
    if not candidates:
        raise AppError("POSTER_NOT_FOUND", "Aucune affiche disponible.", status_code=404)

    async with httpx.AsyncClient(
        verify=config.emby_verify_tls, timeout=20.0, follow_redirects=True
    ) as http:
        for url in candidates:
            try:
                response = await http.get(
                    url, headers={"X-Emby-Token": api_key}
                )
            except httpx.HTTPError:
                continue
            if response.status_code == 200 and response.content:
                content_type = response.headers.get("content-type", "image/jpeg")
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                return Response(
                    content=response.content,
                    media_type=content_type,
                    headers={
                        "Cache-Control": "private, max-age=86400",
                        "X-Content-Type-Options": "nosniff",
                    },
                )

    raise AppError("POSTER_NOT_FOUND", "Aucune affiche disponible.", status_code=404)
