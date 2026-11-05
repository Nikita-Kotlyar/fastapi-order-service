from __future__ import annotations

import hashlib
import hmac
import secrets

from app.config import settings

ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str, *, salt: str | None = None) -> str:
    """Hash a password with PBKDF2-SHA256 and a per-user random salt."""

    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    salt = salt or secrets.token_hex(16)
    iterations = settings.pbkdf2_iterations
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    )
    return f"{ALGORITHM}${iterations}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(digest.hex(), expected)
