"""
Reviewedness metric.

Measures the level of peer or community review coverage for a model.

Since HuggingFace doesn't expose pull request/review data, this metric
uses proxy indicators:
- Author diversity (multiple contributors)
- Community engagement (likes, downloads)
- Academic publication (peer-reviewed papers)

Scoring:
- Author diversity: 40% (more authors = more collaboration/review)
- Community engagement: 30% (high engagement suggests scrutiny)
- Publication: 30% (peer-reviewed papers indicate academic review)
"""

import logging
import math
import os
from typing import Any

try:
    from huggingface_hub import HfFileSystem, hf_hub_download
except ImportError:
    HfFileSystem = None
    hf_hub_download = None

logger = logging.getLogger(__name__)


def _fetch_readme_content(model_info: Any) -> str:
    """
    Fetch README.md content from HuggingFace model repository.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        README content as string, or empty string if not available
    """
    if not HfFileSystem or not hf_hub_download:
        return ""

    try:
        fs = HfFileSystem()
        paths = fs.ls(model_info.id, detail=False)
        if not any(p.endswith("README.md") for p in paths):
            return ""

        readme_file = hf_hub_download(
            repo_id=model_info.id, filename="README.md", repo_type="model"
        )
        with open(readme_file, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.debug(f"Could not fetch README for {model_info.id}: {e}")
        return ""


def _compute_author_diversity_score(model_info: Any) -> float:
    """
    Compute author diversity score based on number of unique contributors.

    More authors suggests more collaboration and potential code review.

    Scoring:
    - 1 author: 0.0
    - 2 authors: 0.3
    - 3-4 authors: 0.6
    - 5+ authors: 1.0

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    try:
        # Import here to avoid issues if not available
        import src.hf_api as hf_api

        token = os.getenv("HF_TOKEN")
        api = hf_api.HuggingFaceAPI(token=token)

        model_id = getattr(model_info, "id", None)
        if not model_id:
            return 0.0

        # Get commit history
        commits = api.list_repo_commits(repo_id=model_id, repo_type="model")

        # Count unique authors
        unique_authors = set()
        for entry in commits:
            authors_attr = getattr(entry, "authors", None)
            if authors_attr:
                if isinstance(authors_attr, list):
                    unique_authors.update(authors_attr)
                else:
                    unique_authors.add(str(authors_attr))

        num_authors = len(unique_authors)

        # Score based on author count
        if num_authors <= 1:
            return 0.0
        elif num_authors == 2:
            return 0.3
        elif num_authors <= 4:
            return 0.6
        else:
            return 1.0

    except Exception as e:
        logger.debug(f"Error computing author diversity: {e}")
        return 0.0


def _compute_community_engagement_score(model_info: Any) -> float:
    """
    Compute community engagement score based on likes and downloads.

    High engagement suggests the model has been scrutinized by the community.

    Uses sigmoid normalization:
    - engagement = likes/1000 + downloads/10000
    - score = 1 / (1 + exp(-engagement + 3))

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    try:
        likes = getattr(model_info, "likes", 0) or 0
        downloads = getattr(model_info, "downloads", 0) or 0

        # Normalize metrics
        engagement = likes / 1000.0 + downloads / 10000.0

        # Sigmoid function for smooth scaling
        # Centered around engagement = 3 (reasonable threshold)
        score = 1.0 / (1.0 + math.exp(-engagement + 3))

        return min(1.0, score)

    except Exception as e:
        logger.debug(f"Error computing community engagement: {e}")
        return 0.0


def _check_publication_evidence(readme_content: str) -> float:
    """
    Check README for evidence of peer-reviewed publications.

    Presence of arXiv, DOI, or academic paper links suggests peer review.

    Args:
        readme_content: Content of README.md

    Returns:
        1.0 if publication evidence found, 0.0 otherwise
    """
    if not readme_content:
        return 0.0

    readme_lower = readme_content.lower()

    # Look for academic publication indicators
    publication_indicators = [
        "arxiv.org",
        "doi:",
        "doi.org",
        "proceedings",
        "conference",
        "journal",
        "acm.org",
        "ieee.org",
        "neurips",
        "icml",
        "iclr",
        "cvpr",
        "emnlp",
        "acl anthology",
    ]

    has_publication = any(indicator in readme_lower for indicator in publication_indicators)

    return 1.0 if has_publication else 0.0


def compute_reviewedness_metric(model_info: Any) -> float:
    """
    Compute reviewedness score using proxy metrics.

    Since HuggingFace doesn't expose PR/review data, we use:
    - Author diversity (40%): Multiple contributors suggest collaboration/review
    - Community engagement (30%): High likes/downloads suggest scrutiny
    - Publication evidence (30%): Peer-reviewed papers indicate academic review

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Reviewedness score between 0.0 and 1.0
    """
    try:
        # Fetch README for publication check
        readme_content = _fetch_readme_content(model_info)

        # Component scores
        author_score = _compute_author_diversity_score(model_info)
        engagement_score = _compute_community_engagement_score(model_info)
        publication_score = _check_publication_evidence(readme_content)

        # Weighted combination
        final_score = (
            author_score * 0.40 + engagement_score * 0.30 + publication_score * 0.30
        )

        # Ensure score is within bounds
        final_score = max(0.0, min(1.0, final_score))

        logger.debug(
            f"Reviewedness scores - authors: {author_score:.2f}, "
            f"engagement: {engagement_score:.2f}, publication: {publication_score:.2f}, "
            f"final: {final_score:.2f}"
        )

        return round(final_score, 4)

    except Exception as e:
        logger.error(f"Error computing reviewedness metric: {e}")
        return 0.0
