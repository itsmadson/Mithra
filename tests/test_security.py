import pytest

from mithra_api.security import (
    MIN_PASSWORD_LENGTH,
    WeakPassword,
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    session_expiry,
    verify_password,
)


def test_a_password_verifies_against_its_hash():
    hashed = hash_password("correct horse battery")
    assert verify_password(hashed, "correct horse battery")


def test_a_wrong_password_does_not_verify():
    hashed = hash_password("correct horse battery")
    assert not verify_password(hashed, "correct horse batteries")


def test_the_hash_never_contains_the_password():
    assert "correct horse battery" not in hash_password("correct horse battery")


def test_the_same_password_hashes_differently_each_time():
    """Per-hash salt: two accounts with one password must not look identical."""
    assert hash_password("correct horse battery") != hash_password("correct horse battery")


def test_short_passwords_are_rejected():
    with pytest.raises(WeakPassword):
        hash_password("x" * (MIN_PASSWORD_LENGTH - 1))


def test_a_password_of_exactly_the_minimum_is_accepted():
    assert hash_password("x" * MIN_PASSWORD_LENGTH)


def test_garbage_in_the_hash_column_fails_closed():
    """A corrupted or truncated hash must deny, not raise."""
    assert not verify_password("not-a-hash", "anything")
    assert needs_rehash("not-a-hash")


def test_session_tokens_are_unique_and_long():
    tokens = {new_session_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(t) >= 32 for t in tokens)


def test_the_stored_session_hash_is_not_the_token():
    token = new_session_token()
    stored = hash_session_token(token)
    assert stored != token
    assert token not in stored


def test_hashing_a_session_token_is_deterministic():
    """Lookup depends on it: the same token must always find the same row."""
    token = new_session_token()
    assert hash_session_token(token) == hash_session_token(token)


def test_sessions_expire_in_the_future():
    from datetime import UTC, datetime

    assert session_expiry() > datetime.now(UTC)
