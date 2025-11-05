"""Configuration and shared constants for manual API tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


PLACEHOLDER_BASE_URL = "https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/dev"
_CONFIG_FILENAME = "api_base_url.txt"
_CONFIG_PATH = Path(__file__).with_name(_CONFIG_FILENAME)

# Expose the configuration file path for callers that want to persist values.
CONFIG_FILE_PATH = _CONFIG_PATH


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _load_from_env() -> Optional[str]:
    return _clean(os.getenv("API_BASE_URL"))


def _load_from_file() -> Optional[str]:
    if _CONFIG_PATH.exists():
        return _clean(_CONFIG_PATH.read_text())
    return None


def _initial_base_url() -> str:
    return _load_from_env() or _load_from_file() or PLACEHOLDER_BASE_URL


API_BASE_URL = _initial_base_url()


def is_placeholder(url: Optional[str] = None) -> bool:
    """Return ``True`` if the URL is still the placeholder value."""

    if url is None:
        url = API_BASE_URL
    return url is None or "YOUR_API_ID" in url


def set_api_base_url(url: str, persist: bool = True) -> str:
    """Update the cached API base URL and optionally persist it to disk."""

    global API_BASE_URL  # pylint: disable=global-statement

    cleaned = _clean(url)
    if not cleaned:
        raise ValueError("API base URL cannot be empty.")

    API_BASE_URL = cleaned
    if persist:
        _CONFIG_PATH.write_text(cleaned + "\n")
    return API_BASE_URL


def require_api_base_url(refresh: bool = True) -> str:
    """Ensure an API base URL is available or raise a helpful error."""

    global API_BASE_URL  # pylint: disable=global-statement

    if refresh:
        env_value = _load_from_env()
        if env_value:
            API_BASE_URL = env_value
        elif is_placeholder(API_BASE_URL):
            file_value = _load_from_file()
            if file_value:
                API_BASE_URL = file_value

    if is_placeholder(API_BASE_URL):
        raise RuntimeError(
            "API base URL is not configured. Set the API_BASE_URL environment variable "
            f"or add your URL to {_CONFIG_FILENAME} in tests/manual-tests/."
        )

    return API_BASE_URL


TEST_URLS = {
    "model": "https://huggingface.co/gpt2",
    "dataset": "https://huggingface.co/datasets/wikitext",
    "code": "https://github.com/huggingface/transformers",
}

