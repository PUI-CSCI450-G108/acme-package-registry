"""
GitHub license integration for license compatibility checking.

This module provides functions to fetch license information from GitHub
and determine license compatibility between a HuggingFace model and
a GitHub repository for fine-tuning and inference use cases.
"""

import logging
import os
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# License compatibility matrix
# These licenses are compatible with LGPLv2.1 for fine-tuning and inference
COMPATIBLE_LICENSES = [
    "mit",
    "apache-2.0",
    "bsd-3-clause",
    "bsd-2-clause",
    "lgpl-2.1",
    "lgpl-3.0",
    "epl-2.0",
    "mpl-2.0",
    "apache",
    "bsd",
    "isc",
    "cc0-1.0",
    "unlicense",
]

# These licenses are incompatible (copyleft licenses stricter than LGPL)
INCOMPATIBLE_LICENSES = [
    "gpl-3.0",
    "gpl-2.0",
    "agpl-3.0",
    "cc-by-nc",
    "cc-by-nc-sa",
    "cc-by-nc-nd",
]


def parse_github_url(github_url: str) -> Optional[Tuple[str, str]]:
    """
    Parse a GitHub URL to extract owner and repo name.

    Args:
        github_url: GitHub repository URL

    Returns:
        Tuple of (owner, repo) or None if invalid URL

    Examples:
        >>> parse_github_url("https://github.com/google-research/bert")
        ('google-research', 'bert')
        >>> parse_github_url("https://github.com/openai/whisper/")
        ('openai', 'whisper')
    """
    try:
        parsed = urlparse(github_url)
        if parsed.hostname not in ["github.com", "www.github.com"]:
            return None

        # Remove leading/trailing slashes and split
        path_parts = parsed.path.strip("/").split("/")

        if len(path_parts) < 2:
            return None

        owner = path_parts[0]
        repo = path_parts[1]

        # Remove .git suffix if present
        if repo.endswith(".git"):
            repo = repo[:-4]

        return (owner, repo)
    except Exception as e:
        logger.warning(f"Error parsing GitHub URL {github_url}: {e}")
        return None


def fetch_github_license(github_url: str) -> Optional[str]:
    """
    Fetch license information from a GitHub repository.

    Uses the GitHub REST API to get the repository's license.
    Requires GITHUB_TOKEN environment variable for authenticated requests
    (to avoid rate limiting).

    Args:
        github_url: GitHub repository URL

    Returns:
        License SPDX identifier (lowercase), or None if not found

    Examples:
        >>> fetch_github_license("https://github.com/huggingface/transformers")
        'apache-2.0'
    """
    parsed = parse_github_url(github_url)
    if not parsed:
        logger.warning(f"Invalid GitHub URL: {github_url}")
        return None

    owner, repo = parsed

    # Use GitHub API to get license
    api_url = f"https://api.github.com/repos/{owner}/{repo}/license"

    # Prepare headers with optional authentication
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    else:
        logger.warning(
            "No GITHUB_TOKEN found in environment - API requests may be rate limited"
        )

    try:
        response = requests.get(api_url, headers=headers, timeout=10)

        if response.status_code == 404:
            logger.warning(f"GitHub repository not found: {owner}/{repo}")
            return None

        if response.status_code == 403:
            logger.error(f"GitHub API rate limit exceeded or access denied")
            return None

        response.raise_for_status()

        data = response.json()
        license_info = data.get("license", {})
        spdx_id = license_info.get("spdx_id")

        if spdx_id and spdx_id != "NOASSERTION":
            # Normalize to lowercase
            return spdx_id.lower()

        # Fallback: try to parse from LICENSE file content
        download_url = data.get("download_url")
        if download_url:
            content_response = requests.get(download_url, timeout=10)
            content_response.raise_for_status()
            content = content_response.text.lower()

            # Simple heuristic matching
            if "apache" in content and "2.0" in content:
                return "apache-2.0"
            elif "mit license" in content:
                return "mit"
            elif "bsd" in content:
                if "3-clause" in content:
                    return "bsd-3-clause"
                elif "2-clause" in content:
                    return "bsd-2-clause"
                return "bsd"
            elif "gpl" in content:
                if "version 3" in content or "v3" in content:
                    return "gpl-3.0"
                elif "version 2" in content or "v2" in content:
                    return "gpl-2.0"

        return None

    except requests.RequestException as e:
        logger.error(f"Error fetching license from GitHub API: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching GitHub license: {e}")
        return None


