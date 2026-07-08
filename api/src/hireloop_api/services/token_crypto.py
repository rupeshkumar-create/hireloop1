"""
Application-level encryption for sensitive integration tokens at rest.

Gmail OAuth access/refresh tokens (gmail.send scope) were stored in plaintext
columns — a DB read (SQL injection, backup leak, over-broad service key) meant
the ability to send email as any candidate. These helpers encrypt them with
Fernet (AES-128-CBC + HMAC) so the database alone is no longer sufficient.

The key is derived from SECRET_KEY (already a required strong prod secret) so
no new env var is needed and encryption is always on. Reads are dual-mode: a
value that fails to decrypt is treated as a legacy plaintext token, so the
migration needs no backfill and cannot break existing connections.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    from hireloop_api.config import get_settings

    secret = (get_settings().secret_key or "change-me").encode("utf-8")
    # Fernet needs a 32-byte urlsafe-base64 key; derive deterministically.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_token(plaintext: str | None) -> str | None:
    """Encrypt a token for storage. None/empty passes through unchanged."""
    if not plaintext:
        return plaintext
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(stored: str | None) -> str | None:
    """Decrypt a stored token. Legacy plaintext values are returned as-is."""
    if not stored:
        return stored
    try:
        return _fernet().decrypt(stored.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Pre-encryption row (or key rotation) — treat as plaintext.
        return stored
