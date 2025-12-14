"""
License compatibility checking and GitHub API integration.

Provides functionality to:
- Fetch license information from GitHub repositories
- Check compatibility between two licenses
- Normalize license strings to SPDX IDs
"""

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Raised when GitHub API request fails."""

    pass


class LicenseNotFoundError(Exception):
    """Raised when repository has no license."""

    pass


# License compatibility matrix
# Format: {artifact_license: {compatible_github_licenses}}
# Based on common open-source license compatibility rules
COMPATIBILITY_MATRIX = {
    # Permissive licenses - very compatible
    "mit": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-2.0",
        "gpl-3.0",
        "mpl-2.0",
        "epl-2.0",
        "isc",
        "unlicense",
    },
    "apache-2.0": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-3.0",  # Note: NOT gpl-2.0 (Apache-2.0 incompatible with GPLv2)
        "mpl-2.0",
        "epl-2.0",
        "isc",
        "unlicense",
    },
    "bsd-3-clause": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-2.0",
        "gpl-3.0",
        "mpl-2.0",
        "epl-2.0",
        "isc",
        "unlicense",
    },
    "bsd-2-clause": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-2.0",
        "gpl-3.0",
        "mpl-2.0",
        "epl-2.0",
        "isc",
        "unlicense",
    },
    # LGPL - weak copyleft, fairly compatible
    "lgpl-2.1": {"lgpl-2.1", "lgpl-3.0", "gpl-2.0", "gpl-3.0"},
    "lgpl-3.0": {"lgpl-3.0", "gpl-3.0"},
    # GPL - strong copyleft, restrictive
    "gpl-2.0": {"gpl-2.0", "gpl-3.0"},
    "gpl-3.0": {"gpl-3.0"},
    # AGPL - strongest copyleft
    "agpl-3.0": {"agpl-3.0"},
    # Mozilla/Eclipse - weak copyleft
    "mpl-2.0": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "mpl-2.0",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-2.0",
        "gpl-3.0",
    },
    "epl-2.0": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "epl-2.0",
        "gpl-2.0",
        "gpl-3.0",
    },
    # Non-commercial - very restrictive
    "cc-by-nc-4.0": {"cc-by-nc-4.0", "cc-by-nc-sa-4.0"},
    "cc-by-nc-sa-4.0": {"cc-by-nc-sa-4.0"},
    # Creative Commons - attribution required
    "cc-by-4.0": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-2.0",
        "gpl-3.0",
        "mpl-2.0",
        "epl-2.0",
    },
    "cc-by-sa-4.0": {"cc-by-sa-4.0", "gpl-3.0"},
    # ISC - similar to MIT
    "isc": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "isc",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-2.0",
        "gpl-3.0",
        "mpl-2.0",
        "epl-2.0",
    },
    # Unlicense - public domain
    "unlicense": {
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "isc",
        "unlicense",
        "lgpl-2.1",
        "lgpl-3.0",
        "gpl-2.0",
        "gpl-3.0",
        "mpl-2.0",
        "epl-2.0",
    },
}


def normalize_license_string(license_str: str) -> Optional[str]:
    """
    Normalize various license formats to SPDX IDs.

    Examples:
    - "MIT" -> "mit"
    - "Apache 2.0" -> "apache-2.0"
    - "apache-2.0" -> "apache-2.0"

    Args:
        license_str: License string to normalize

    Returns:
        Normalized SPDX license ID (lowercase) or None if empty
    """
    if not license_str:
        return None

    license_lower = license_str.lower().strip()

    # Handle common variations
    normalizations = {
        "mit": "mit",
        "apache-2.0": "apache-2.0",
        "apache 2.0": "apache-2.0",
        "apache license 2.0": "apache-2.0",
        "bsd-3-clause": "bsd-3-clause",
        "bsd-2-clause": "bsd-2-clause",
        "gpl-3.0": "gpl-3.0",
        "gpl-2.0": "gpl-2.0",
        "lgpl-2.1": "lgpl-2.1",
        "lgpl-3.0": "lgpl-3.0",
        "agpl-3.0": "agpl-3.0",
        "mpl-2.0": "mpl-2.0",
        "epl-2.0": "epl-2.0",
        "cc-by-4.0": "cc-by-4.0",
        "cc-by-sa-4.0": "cc-by-sa-4.0",
        "cc-by-nc-4.0": "cc-by-nc-4.0",
        "cc-by-nc-sa-4.0": "cc-by-nc-sa-4.0",
        "cc-by-nc": "cc-by-nc-4.0",
        "isc": "isc",
        "unlicense": "unlicense",
    }

    result = normalizations.get(license_lower, license_lower)
    logger.debug(f"Normalized license '{license_str}' to '{result}'")
    return result


def check_license_compatibility(
    artifact_license: str, github_license: str
) -> bool:
    """
    Check if artifact license is compatible with GitHub repository license.

    Compatibility is checked for the use case: using the GitHub repository's
    code/data with a model that has the artifact license.

    Args:
        artifact_license: SPDX license ID of the artifact (normalized)
        github_license: SPDX license ID of GitHub repo (normalized)

    Returns:
        True if compatible, False otherwise
    """
    if not artifact_license or not github_license:
        logger.warning(
            f"Missing license for compatibility check: artifact={artifact_license}, github={github_license}"
        )
        return False

    # Exact match is always compatible
    if artifact_license == github_license:
        logger.info(
            f"License compatibility: exact match ({artifact_license})"
        )
        return True

    # Check compatibility matrix
    compatible_licenses = COMPATIBILITY_MATRIX.get(artifact_license, set())
    is_compatible = github_license in compatible_licenses

    logger.info(
        f"License compatibility check: artifact={artifact_license}, "
        f"github={github_license}, compatible={is_compatible}"
    )

    return is_compatible


def fetch_github_license(github_url: str) -> str:
    """
    Fetch license from GitHub repository using GitHub REST API.

    Args:
        github_url: Full GitHub URL (e.g., https://github.com/owner/repo)

    Returns:
        License SPDX ID (lowercase, e.g., 'mit', 'apache-2.0')

    Raises:
        GitHubAPIError: If API request fails
        LicenseNotFoundError: If repo has no license
    """
    # Parse owner/repo from URL
    # Handle formats: https://github.com/owner/repo[/tree/branch][.git]
    pattern = r"https://github\.com/([^/]+)/([^/]+)"
    match = re.match(pattern, github_url)
    if not match:
        raise ValueError(f"Invalid GitHub URL format: {github_url}")

    owner, repo = match.groups()
    # Remove .git suffix if present
    repo = repo.replace(".git", "")

    api_url = f"https://api.github.com/repos/{owner}/{repo}/license"

    logger.info(f"Fetching license from GitHub API: {api_url}")

    try:
        # GitHub API v3 - use Accept header
        req = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "ACME-Package-Registry",
            },
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        # Response structure: {"license": {"spdx_id": "MIT", ...}}
        license_info = data.get("license", {})
        spdx_id = license_info.get("spdx_id")

        if not spdx_id or spdx_id == "NOASSERTION":
            raise LicenseNotFoundError(
                f"No license found for {owner}/{repo}"
            )

        # Normalize to lowercase (consistent with existing license.py)
        normalized = spdx_id.lower()
        logger.info(
            f"Fetched license for {owner}/{repo}: {spdx_id} -> {normalized}"
        )
        return normalized

    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise GitHubAPIError(f"Repository not found: {owner}/{repo}")
        elif e.code == 403:
            # Rate limiting
            raise GitHubAPIError("GitHub API rate limit exceeded (403)")
        else:
            raise GitHubAPIError(f"GitHub API error {e.code}: {e.reason}")

    except urllib.error.URLError as e:
        raise GitHubAPIError(
            f"Network error accessing GitHub API: {e.reason}"
        )

    except json.JSONDecodeError as e:
        raise GitHubAPIError(f"Failed to parse GitHub API response: {e}")

    except Exception as e:
        raise GitHubAPIError(
            f"Unexpected error fetching GitHub license: {str(e)}"
        )
