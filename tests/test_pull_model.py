import os
import sys
import types

import pytest

# Ensure the project's src directory is importable
CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


# Provide a lightweight stub for the optional 'validators' dependency
# so that importing the module under test doesn't fail in environments
# where 'validators' is not installed.
validators_stub = types.ModuleType("validators")


def _is_valid_url(candidate: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(candidate)
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)


validators_stub.url = _is_valid_url
sys.modules["validators"] = validators_stub


from metrics.helpers.pull_model import (  # noqa: E402
    UrlType,
    get_url_type,
    pull_model_info,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/org/repo", UrlType.GIT_REPO),
        ("https://huggingface.co/datasets/glue", UrlType.HUGGING_FACE_DATASET),
        (
            "https://huggingface.co/spaces/gradio/hello_world",
            UrlType.HUGGING_FACE_CODEBASE,
        ),
        ("https://huggingface.co/bert-base-uncased", UrlType.HUGGING_FACE_MODEL),
        ("https://example.com/foo", UrlType.OTHER),
        ("not_a_url", UrlType.INVALID),
    ],
)
def test_get_url_type(url: str, expected: UrlType) -> None:
    assert get_url_type(url) == expected


class FakeHfApi:
    """A fake HuggingFace client that mimics both the public wrapper methods
    and the underlying .api attribute used by pull_model_info.
    """

    def __init__(self) -> None:
        self.calls = []
        # Expose self as `.api` so code can call `client.api.space_info` etc.
        self.api = self

    # Core info methods (accept **kwargs because real API does)
    def dataset_info(self, name: str, **kwargs):
        self.calls.append(("dataset_info", name))
        return {"type": "dataset", "name": name}

    def model_info(self, name: str, **kwargs):
        self.calls.append(("model_info", name))
        return {"type": "model", "name": name}

    def space_info(self, name: str, **kwargs):
        self.calls.append(("space_info", name))
        return {"type": "space", "name": name}

    # Wrapper-like methods so patched _get_client() returning this object
    # still satisfies calls to get_model_info / get_dataset_info
    def get_model_info(self, name: str):  # mirror HuggingFaceAPI
        return self.model_info(name)

    def get_dataset_info(self, name: str):  # mirror HuggingFaceAPI
        return self.dataset_info(name)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeHfApi:
    """Provide a single patched fake client for tests that need network isolation."""
    fake = FakeHfApi()
    monkeypatch.setattr(
        "metrics.helpers.pull_model._get_client", lambda: fake, raising=True
    )
    return fake


def test_pull_model_info_for_model(fake_client: FakeHfApi) -> None:
    url = "https://huggingface.co/owner/repo"
    result = pull_model_info(url)
    assert result == {"type": "model", "name": "owner/repo"}


def test_pull_model_info_for_dataset(fake_client: FakeHfApi) -> None:
    url = "https://huggingface.co/datasets/owner/repo"
    result = pull_model_info(url)
    assert result == {"type": "dataset", "name": "owner/repo"}


def test_pull_model_info_for_space(fake_client: FakeHfApi) -> None:
    url = "https://huggingface.co/spaces/owner/repo"
    result = pull_model_info(url)
    assert result == {"type": "space", "name": "owner/repo"}


def test_pull_model_info_for_git_repo_returns_none(fake_client: FakeHfApi) -> None:
    url = "https://github.com/org/repo"
    result = pull_model_info(url)
    assert result is None


def test_pull_model_info_other_url_raises() -> None:
    url = "https://example.com/foo"
    with pytest.raises(ValueError) as exc:
        pull_model_info(url)
    assert str(exc.value) == f"Other URL type: {url}"


def test_pull_model_info_invalid_url_raises() -> None:
    url = "not_a_url"
    with pytest.raises(ValueError) as exc:
        pull_model_info(url)
    assert str(exc.value) == f"Invalid URL: {url}"
