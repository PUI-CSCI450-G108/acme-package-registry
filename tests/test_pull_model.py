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


from metrics.helpers.pull_model import UrlType, get_url_type, pull_model_info  # noqa: E402


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
    def __init__(self) -> None:
        self.calls = []

    def dataset_info(self, name: str):
        self.calls.append(("dataset_info", name))
        return {"type": "dataset", "name": name}

    def model_info(self, name: str):
        self.calls.append(("model_info", name))
        return {"type": "model", "name": name}

    def space_info(self, name: str):
        self.calls.append(("space_info", name))
        return {"type": "space", "name": name}


def test_pull_model_info_for_model(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a two-segment model URL so the helper's split logic works
    url = "https://huggingface.co/owner/repo"

    fake = FakeHfApi()
    monkeypatch.setattr(
        "metrics.helpers.pull_model.HfApi", lambda: fake, raising=True
    )

    result = pull_model_info(url)
    assert result == {"type": "model", "name": "owner/repo"}


def test_pull_model_info_for_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://huggingface.co/datasets/owner/repo"

    fake = FakeHfApi()
    monkeypatch.setattr(
        "metrics.helpers.pull_model.HfApi", lambda: fake, raising=True
    )

    result = pull_model_info(url)
    assert result == {"type": "dataset", "name": "owner/repo"}


def test_pull_model_info_for_space(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://huggingface.co/spaces/owner/repo"

    fake = FakeHfApi()
    monkeypatch.setattr(
        "metrics.helpers.pull_model.HfApi", lambda: fake, raising=True
    )

    result = pull_model_info(url)
    assert result == {"type": "space", "name": "owner/repo"}


def test_pull_model_info_for_git_repo_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://github.com/org/repo"

    fake = FakeHfApi()
    monkeypatch.setattr(
        "metrics.helpers.pull_model.HfApi", lambda: fake, raising=True
    )

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

