import base64
import binascii
import hashlib
import hmac
import logging
import os
import secrets
from abc import ABC, abstractmethod
from typing import Dict, Optional

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class User(BaseModel):
    """User domain model with hashed password and permission flags."""

    username: str
    password_hash: str
    can_upload: bool = False
    can_search: bool = False
    can_download: bool = False
    is_admin: bool = False


class UserRepository(ABC):
    """Abstraction for user persistence so storage can be swapped later."""

    @abstractmethod
    def add_user(self, user: User) -> None:
        """Add a user to the repository.

        Args:
            user: The user to add.

        Raises:
            ValueError: If a user with the same username already exists.
        """
        raise NotImplementedError

    @abstractmethod
    def get_user(self, username: str) -> Optional[User]:
        """Retrieve a user by username.

        Args:
            username: The username of the user to retrieve.

        Returns:
            The User object if found, otherwise None.
        """
        raise NotImplementedError

    @abstractmethod
    def delete_user(self, username: str) -> bool:
        ...

    @abstractmethod
    def get_user(self, username: str) -> Optional[User]:
        ...

    @abstractmethod
    def delete_user(self, username: str) -> bool:
        ...


class InMemoryUserRepository(UserRepository):
    """Simple repository that keeps user data in process memory."""

    def __init__(self) -> None:
        self._users: Dict[str, User] = {}

    def add_user(self, user: User) -> None:
        if user.username in self._users:
            raise ValueError(f"User '{user.username}' already exists")
        self._users[user.username] = user

    def get_user(self, username: str) -> Optional[User]:
        return self._users.get(username)

    def delete_user(self, username: str) -> bool:
        return self._users.pop(username, None) is not None


def _hash_password(plain_password: str) -> str:
    """Hash a password using PBKDF2 with a random salt."""

    if not isinstance(plain_password, str):
        raise ValueError("Password must be a string")
    if not plain_password:
        raise ValueError("Password cannot be empty")
    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    try:
        password_bytes = plain_password.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Password contains invalid characters and cannot be encoded as UTF-8")

    salt = secrets.token_bytes(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256", password_bytes, salt, 100_000
    )
    combined = salt + derived_key
    return base64.b64encode(combined).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Validate a password against a stored PBKDF2 hash."""

    try:
        decoded = base64.b64decode(password_hash.encode("utf-8"))
    except (binascii.Error, ValueError):
        logger.warning("Invalid password hash encountered during verification")
        return False

    salt, stored_key = decoded[:16], decoded[16:]
    new_key = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode("utf-8"), salt, 100_000
    )
    return hmac.compare_digest(stored_key, new_key)


def create_user(
    repository: UserRepository,
    username: str,
    plain_password: str,
    *,
    can_upload: bool = False,
    can_search: bool = False,
    can_download: bool = False,
    is_admin: bool = False,
) -> User:
    """Create and persist a new user, ensuring unique username and hashed password."""

    if repository.get_user(username):
        raise ValueError(f"User '{username}' already exists")

    password_hash = _hash_password(plain_password)
    user = User(
        username=username,
        password_hash=password_hash,
        can_upload=can_upload,
        can_search=can_search,
        can_download=can_download,
        is_admin=is_admin,
    )
    repository.add_user(user)
    logger.info("Created user '%s'", username)
    return user


def get_user_by_username(repository: UserRepository, username: str) -> Optional[User]:
    """Convenience wrapper around repository user lookup."""

    return repository.get_user(username)


def delete_user(repository: UserRepository, username: str) -> bool:
    """Delete a user by username; returns True if a user was removed."""

    return repository.delete_user(username)


DEFAULT_ADMIN_USERNAME = "ece30861defaultadminuser"
DEFAULT_ADMIN_PASSWORD = os.environ.get(
    "DEFAULT_ADMIN_PASSWORD",
    "correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages",
)


def initialize_default_admin(repository: UserRepository) -> User:
    """Create the default admin user if it does not already exist."""

    existing_user = repository.get_user(DEFAULT_ADMIN_USERNAME)
    if existing_user:
        return existing_user

    return create_user(
        repository,
        DEFAULT_ADMIN_USERNAME,
        DEFAULT_ADMIN_PASSWORD,
        can_upload=True,
        can_search=True,
        can_download=True,
        is_admin=True,
    )
