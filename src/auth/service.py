"""High-level authentication workflows used by Lambda handlers."""

import logging
from typing import Optional, Tuple

from src.auth.exceptions import AuthError
from src.auth.jwt_utils import TokenPayload, create_access_token, decode_token
from src.auth.token_store import InMemoryTokenStore, TokenStore
from src.user_management import (
    InMemoryUserRepository,
    UserRepository,
    create_user,
    get_user_by_username,
    initialize_default_admin,
    verify_password,
)

logger = logging.getLogger(__name__)


def _normalize_token(raw_token: str) -> str:
    # Accept headers with or without "bearer" prefix while keeping payload unchanged.
    token = raw_token.strip()
    if token.lower().startswith("bearer "):
        return token[7:]
    return token


class AuthService:
    """Encapsulates user login, registration, and token revocation logic."""

    def __init__(self, user_repository: UserRepository, token_store: TokenStore):
        self.user_repository = user_repository
        self.token_store = token_store
        initialize_default_admin(self.user_repository)

    def authenticate_token(self, token: str) -> Tuple[TokenPayload, object]:
        normalized = _normalize_token(token)
        payload = decode_token(normalized)
        self.token_store.increment_token_use(payload.jti)
        user = get_user_by_username(self.user_repository, payload.sub)
        if not user:
            logger.info("Token subject %s not found", payload.sub)
            raise AuthError("User not found")
        return payload, user

    def login(self, username: str, password: str) -> Tuple[str, TokenPayload]:
        user = get_user_by_username(self.user_repository, username)
        if not user or not verify_password(password, user.password_hash):
            logger.info("Failed login attempt for user '%s'", username)
            raise AuthError("Invalid username or password")

        token = create_access_token(user)
        payload = decode_token(token)
        self.token_store.register_new_token(payload)
        logger.info("Issued token %s for user '%s'", payload.jti, username)
        return token, payload

    def register_user(
        self,
        *,
        admin_token: str,
        username: str,
        password: str,
        can_upload: bool = False,
        can_search: bool = False,
        can_download: bool = False,
        is_admin: bool = False,
    ):
        payload, admin_user = self.authenticate_token(admin_token)
        if not admin_user.is_admin:
            logger.info("User '%s' attempted admin-only registration", admin_user.username)
            raise AuthError("Admin privileges required")

        # Admins automatically receive all permissions
        if is_admin:
            can_upload = True
            can_search = True
            can_download = True

        user = create_user(
            self.user_repository,
            username,
            password,
            can_upload=can_upload,
            can_search=can_search,
            can_download=can_download,
            is_admin=is_admin,
        )
        logger.info(
            "Admin '%s' (jti=%s) registered user '%s'", admin_user.username, payload.jti, username
        )
        return user

    def logout(self, token: str) -> TokenPayload:
        normalized = _normalize_token(token)
        payload = decode_token(normalized)
        self.token_store.revoke_token(payload.jti)
        logger.info("Revoked token %s for user '%s'", payload.jti, payload.sub)
        return payload


_default_user_repository: Optional[UserRepository] = None
_default_token_store: Optional[TokenStore] = None
_default_auth_service: Optional[AuthService] = None


def get_default_auth_service() -> AuthService:
    global _default_auth_service, _default_token_store, _default_user_repository
    if _default_auth_service is None:
        _default_user_repository = InMemoryUserRepository()
        _default_token_store = InMemoryTokenStore()
        _default_auth_service = AuthService(_default_user_repository, _default_token_store)
    return _default_auth_service
