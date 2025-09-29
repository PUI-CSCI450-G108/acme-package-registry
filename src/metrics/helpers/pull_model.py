from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse

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


def canonicalize_hf_url(url: str) -> str:
    """Return a cleaned HF URL with only the canonical id part.
    Examples:
      https://huggingface.co/openai/whisper-tiny/tree/main -> https://huggingface.co/openai/whisper-tiny
      https://huggingface.co/datasets/glue/viewer -> https://huggingface.co/datasets/glue
    """
    if not validators.url(url):
        return url
    if not url.startswith("https://huggingface.co/"):
        return url
    p = urlparse(url)
    parts = [seg for seg in p.path.split("/") if seg]
    if not parts:
        return url
    # datasets / spaces / {model}
    if parts[0] == "datasets":
        parts = parts[:3] if len(parts) >= 3 else parts[:2]
        return f"https://huggingface.co/{'/'.join(parts)}"
    if parts[0] == "spaces":
        parts = parts[:3]
        return f"https://huggingface.co/{'/'.join(parts)}"
    # model path: owner/name[/...]
    if len(parts) >= 2:
        return f"https://huggingface.co/{parts[0]}/{parts[1]}"
    return url


def pull_model_info(url: str) -> Any:
    """Return rich info dict / object for a HF resource.

    Returns None for plain git repos (deferred cloning handled elsewhere).
    Raises ValueError on invalid / unsupported URLs.
    """
    client = _get_client()
    url = canonicalize_hf_url(url)
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
    # Always return an UrlType (never None)
    try:
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
        # Plain HF model URLs fall here
        return UrlType.HUGGING_FACE_MODEL
    except Exception:
        # Defensive default if something unexpected happens
        return UrlType.INVALID