def normalize_license_identifier(license_str: str) -> str:
    """
    Normalize a license string to a standard identifier.

    Args:
        license_str: License string (may be SPDX ID, name, or description)

    Returns:
        Normalized license identifier (lowercase)

    Examples:
        >>> normalize_license_identifier("Apache-2.0")
        'apache-2.0'
        >>> normalize_license_identifier("MIT License")
        'mit'
        >>> normalize_license_identifier("BSD 3-Clause")
        'bsd-3-clause'
    """
    if not license_str:
        return ""

    license_lower = license_str.lower().strip()

    # Direct SPDX ID match
    if license_lower in COMPATIBLE_LICENSES or license_lower in INCOMPATIBLE_LICENSES:
        return license_lower

    # Pattern matching for common variations
    if "apache" in license_lower:
        if "2.0" in license_lower or "2" in license_lower:
            return "apache-2.0"
        return "apache"

    if "mit" in license_lower:
        return "mit"

    if "bsd" in license_lower:
        if "3" in license_lower or "three" in license_lower:
            return "bsd-3-clause"
        elif "2" in license_lower or "two" in license_lower:
            return "bsd-2-clause"
        return "bsd"

    if "gpl" in license_lower:
        if "agpl" in license_lower or "affero" in license_lower:
            return "agpl-3.0"
        elif "3" in license_lower or "v3" in license_lower:
            return "gpl-3.0"
        elif "2" in license_lower or "v2" in license_lower:
            return "gpl-2.0"
        return "gpl-3.0"  # Default to strictest

    if "lgpl" in license_lower:
        if "3" in license_lower or "v3" in license_lower:
            return "lgpl-3.0"
        elif "2.1" in license_lower:
            return "lgpl-2.1"
        return "lgpl-2.1"

    if "mpl" in license_lower or "mozilla" in license_lower:
        return "mpl-2.0"

    if "epl" in license_lower or "eclipse" in license_lower:
        return "epl-2.0"

    if "cc0" in license_lower or "creative commons zero" in license_lower:
        return "cc0-1.0"

    if "unlicense" in license_lower:
        return "unlicense"

    if "isc" in license_lower:
        return "isc"

    # Non-commercial Creative Commons licenses
    if "cc" in license_lower and "nc" in license_lower:
        return "cc-by-nc"

    return license_lower


def check_license_compatibility(
    model_license: str, github_license: str
) -> Tuple[bool, str]:
    """
    Check if a model license is compatible with a GitHub repository license
    for fine-tuning and inference usage.

    Compatibility rules (for LGPLv2.1 compatibility):
    - Model and code must both be permissive (MIT, Apache, BSD, LGPL, etc.)
    - Stricter copyleft licenses (GPL, AGPL) are incompatible
    - Non-commercial licenses (CC-BY-NC) are incompatible

    Args:
        model_license: License of the HuggingFace model
        github_license: License of the GitHub repository

    Returns:
        Tuple of (is_compatible: bool, reason: str)

    Examples:
        >>> check_license_compatibility("apache-2.0", "mit")
        (True, "Both licenses are permissive and compatible")
        >>> check_license_compatibility("gpl-3.0", "mit")
        (False, "Model license gpl-3.0 is incompatible (copyleft)")
    """
    model_lic_norm = normalize_license_identifier(model_license)
    github_lic_norm = normalize_license_identifier(github_license)

    # Check if model license is incompatible
    for incompatible in INCOMPATIBLE_LICENSES:
        if incompatible in model_lic_norm:
            return (
                False,
                f"Model license {model_lic_norm} is incompatible (copyleft or non-commercial)",
            )

    # Check if GitHub license is incompatible
    for incompatible in INCOMPATIBLE_LICENSES:
        if incompatible in github_lic_norm:
            return (
                False,
                f"GitHub license {github_lic_norm} is incompatible (copyleft or non-commercial)",
            )

    # Check if both are in compatible list
    model_compatible = any(lic in model_lic_norm for lic in COMPATIBLE_LICENSES)
    github_compatible = any(lic in github_lic_norm for lic in COMPATIBLE_LICENSES)

    if model_compatible and github_compatible:
        return (True, "Both licenses are permissive and compatible")

    # Unknown licenses - be conservative
    if not model_lic_norm or not github_lic_norm:
        return (False, "One or both licenses could not be determined")

    # If we get here, at least one license is unknown/unrecognized
    return (False, f"License compatibility uncertain: model={model_lic_norm}, github={github_lic_norm}")
