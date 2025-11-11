"""
Reviewedness metric.

Measures the level of peer or community review coverage for a model.

This metric combines multiple indicators of review activity:
- Author diversity (multiple contributors from different organizations)
- Community engagement (likes, downloads with adjusted scaling)
- Academic publication (graduated scoring based on quality/quantity)
- Discussion/PR activity (actual peer review conversations)
- Model card completeness (documentation quality)

Scoring:
- Author diversity: 30% (more authors/orgs = more collaboration/review)
- Community engagement: 20% (engagement suggests scrutiny, tuned to prevent saturation)
- Publication: 20% (graduated: 0.0/0.5/1.0 based on evidence quality)
- Discussion/PR activity: 20% (actual community review conversations)
- Model card completeness: 10% (well-documented models get more scrutiny)
"""

import logging
import math
import os
import re
from typing import Any

try:
    from huggingface_hub import HfFileSystem, hf_hub_download, get_repo_discussions
except ImportError:
    HfFileSystem = None
    hf_hub_download = None
    get_repo_discussions = None

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
    Compute author diversity score based on unique contributors and organizations.

    More authors from different organizations suggests more collaboration and review.
    Enhanced to check for organizational diversity via email domains and usernames.

    Scoring (takes max of author count and org diversity):
    - 1 author/org: 0.0
    - 2 authors/orgs: 0.3
    - 3-4 authors/orgs: 0.6
    - 5+ authors/orgs: 1.0

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
        unique_orgs = set()

        for entry in commits:
            authors_attr = getattr(entry, "authors", None)
            if authors_attr:
                if isinstance(authors_attr, list):
                    for author in authors_attr:
                        author_str = str(author)
                        unique_authors.add(author_str)

                        # Extract organization from email domain or username
                        # Look for patterns like "user@company.com" or "company/user"
                        if "@" in author_str:
                            domain = author_str.split("@")[-1].split(".")[0]
                            unique_orgs.add(domain.lower())
                        elif "/" in author_str:
                            org = author_str.split("/")[0]
                            unique_orgs.add(org.lower())
                else:
                    author_str = str(authors_attr)
                    unique_authors.add(author_str)

                    if "@" in author_str:
                        domain = author_str.split("@")[-1].split(".")[0]
                        unique_orgs.add(domain.lower())
                    elif "/" in author_str:
                        org = author_str.split("/")[0]
                        unique_orgs.add(org.lower())

        num_authors = len(unique_authors)
        num_orgs = len(unique_orgs) if unique_orgs else 1

        # Score based on both author count and org diversity (take max)
        # This rewards either many individuals OR cross-organizational collaboration
        def score_count(count):
            if count <= 1:
                return 0.0
            elif count == 2:
                return 0.3
            elif count <= 4:
                return 0.6
            else:
                return 1.0

        author_score = score_count(num_authors)
        org_score = score_count(num_orgs)

        # Take max to reward either type of diversity
        final_score = max(author_score, org_score)

        logger.debug(f"Author diversity: {num_authors} authors, {num_orgs} orgs, score: {final_score}")

        return final_score

    except Exception as e:
        logger.debug(f"Error computing author diversity: {e}")
        return 0.0


