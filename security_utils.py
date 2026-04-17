"""Password hashing helpers using PBKDF2 (no external deps)."""
from __future__ import annotations

import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Return encoded PBKDF2 hash string."""
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded_hash: str | None) -> bool:
    """Validate password against stored hash string."""
    if not encoded_hash:
        return False
    try:
        algorithm, iterations_s, salt_hex, digest_hex = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_s),
        ).hex()
        return hmac.compare_digest(digest, digest_hex)
    except Exception:
        return False
