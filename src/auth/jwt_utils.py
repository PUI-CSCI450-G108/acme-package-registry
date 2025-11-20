"""Utility functions for issuing and validating JWT access tokens."""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError as PyJWTInvalidTokenError
from pydantic import BaseModel, ValidationError

from .exceptions import AuthError, InvalidTokenError, TokenExpiredError
from src.user_management import User

logger = logging.getLogger(__name__)

DEFAULT_EXPIRATION = timedelta(hours=10)


def _get_jwt_configuration() -> Tuple[str, str]:
    secret = os.environ.get("JWT_SECRET")
    algorithm = os.environ.get("JWT_ALGORITHM")
    if not secret:
        raise AuthError("JWT_SECRET environment variable is not set")
    if not algorithm:
        raise AuthError("JWT_ALGORITHM environment variable is not set")
    return secret, algorithm


class TokenPayload(BaseModel):
    """Structured representation of the JWT payload."""

    sub: str
    iat: int
    exp: int
    jti: str
    is_admin: bool = False
    can_upload: bool = False
    can_search: bool = False
    can_download: bool = False

    @property
    def issued_at(self) -> datetime:
        return datetime.fromtimestamp(self.iat, tz=timezone.utc)

    @property
    def expires_at(self) -> datetime:
        return datetime.fromtimestamp(self.exp, tz=timezone.utc)


def create_access_token(
    user: User,
    *,
    now: Optional[datetime] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT for the given user.

    Args:
        user: The user object (must have a ``username`` attribute).
        now: Optional datetime to use as the issuance time (primarily for testing).
        expires_delta: Optional override for token lifetime.

    Returns:
        Encoded JWT string.

    Raises:
        AuthError: If required JWT configuration is missing.
    """

    issued_at = now or datetime.now(timezone.utc)
    expiration_delta = expires_delta or DEFAULT_EXPIRATION
    issued_at_seconds = int(issued_at.timestamp())
    expiration_seconds = int((issued_at + expiration_delta).timestamp())

    secret, algorithm = _get_jwt_configuration()
    payload = {
        "sub": user.username,
        "iat": issued_at_seconds,
        "exp": expiration_seconds,
        "jti": str(uuid.uuid4()),
        "is_admin": user.is_admin,
        "can_upload": user.can_upload,
        "can_search": user.can_search,
        "can_download": user.can_download,
    }

    logger.info("Issuing access token for user '%s'", user.username)
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT string.

    Args:
        token: Encoded JWT token string.

    Returns:
        Validated ``TokenPayload`` instance.

    Raises:
        InvalidTokenError: If the token cannot be decoded or is malformed.
        TokenExpiredError: If the token has expired.
        AuthError: If JWT configuration is missing.
    """

    secret, algorithm = _get_jwt_configuration()

    try:
        raw_payload = jwt.decode(token, secret, algorithms=[algorithm])
    except ExpiredSignatureError as exc:
        logger.info("Token has expired")
        raise TokenExpiredError("Token has expired") from exc
    except PyJWTInvalidTokenError as exc:
        logger.info("Invalid token encountered")
        raise InvalidTokenError("Invalid token") from exc

    try:
        return TokenPayload(**raw_payload)
    except ValidationError as exc:
        logger.info("Decoded token payload failed validation")
        raise InvalidTokenError("Token payload is invalid") from exc