def _compute_community_engagement_score(model_info: Any) -> float:
    """
    Compute community engagement score based on likes and downloads.

    High engagement suggests the model has been scrutinized by the community.

    Uses sigmoid normalization with adjusted constants to prevent saturation:
    - engagement = likes/2000 + downloads/50000  (increased denominators)
    - score = 1 / (1 + exp(-0.5*engagement + 3))  (gentler slope)

    This tuning prevents popular models from all scoring 1.0 while still
    rewarding high engagement. Models need ~12K likes + 600K downloads to reach 0.95.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    try:
        likes = getattr(model_info, "likes", 0) or 0
        downloads = getattr(model_info, "downloads", 0) or 0

        # Normalize metrics with higher denominators to prevent saturation
        engagement = likes / 2000.0 + downloads / 50000.0

        # Sigmoid function with gentler slope (0.5 multiplier)
        # Centered around engagement = 6 for better discrimination
        score = 1.0 / (1.0 + math.exp(-0.5 * engagement + 3))

        return min(1.0, score)

    except Exception as e:
        logger.debug(f"Error computing community engagement: {e}")
        return 0.0


def _check_publication_evidence(readme_content: str) -> float:
    """
    Check README for evidence of peer-reviewed publications.

    Graduated scoring based on quality and quantity of publication evidence:
    - 1.0: Multiple high-quality venues (conference/journal + DOI/arXiv)
    - 0.5: Single publication indicator (just arXiv, or just conference mention)
    - 0.0: No publication evidence

    Args:
        readme_content: Content of README.md

    Returns:
        Score between 0.0 and 1.0
    """
    if not readme_content:
        return 0.0

    readme_lower = readme_content.lower()

    # High-quality publication indicators (peer-reviewed venues)
    high_quality_indicators = [
        "neurips",
        "icml",
        "iclr",
        "cvpr",
        "emnlp",
        "acl anthology",
        "conference",
        "proceedings",
        "journal",
        "acm.org",
        "ieee.org",
    ]

    # Paper identifiers (arXiv, DOI)
    paper_identifiers = [
        "arxiv.org",
        "doi:",
        "doi.org",
    ]

    # Count matches
    high_quality_count = sum(1 for indicator in high_quality_indicators if indicator in readme_lower)
    identifier_count = sum(1 for identifier in paper_identifiers if identifier in readme_lower)

    # Graduated scoring
    if high_quality_count > 0 and identifier_count > 0:
        # Both venue and paper identifier present = strong evidence
        return 1.0
    elif high_quality_count > 0 or identifier_count > 0:
        # At least one indicator = moderate evidence
        return 0.5
    else:
        return 0.0


def _compute_model_card_completeness(model_info: Any, readme_content: str) -> float:
    """
    Compute model card completeness score.

    Well-documented models are more likely to undergo community scrutiny.
    Checks for presence of key documentation sections and metadata.

    Scoring criteria:
    - Has detailed README (>1000 chars): 0.3
    - Has model card metadata tags: 0.2
    - Has license field: 0.2
    - Has datasets field: 0.2
    - Has base_model or metrics: 0.1

    Args:
        model_info: HuggingFace ModelInfo object
        readme_content: Content of README.md

    Returns:
        Score between 0.0 and 1.0
    """
    score = 0.0

    try:
        # Check README length (detailed documentation)
        if readme_content and len(readme_content) > 1000:
            score += 0.3

        # Check for model card metadata
        card_data = getattr(model_info, "cardData", None) or {}

        # Has tags
        tags = getattr(model_info, "tags", None) or []
        if tags and len(tags) > 0:
            score += 0.2

        # Has license
        if card_data.get("license"):
            score += 0.2

        # Has datasets
        if card_data.get("datasets"):
            score += 0.2

        # Has base_model or metrics
        if card_data.get("base_model") or card_data.get("model-index"):
            score += 0.1

        return min(1.0, score)

    except Exception as e:
        logger.debug(f"Error computing model card completeness: {e}")
        return 0.0


def _compute_discussion_activity_score(model_info: Any) -> float:
    """
    Compute discussion/PR activity score based on community conversations.

    Actual discussions and pull requests indicate peer review activity.

    Scoring based on total discussion count:
    - 0 discussions: 0.0
    - 1-2 discussions: 0.2
    - 3-5 discussions: 0.4
    - 6-10 discussions: 0.6
    - 11-20 discussions: 0.8
    - 21+ discussions: 1.0

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    if not get_repo_discussions:
        logger.debug("get_repo_discussions not available")
        return 0.0

    try:
        model_id = getattr(model_info, "id", None)
        if not model_id:
            return 0.0

        # Get discussions list
        discussions = list(get_repo_discussions(repo_id=model_id, repo_type="model"))
        discussion_count = len(discussions)

        # Graduated scoring based on discussion count
        if discussion_count == 0:
            return 0.0
        elif discussion_count <= 2:
            return 0.2
        elif discussion_count <= 5:
            return 0.4
        elif discussion_count <= 10:
            return 0.6
        elif discussion_count <= 20:
            return 0.8
        else:
            return 1.0

    except Exception as e:
        logger.debug(f"Error computing discussion activity: {e}")
        return 0.0


def compute_reviewedness_metric(model_info: Any) -> float:
    """
    Compute reviewedness score using multiple indicators.

    Combines five components to measure review activity:
    - Author diversity (30%): Multiple contributors/orgs suggest collaboration/review
    - Community engagement (20%): High likes/downloads suggest scrutiny (tuned scaling)
    - Publication evidence (20%): Peer-reviewed papers indicate academic review (graduated)
    - Discussion/PR activity (20%): Actual community review conversations
    - Model card completeness (10%): Well-documented models get more scrutiny

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Reviewedness score between 0.0 and 1.0
    """
    try:
        # Fetch README for publication and completeness checks
        readme_content = _fetch_readme_content(model_info)

        # Component scores
        author_score = _compute_author_diversity_score(model_info)
        engagement_score = _compute_community_engagement_score(model_info)
        publication_score = _check_publication_evidence(readme_content)
        discussion_score = _compute_discussion_activity_score(model_info)
        completeness_score = _compute_model_card_completeness(model_info, readme_content)

        # Weighted combination (new weights)
        final_score = (
            author_score * 0.30 +
            engagement_score * 0.20 +
            publication_score * 0.20 +
            discussion_score * 0.20 +
            completeness_score * 0.10
        )

        # Ensure score is within bounds
        final_score = max(0.0, min(1.0, final_score))

        logger.debug(
            f"Reviewedness scores - authors: {author_score:.2f}, "
            f"engagement: {engagement_score:.2f}, publication: {publication_score:.2f}, "
            f"discussions: {discussion_score:.2f}, completeness: {completeness_score:.2f}, "
            f"final: {final_score:.2f}"
        )

        return round(final_score, 4)

    except Exception as e:
        logger.error(f"Error computing reviewedness metric: {e}")
        return 0.0
