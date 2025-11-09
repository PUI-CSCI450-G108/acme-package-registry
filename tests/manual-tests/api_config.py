"""Configuration and shared constants for manual API tests."""

import os


def _require_api_base_url() -> str:
    """Return the API base URL from the environment or raise a helpful error."""
    api_base_url = os.getenv("API_BASE_URL")
    if not api_base_url:
        raise RuntimeError(
            "API_BASE_URL environment variable is not set. Please set it to your API Gateway URL."
        )
    return api_base_url


API_BASE_URL = os.getenv("API_BASE_URL")


TEST_URLS = {
    "model": "https://huggingface.co/gpt2",
    "dataset": "https://huggingface.co/datasets/wikitext",
    "code": "https://github.com/huggingface/transformers",
}

