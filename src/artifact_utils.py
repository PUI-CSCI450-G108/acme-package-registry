"""
Shared utilities for artifact ID generation and URL handling.

This module provides functions used by both Lambda handlers and metrics.
"""

import uuid
from src.metrics.helpers.pull_model import canonicalize_hf_url


def generate_artifact_id(artifact_type: str, url: str) -> str:
    """
    Generate a deterministic, low-collision artifact ID.

    Uses UUIDv5 (namespace-based) for deterministic IDs from (type, canonical URL).
    This ensures the same artifact_type + URL combination always produces
    the same ID, enabling idempotency and duplicate detection.

    Args:
        artifact_type: Type of artifact ('model', 'dataset', or 'code')
        url: Source URL for the artifact

    Returns:
        String representation of UUID (hyphenated format)

    Note:
        HuggingFace URLs are canonicalized to avoid duplicate IDs for equivalent URLs.
    """
    normalized_url = (
        canonicalize_hf_url(url)
        if isinstance(url, str) and url.startswith("https://huggingface.co/")
        else url
    )
    name = f"{artifact_type}:{normalized_url}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))
