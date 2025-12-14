import pytest

from src.auth import AuthError, AuthService, InMemoryTokenStore, InvalidTokenError
from src.user_management import InMemoryUserRepository, UserRepository, create_user


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
    admin_token, _ = auth_service.login("ece30861defaultadminuser", "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE artifacts;")

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


class FakeRepo(UserRepository):
    """A minimal repository to simulate non-in-memory backends."""

    def __init__(self, user):
        self._user = user
        self._users = {user.username: user}

    def add_user(self, user):
        if user.username in self._users:
            raise ValueError("User already exists")
        self._users[user.username] = user

    def get_user(self, username):
        return self._users.get(username)

    def delete_user(self, username):
        return bool(self._users.pop(username, None))


def test_repo_admin_tokens_without_admin_claim(monkeypatch):
    # Build a fake repository that reports admin privileges but is not
    # InMemoryUserRepository, mirroring S3-backed storage.
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")

    real_repo = InMemoryUserRepository()
    token_store = InMemoryTokenStore()
    service = AuthService(real_repo, token_store)

    admin = service.user_repository.get_user("ece30861defaultadminuser")

    # Issue a token that omits the admin claim to mimic older tokens.
    admin.is_admin = False
    token, _ = service.login("ece30861defaultadminuser", "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE artifacts;")
    admin.is_admin = True

    # Swap in a non-in-memory repository that still knows the admin is an admin.
    service.user_repository = FakeRepo(admin)

    created = service.register_user(
        admin_token=token,
        username="repo-admin-register",
        password="strongpass",
    )

    assert created.username == "repo-admin-register"
