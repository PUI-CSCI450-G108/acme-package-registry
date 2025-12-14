"""High-level authentication workflows used by Lambda handlers."""

import logging
import os
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
from src.s3_user_repository import S3UserRepository

logger = logging.getLogger(__name__)


def _normalize_token(raw_token: str) -> str:
    """Accept headers with or without 'bearer ' prefix."""
    token = raw_token.strip()
    if token.lower().startswith("bearer "):
        return token[7:]
    return token


class AuthService:
    """Encapsulates user login, registration, and token revocation logic."""

    def __init__(self, user_repository: UserRepository, token_store: TokenStore):
        self.user_repository = user_repository
        self.token_store = token_store

        # Ensure the default admin exists in whatever backing store we're using
        initialize_default_admin(self.user_repository)

    # ----------------------------------------------------------------------
    # TOKEN AUTH
    # ----------------------------------------------------------------------
    def authenticate_token(self, token: str) -> Tuple[TokenPayload, object]:
        """Validates token, loads the user from the repository."""
        normalized = _normalize_token(token)
        payload = decode_token(normalized)

        # record token usage
        self.token_store.increment_token_use(payload.jti)

        # Load user from repository
        user = get_user_by_username(self.user_repository, payload.sub)
        if not user:
            logger.info("Token subject %s not found", payload.sub)
            raise AuthError("User not found")

        return payload, user

    # ----------------------------------------------------------------------
    # LOGIN
    # ----------------------------------------------------------------------
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

    # ----------------------------------------------------------------------
    # REGISTER NEW USER — ADMIN ONLY
    # ----------------------------------------------------------------------
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

        token_is_admin = bool(getattr(payload, "is_admin", False))

        # Check both the token claim and the repository record so admins are
        # recognized even if their token was issued without the is_admin flag
        # (e.g., older tokens) or if the repository is not in-memory.
        repo_is_admin = bool(getattr(admin_user, "is_admin", False))

        # ONLY admins may register users: accept if EITHER source says admin
        if not (token_is_admin or repo_is_admin):
            logger.info(
                "Admin check failed for token subject '%s' "
                "(token_is_admin=%s, repo_is_admin=%s)",
                payload.sub,
                token_is_admin,
                repo_is_admin,
            )
            raise AuthError("Admin privileges required")

        # Admins always inherit full permissions for newly created admins
        if is_admin:
            can_upload = True
            can_search = True
            can_download = True

        # Persist to repository (S3 or in-memory)
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
            "Admin '%s' (jti=%s) registered user '%s'",
            admin_user.username,
            payload.jti,
            username,
        )

        return user

    # ----------------------------------------------------------------------
    # LOGOUT
    # ----------------------------------------------------------------------
    def logout(self, token: str) -> TokenPayload:
        normalized = _normalize_token(token)
        payload = decode_token(normalized)

        self.token_store.revoke_token(payload.jti)
        logger.info("Revoked token %s for user '%s'", payload.jti, payload.sub)
        return payload


# ----------------------------------------------------------------------
# DEFAULT FACTORY FUNCTION
# ----------------------------------------------------------------------
_default_user_repository: Optional[UserRepository] = None
_default_token_store: Optional[TokenStore] = None
_default_auth_service: Optional[AuthService] = None


def get_default_auth_service() -> AuthService:
    """
    Create a SINGLE global AuthService instance per process.

    - In Lambda with USER_DB_BUCKET/USER_DB_KEY set => uses S3UserRepository
    - In tests/local where those env vars are absent => uses InMemoryUserRepository
    """
    global _default_auth_service, _default_user_repository, _default_token_store

    if _default_auth_service is None:
        bucket = os.environ.get("USER_DB_BUCKET")
        key = os.environ.get("USER_DB_KEY")

        if bucket and key:
            repo: UserRepository = S3UserRepository(bucket=bucket, key=key)
        else:
            repo = InMemoryUserRepository()

        _default_user_repository = repo
        _default_token_store = InMemoryTokenStore()
        _default_auth_service = AuthService(_default_user_repository, _default_token_store)

    return _default_auth_service
