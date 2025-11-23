import pytest

from src.auth import AuthError, AuthService, InMemoryTokenStore, InvalidTokenError
from src.user_management import InMemoryUserRepository, create_user


@pytest.fixture(autouse=True)
def configure_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")


@pytest.fixture
def auth_service():
    repository = InMemoryUserRepository()
    token_store = InMemoryTokenStore()
    return AuthService(repository, token_store)


def test_login_registers_token(auth_service):
    create_user(auth_service.user_repository, "alice", "strongpass", can_upload=True)

    token, payload = auth_service.login("alice", "strongpass")

    assert token
    assert payload.sub == "alice"
    # Token should be tracked and usable
    assert auth_service.token_store.increment_token_use(payload.jti)


def test_register_requires_admin(auth_service):
    create_user(auth_service.user_repository, "bob", "pw123456")
    non_admin_token, _ = auth_service.login("bob", "pw123456")

    with pytest.raises(AuthError):
        auth_service.register_user(
            admin_token=non_admin_token,
            username="carol",
            password="pw123456",
            can_upload=True,
        )


def test_admin_register_and_logout_revokes_token(auth_service):
    admin_token, _ = auth_service.login("ece30861defaultadminuser", "correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages")

    new_user = auth_service.register_user(
        admin_token=admin_token,
        username="dave",
        password="strongpass",
        can_download=True,
    )

    assert new_user.username == "dave"

    token, payload = auth_service.login("dave", "strongpass")
    auth_service.logout(f"bearer {token}")

    with pytest.raises(InvalidTokenError):
        auth_service.authenticate_token(token)
