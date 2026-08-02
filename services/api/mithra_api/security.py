"""Password hashing and session tokens.

Argon2id for passwords: it is the current recommendation, it is memory-hard, and
the library refuses to let a caller pick unsafe parameters, which matters more
than tuning here.

Sessions are opaque random tokens stored server-side rather than signed claims
in a cookie. A JWT cannot be revoked without keeping the same server-side list
that a plain token needs anyway, and this way logging out actually ends the
session. Only the token's hash is stored, so a database dump does not hand over
live sessions.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()

SESSION_TTL = timedelta(days=14)
SESSION_COOKIE = "mithra_session"

MIN_PASSWORD_LENGTH = 10


class WeakPassword(ValueError):
    """The password does not meet the minimum policy."""


def check_password_policy(password: str) -> None:
    """Length only.

    Composition rules (a digit, a symbol, mixed case) push people towards
    predictable substitutions and measurably weaker passwords; length is the
    property that actually resists guessing.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )


def hash_password(password: str) -> str:
    check_password_policy(password)
    return _hasher.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash predates the current parameters."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


def new_session_token() -> str:
    """The value handed to the client. Never stored."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """What is stored.

    A plain SHA-256 rather than Argon2: the token already has 256 bits of
    entropy, so there is nothing to brute-force, and session lookup happens on
    every request where a memory-hard hash would be a denial-of-service vector
    against ourselves.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def session_expiry(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + SESSION_TTL
