import json
from types import SimpleNamespace

import pytest

from lambda_handlers.auth_register import handler
from src.auth.exceptions import AuthError, InvalidTokenError


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """Ensure the default auth service singleton does not leak between tests."""
    monkeypatch.setattr("src.auth.service._default_auth_service", None)
    monkeypatch.setattr("src.auth.service._default_user_repository", None)
    monkeypatch.setattr("src.auth.service._default_token_store", None)


@pytest.fixture
def registration_body():
    return {
        "user": {"name": "new_user", "is_admin": False},
        "secret": {"password": "pw123456"},
        "permissions": {"can_upload": True, "can_download": False, "can_search": True},
    }


def test_register_user_success(monkeypatch, registration_body):
    captured = {}

    def fake_register_user(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            username=kwargs["username"],
            is_admin=kwargs.get("is_admin", False),
            can_upload=kwargs.get("can_upload", False),
            can_search=kwargs.get("can_search", False),
            can_download=kwargs.get("can_download", False),
        )

    monkeypatch.setattr(
        "lambda_handlers.auth_register.get_default_auth_service",
        lambda: SimpleNamespace(register_user=fake_register_user),
    )

    event = {"headers": {"X-Authorization": "token-123"}, "body": json.dumps(registration_body)}

    response = handler(event, None)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body == {
        "username": "new_user",
        "is_admin": False,
        "can_upload": True,
        "can_search": True,
        "can_download": False,
    }
    assert captured == {
        "admin_token": "token-123",
        "username": "new_user",
        "password": "pw123456",
        "can_upload": True,
        "can_search": True,
        "can_download": False,
        "is_admin": False,
    }


def test_register_user_forbidden(monkeypatch, registration_body):
    def fake_register_user(**_kwargs):
        raise AuthError("Admin privileges required")

    monkeypatch.setattr(
        "lambda_handlers.auth_register.get_default_auth_service",
        lambda: SimpleNamespace(register_user=fake_register_user),
    )

    event = {"headers": {"X-Authorization": "token-123"}, "body": json.dumps(registration_body)}

    response = handler(event, None)

    assert response["statusCode"] == 403
    assert json.loads(response["body"]) == {"error": "Admin privileges required."}


def test_register_user_invalid_token(monkeypatch, registration_body):
    def fake_register_user(**_kwargs):
        raise InvalidTokenError("token expired")

    monkeypatch.setattr(
        "lambda_handlers.auth_register.get_default_auth_service",
        lambda: SimpleNamespace(register_user=fake_register_user),
    )

    event = {"headers": {"X-Authorization": "token-123"}, "body": json.dumps(registration_body)}

    response = handler(event, None)

    assert response["statusCode"] == 401
    assert json.loads(response["body"]) == {"error": "Invalid token."}
