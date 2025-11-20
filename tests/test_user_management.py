import pytest

from src.user_management import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    InMemoryUserRepository,
    create_user,
    delete_user,
    get_user_by_username,
    initialize_default_admin,
    verify_password,
)


def test_create_user_and_verify_password():
    repository = InMemoryUserRepository()
    user = create_user(
        repository,
        "alice",
        "s3cretpw",
        can_upload=True,
        can_search=True,
        can_download=False,
    )

    assert user.username == "alice"
    assert user.can_upload is True
    assert user.can_search is True
    assert user.can_download is False
    assert verify_password("s3cretpw", user.password_hash)
    assert not verify_password("wrong", user.password_hash)


def test_create_user_requires_unique_username():
    repository = InMemoryUserRepository()
    create_user(repository, "bob", "password")

    with pytest.raises(ValueError):
        create_user(repository, "bob", "password2")


def test_get_and_delete_user():
    repository = InMemoryUserRepository()
    create_user(repository, "carol", "pw123456", can_download=True)

    retrieved = get_user_by_username(repository, "carol")
    assert retrieved is not None
    assert retrieved.can_download is True

    assert delete_user(repository, "carol") is True
    assert get_user_by_username(repository, "carol") is None
    assert delete_user(repository, "carol") is False


def test_initialize_default_admin_idempotent():
    repository = InMemoryUserRepository()
    admin = initialize_default_admin(repository)

    assert admin.username == DEFAULT_ADMIN_USERNAME
    assert admin.is_admin is True
    assert admin.can_upload is True
    assert admin.can_search is True
    assert admin.can_download is True
    assert verify_password(DEFAULT_ADMIN_PASSWORD, admin.password_hash)

    second_admin = initialize_default_admin(repository)
    assert second_admin.username == admin.username
    assert repository.get_user(DEFAULT_ADMIN_USERNAME) == second_admin
