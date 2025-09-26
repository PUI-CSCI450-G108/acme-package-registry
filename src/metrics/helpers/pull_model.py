from enum import Enum
from typing import Optional, Any

import validators

try:
    # Prefer central wrapper
    from src.hf_api import HuggingFaceAPI  # type: ignore
except Exception:  # pragma: no cover - fallback path for tests manipulating sys.path
    from hf_api import HuggingFaceAPI  # type: ignore


# Define enum for url types
class UrlType(Enum):
    HUGGING_FACE_MODEL = "hugging_face_model"
    HUGGING_FACE_DATASET = "hugging_face_dataset"
    HUGGING_FACE_CODEBASE = "hugging_face_codebase"
    GIT_REPO = "git_repo"
    OTHER = "other"
    INVALID = "invalid"


_hf_client: Optional[HuggingFaceAPI] = None


def _get_client() -> HuggingFaceAPI:
    global _hf_client
    if _hf_client is None:
        _hf_client = HuggingFaceAPI()
    return _hf_client


def pull_model_info(url: str) -> Any:
    """Return rich info dict / object for a HF resource.

    Returns None for plain git repos (deferred cloning handled elsewhere).
    Raises ValueError on invalid / unsupported URLs.
    """
    client = _get_client()
    url_type = get_url_type(url)

    if url_type == UrlType.INVALID:
        raise ValueError(f"Invalid URL: {url}")

    if url_type == UrlType.GIT_REPO:
        # Defer cloning / git-based metrics to another component
        return None

    if url_type == UrlType.OTHER:
        raise ValueError(f"Other URL type: {url}")

    # Extract the canonical repo id
    if url_type == UrlType.HUGGING_FACE_DATASET:
        name = url.split("/datasets/")[1]
        return client.get_dataset_info(name)
    if url_type == UrlType.HUGGING_FACE_CODEBASE:
        name = url.split("/spaces/")[1]
        # space_info not wrapped yet; fall back to underlying api attr
        return client.api.space_info(name, files_metadata=True)  # type: ignore[attr-defined]
    # Default: model
    name = url.split("huggingface.co/")[1]
    return client.get_model_info(name)


# Parses the url and returns the type of the url
def get_url_type(url: str) -> UrlType:
    if not validators.url(url):
        return UrlType.INVALID
    if url.startswith("https://github.com/"):
        return UrlType.GIT_REPO
    if not url.startswith("https://huggingface.co/"):
        return UrlType.OTHER
    if "/datasets/" in url:
        return UrlType.HUGGING_FACE_DATASET
    if "/spaces/" in url:
        return UrlType.HUGGING_FACE_CODEBASE
    return UrlType.HUGGING_FACE_MODEL