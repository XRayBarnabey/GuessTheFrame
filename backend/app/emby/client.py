"""Async Emby REST API client.

Only the endpoints needed by GuessTheFrame are implemented. The client never
leaks the Emby token to the browser: it runs exclusively on the backend.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import get_settings

logger = logging.getLogger("guesstheframe.emby")

APP_CLIENT = "GuessTheFrame"
APP_DEVICE = "Web"
APP_DEVICE_ID = "guesstheframe-server"
APP_VERSION = "0.1.0"

ITEM_FIELDS = ",".join(
    [
        "DateCreated",
        "DateModified",
        "Genres",
        "Overview",
        "People",
        "ProviderIds",
        "MediaSources",
        "MediaStreams",
        "ProductionYear",
        "PremiereDate",
        "RunTimeTicks",
        "OfficialRating",
        "CommunityRating",
        "SortName",
        "Chapters",
        "PrimaryImageAspectRatio",
        "Studios",
        "Taglines",
        "Collections",
        "Tags",
    ]
)


class EmbyError(Exception):
    """Base class for Emby integration errors."""

    code = "EMBY_ERROR"
    user_message = "Une erreur est survenue avec le serveur Emby."

    def __init__(self, message: str | None = None, *, status_code: int | None = None):
        super().__init__(message or self.user_message)
        self.status_code = status_code


class EmbyUnavailable(EmbyError):
    code = "EMBY_UNAVAILABLE"
    user_message = (
        "Le serveur Emby est injoignable. Vérifiez l'adresse, le réseau et que le serveur est démarré."
    )


class EmbyAuthError(EmbyError):
    code = "EMBY_AUTH_FAILED"
    user_message = "Identifiants Emby incorrects ou compte désactivé."


class EmbyForbidden(EmbyError):
    code = "EMBY_FORBIDDEN"
    user_message = "Ce compte Emby n'a pas accès à cette ressource."


class EmbyRequestError(EmbyError):
    code = "EMBY_REQUEST_FAILED"
    user_message = "Le serveur Emby a renvoyé une réponse inattendue."


def normalize_emby_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise EmbyUnavailable("L'adresse du serveur Emby est vide.")
    if not value.lower().startswith(("http://", "https://")):
        value = "http://" + value

    parts = urlsplit(value)
    if not parts.netloc:
        raise EmbyUnavailable("L'adresse du serveur Emby est invalide.")

    path = parts.path.rstrip("/")
    if path.endswith("/emby"):
        path = path[: -len("/emby")]

    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _authorization_header(user_id: str = "") -> str:
    parts = []
    if user_id:
        parts.append(f'UserId="{user_id}"')
    parts.extend(
        [
            f'Client="{APP_CLIENT}"',
            f'Device="{APP_DEVICE}"',
            f'DeviceId="{APP_DEVICE_ID}"',
            f'Version="{APP_VERSION}"',
        ]
    )
    return "Emby " + ", ".join(parts)


class EmbyClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        verify_tls: bool = True,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = normalize_emby_url(base_url)
        self.token = token
        self.verify_tls = verify_tls
        self.timeout = timeout

    @property
    def api_root(self) -> str:
        return f"{self.base_url}/emby"

    def _headers(self, *, auth_user_id: str = "") -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-Emby-Authorization": _authorization_header(auth_user_id),
            "User-Agent": f"{APP_CLIENT}/{APP_VERSION}",
        }
        if self.token:
            headers["X-Emby-Token"] = self.token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        auth_user_id: str = "",
        timeout: float | None = None,
    ) -> Any:
        url = f"{self.api_root}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                verify=self.verify_tls,
                timeout=timeout or self.timeout,
                follow_redirects=True,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=self._headers(auth_user_id=auth_user_id),
                )
        except httpx.TimeoutException as exc:
            logger.warning("Emby timeout on %s %s", method, path)
            raise EmbyUnavailable("Le serveur Emby ne répond pas (délai dépassé).") from exc
        except httpx.HTTPError as exc:
            logger.warning("Emby connection error on %s %s: %s", method, path, exc)
            raise EmbyUnavailable() from exc

        if response.status_code in (401, 403):
            logger.warning("Emby auth error on %s %s: %s", method, path, response.status_code)
            if response.status_code == 403:
                raise EmbyForbidden(status_code=response.status_code)
            raise EmbyAuthError(status_code=response.status_code)
        if response.status_code == 404:
            raise EmbyRequestError(
                f"Ressource Emby introuvable ({path}).",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            logger.warning(
                "Emby error on %s %s: %s %s",
                method,
                path,
                response.status_code,
                response.text[:300],
            )
            raise EmbyRequestError(
                f"Le serveur Emby a répondu {response.status_code}.",
                status_code=response.status_code,
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise EmbyRequestError("Réponse Emby non JSON.") from exc

    # ------------------------------------------------------------------
    # Server / authentication
    # ------------------------------------------------------------------

    async def get_public_info(self) -> dict[str, Any]:
        return await self._request("GET", "System/Info/Public")

    async def get_system_info(self) -> dict[str, Any]:
        return await self._request("GET", "System/Info")

    async def authenticate(self, username: str, password: str) -> dict[str, Any]:
        try:
            payload = await self._request(
                "POST",
                "Users/AuthenticateByName",
                json={"Username": username, "Pw": password},
            )
        except EmbyRequestError as exc:
            if exc.status_code in (400, 401, 403):
                raise EmbyAuthError(
                    "Identifiants Emby incorrects.", status_code=exc.status_code
                ) from exc
            raise
        if not payload or not payload.get("AccessToken"):
            raise EmbyAuthError("Réponse d'authentification Emby invalide.")
        return payload

    async def logout(self, access_token: str) -> None:
        original = self.token
        self.token = access_token
        try:
            await self._request(
                "POST",
                "Sessions/Logout",
                auth_user_id="",
            )
        except EmbyError:
            logger.info("Emby logout failed (token may already be revoked)")
        finally:
            self.token = original

    async def get_user(self, user_id: str) -> dict[str, Any]:
        return await self._request("GET", f"Users/{user_id}")

    # ------------------------------------------------------------------
    # Library / catalogue
    # ------------------------------------------------------------------

    async def get_media_folders(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "Library/MediaFolders")
        return list(payload.get("Items", []) if payload else [])

    async def get_views(self, user_id: str) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"Users/{user_id}/Views",
            params={"IncludeExternalContent": "false"},
            auth_user_id=user_id,
        )
        return list(payload.get("Items", []) if payload else [])

    async def get_items(
        self,
        *,
        parent_id: str | None = None,
        include_item_types: str = "Movie,Episode",
        start_index: int = 0,
        limit: int = 200,
        fields: str = ITEM_FIELDS,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "Recursive": "true",
            "IncludeItemTypes": include_item_types,
            "Fields": fields,
            "EnableImages": "true",
            "EnableUserData": "false",
            "ImageTypeLimit": "1",
            "StartIndex": str(start_index),
            "Limit": str(limit),
            "SortBy": "SortName",
            "SortOrder": "Ascending",
        }
        if parent_id:
            params["ParentId"] = parent_id

        if user_id:
            path = f"Users/{user_id}/Items"
            payload = await self._request(
                "GET", path, params=params, auth_user_id=user_id
            )
        else:
            payload = await self._request("GET", "Items", params=params)
        return payload or {"Items": [], "TotalRecordCount": 0}

    async def get_item(self, item_id: str) -> dict[str, Any]:
        # Some Emby servers reject path-based item lookups (404), so prefer
        # the query-based endpoint which is supported everywhere.
        payload = await self._request(
            "GET",
            "Items",
            params={"Ids": item_id, "Recursive": "true"},
        )
        items = list((payload or {}).get("Items") or [])
        if not items:
            raise EmbyRequestError(
                f"Ressource Emby introuvable (Items/{item_id}).", status_code=404
            )
        return items[0]

    async def get_seasons(self, series_id: str) -> list[dict[str, Any]]:
        payload = await self._request("GET", f"Shows/{series_id}/Seasons")
        return list((payload or {}).get("Items") or [])

    async def get_items_by_ids(self, item_ids: list[str], *, user_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"Users/{user_id}/Items",
            params={
                "Ids": ",".join(item_ids),
                "Fields": "Id,Name,Type",
                "EnableImages": "false",
            },
            auth_user_id=user_id,
        )

    # ------------------------------------------------------------------
    # Images / playback URLs (backend only)
    # ------------------------------------------------------------------

    def image_url(
        self,
        item_id: str,
        image_type: str = "Primary",
        *,
        index: int | None = None,
        max_width: int | None = None,
        tag: str | None = None,
    ) -> str:
        suffix = f"/{index}" if index is not None else ""
        url = f"{self.api_root}/Items/{item_id}/Images/{image_type}{suffix}"
        params = []
        if max_width:
            params.append(f"MaxWidth={max_width}")
        if tag:
            params.append(f"Tag={tag}")
        if params:
            url += "?" + "&".join(params)
        return url

    def stream_url(
        self, item_id: str, media_source_id: str, container: str | None = None
    ) -> str:
        url = (
            f"{self.api_root}/Videos/{item_id}/stream"
            f"?Static=true&MediaSourceId={media_source_id}"
        )
        if container:
            url += f"&Container={container}"
        return url

    def web_item_url(self, item_id: str, server_id: str) -> str:
        return (
            f"{self.base_url}/web/index.html#!/item"
            f"?id={item_id}&serverId={server_id}"
        )

    def headers_for_stream(self, token: str | None = None) -> dict[str, str]:
        value = token or self.token
        return {"X-Emby-Token": value} if value else {}


def client_from_settings(*, token: str | None = None, base_url: str | None = None,
                         verify_tls: bool | None = None) -> EmbyClient:
    settings = get_settings()
    return EmbyClient(
        base_url or settings.emby_url,
        token=token,
        verify_tls=settings.emby_verify_tls if verify_tls is None else verify_tls,
    )
