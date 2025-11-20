"""Token usage tracking with a swappable backend."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from .exceptions import InvalidTokenError, TokenExpiredError, TokenUsageExceededError
from .jwt_utils import TokenPayload

logger = logging.getLogger(__name__)

MAX_TOKEN_USES = 1000


@dataclass
class TokenRecord:
    username: str
    issued_at: datetime
    expires_at: datetime
    jti: str
    use_count: int = 0
    max_uses: int = MAX_TOKEN_USES


class TokenStore(ABC):
    """Abstract base class describing token tracking operations."""

    @abstractmethod
    def register_new_token(self, payload: TokenPayload) -> None:
        """Persist a new token entry."""

    @abstractmethod
    def increment_token_use(
        self, jti: str, *, now: Optional[datetime] = None
    ) -> bool:
        """Increment token usage and return whether the token is still valid."""


class InMemoryTokenStore(TokenStore):
    """In-memory token tracking implementation."""

    def __init__(self) -> None:
        self._tokens: Dict[str, TokenRecord] = {}

    def register_new_token(self, payload: TokenPayload) -> None:
        record = TokenRecord(
            username=payload.sub,
            issued_at=payload.issued_at,
            expires_at=payload.expires_at,
            jti=payload.jti,
        )
        logger.info(
            "Registering token %s for user '%s' with expiry at %s",
            payload.jti,
            payload.sub,
            payload.expires_at.isoformat(),
        )
        self._tokens[payload.jti] = record

    def increment_token_use(
        self, jti: str, *, now: Optional[datetime] = None
    ) -> bool:
        record = self._tokens.get(jti)
        if not record:
            logger.info("Token id %s not found during usage increment", jti)
            raise InvalidTokenError("Unknown token identifier")

        current_time = now or datetime.now(timezone.utc)
        if current_time >= record.expires_at:
            logger.info(
                "Token %s has expired at %s", jti, record.expires_at.isoformat()
            )
            raise TokenExpiredError("Token has expired")

        record.use_count += 1
        if record.use_count > record.max_uses:
            logger.info("Token %s exceeded max uses (%s)", jti, record.max_uses)
            raise TokenUsageExceededError("Token usage limit exceeded")

        return True
