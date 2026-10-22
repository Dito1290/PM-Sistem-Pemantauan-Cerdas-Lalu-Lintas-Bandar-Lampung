"""bcrypt password hashing."""
from __future__ import annotations

import bcrypt

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # bcrypt ignores anything beyond 72 bytes; reject instead.

# Used to keep login timing similar whether or not the username exists.
_DUMMY_HASH = bcrypt.hashpw(b"citysight-dummy-password", bcrypt.gensalt()).decode()


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password minimal {MIN_PASSWORD_LENGTH} karakter.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password maksimal {MAX_PASSWORD_BYTES} byte.")
    if password.isdigit() or password.isalpha():
        raise ValueError("Password harus memadukan huruf dan angka/simbol.")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    from flask import current_app, has_app_context

    rounds = current_app.config.get("BCRYPT_ROUNDS", 12) if has_app_context() else 12
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    target = (password_hash or _DUMMY_HASH).encode()
    try:
        matched = bcrypt.checkpw(candidate, target)
    except ValueError:
        return False
    return matched and password_hash is not None
