from datetime import datetime, timedelta, timezone

import pytest

from src.auth import (
    InMemoryTokenStore,
    TokenExpiredError,
    TokenPayload,
    TokenUsageExceededError,
    create_access_token,
    decode_token,
)
from src.user_management import User


@pytest.fixture(autouse=True)
def configure_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")


@pytest.fixture
def user():
    return User(username="alice", password_hash="hash")


def test_create_and_decode_token(user):
    issued_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    token = create_access_token(user, now=issued_at)
    payload = decode_token(token)

    assert isinstance(payload, TokenPayload)
    assert payload.sub == user.username
    assert payload.iat == int(issued_at.timestamp())
    assert payload.exp == int((issued_at + timedelta(hours=10)).timestamp())
    assert payload.jti


def test_token_usage_limit_enforced(user):
    store = InMemoryTokenStore()
    issued_at = datetime.now(timezone.utc)
    payload = decode_token(create_access_token(user, now=issued_at))
    store.register_new_token(payload)

    for _ in range(1000):
        assert store.increment_token_use(payload.jti, now=issued_at)

    with pytest.raises(TokenUsageExceededError):
        store.increment_token_use(payload.jti, now=issued_at)


def test_token_time_expiration(user):
    store = InMemoryTokenStore()
    issued_at = datetime.now(timezone.utc)
    token = create_access_token(user, now=issued_at, expires_delta=timedelta(seconds=2))
    payload = decode_token(token)
    store.register_new_token(payload)

    assert store.increment_token_use(payload.jti, now=issued_at + timedelta(seconds=1))

    with pytest.raises(TokenExpiredError):
        store.increment_token_use(payload.jti, now=issued_at + timedelta(seconds=3))


def test_decode_rejects_expired_token(user):
    issued_at = datetime.now(timezone.utc)
    expired_token = create_access_token(
        user, now=issued_at, expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(TokenExpiredError):
        decode_token(expired_token)
