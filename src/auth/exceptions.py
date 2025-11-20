"""Authentication-specific exception hierarchy."""


class AuthError(Exception):
    """Base class for authentication-related errors."""


class InvalidTokenError(AuthError):
    """Raised when a token cannot be decoded or is malformed."""


class TokenExpiredError(AuthError):
    """Raised when a token has expired based on its timestamp."""


class TokenUsageExceededError(AuthError):
    """Raised when a token has exceeded its permitted usage count."""
