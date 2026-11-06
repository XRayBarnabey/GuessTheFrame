"""Small crypto helpers: encryption at rest, opaque tokens, hashing."""

from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError


def _fernet() -> Fernet:
    settings = get_settings()
    raw = settings.encryption_key
    if not raw or raw == "change-me":
        raise AppError(
            "ENCRYPTION_NOT_CONFIGURED",
            "La clé de chiffrement n'est pas configurée. Lancez scripts/setup.ps1.",
            status_code=500,
        )
    try:
        key = raw.encode("ascii")
        return Fernet(key)
    except (ValueError, UnicodeEncodeError):
        # Accept a passphrase and derive a valid Fernet key from it.
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError(
            "SECRET_DECRYPTION_FAILED",
            "Impossible de déchiffrer un secret. Vérifiez GTF_ENCRYPTION_KEY.",
            status_code=500,
        ) from exc


def new_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
