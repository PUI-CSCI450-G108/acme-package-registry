"""
Tests for reviewedness metric.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.metrics.reviewedness import compute_reviewedness_metric


class MockCommit:
    def __init__(self, authors):
        self.authors = authors


class MockModelInfo:
    def __init__(self, repo_id, likes=0, downloads=0):
        self.id = repo_id
        self.likes = likes
        self.downloads = downloads


@patch("src.metrics.reviewedness._fetch_readme_content")
@patch("src.metrics.reviewedness._compute_author_diversity_score")
@patch("src.metrics.reviewedness._compute_community_engagement_score")
def test_reviewedness_high_score(mock_engagement, mock_authors, mock_fetch):
    """Test high reviewedness score with all factors."""
    mock_authors.return_value = 1.0  # 5+ authors
    mock_engagement.return_value = 0.8  # High engagement
    mock_fetch.return_value = "Paper: https://arxiv.org/abs/2101.00000"

    model_info = MockModelInfo("test/model", likes=5000, downloads=100000)

    score = compute_reviewedness_metric(model_info)

    # Should have high score
    assert 0.7 <= score <= 1.0


@patch("src.metrics.reviewedness._fetch_readme_content")
@patch("src.metrics.reviewedness._compute_author_diversity_score")
@patch("src.metrics.reviewedness._compute_community_engagement_score")
def test_reviewedness_low_score(mock_engagement, mock_authors, mock_fetch):
    """Test low reviewedness score with minimal factors."""
    mock_authors.return_value = 0.0  # 1 author
    mock_engagement.return_value = 0.1  # Low engagement
    mock_fetch.return_value = "Basic model"

    model_info = MockModelInfo("test/model", likes=5, downloads=100)

    score = compute_reviewedness_metric(model_info)

    # Should have low score
    assert 0.0 <= score <= 0.3


@patch("src.hf_api.HuggingFaceAPI")
def test_reviewedness_author_diversity_single(mock_api_class):
    """Test author diversity with single author."""
    from src.metrics.reviewedness import _compute_author_diversity_score

    mock_api = MagicMock()
    mock_api.list_repo_commits.return_value = [
        MockCommit(["author1"]),
        MockCommit(["author1"]),
    ]
    mock_api_class.return_value = mock_api

    model_info = MockModelInfo("test/model")
    score = _compute_author_diversity_score(model_info)

    # Single author should get 0.0
    assert score == 0.0


@patch("src.hf_api.HuggingFaceAPI")
def test_reviewedness_author_diversity_multiple(mock_api_class):
    """Test author diversity with multiple authors."""
    from src.metrics.reviewedness import _compute_author_diversity_score

    mock_api = MagicMock()
    mock_api.list_repo_commits.return_value = [
        MockCommit(["author1"]),
        MockCommit(["author2"]),
        MockCommit(["author3"]),
        MockCommit(["author1"]),  # Duplicate
    ]
    mock_api_class.return_value = mock_api

    model_info = MockModelInfo("test/model")
    score = _compute_author_diversity_score(model_info)

    # 3 authors should get 0.6
    assert score == 0.6


def test_reviewedness_community_engagement_high():
    """Test community engagement with high metrics."""
    from src.metrics.reviewedness import _compute_community_engagement_score

    model_info = MockModelInfo("test/model", likes=10000, downloads=1000000)
    score = _compute_community_engagement_score(model_info)

    # High engagement should give high score
    assert score > 0.8


def test_reviewedness_community_engagement_low():
    """Test community engagement with low metrics."""
    from src.metrics.reviewedness import _compute_community_engagement_score

    model_info = MockModelInfo("test/model", likes=0, downloads=0)
    score = _compute_community_engagement_score(model_info)

    # Low engagement should give low score
    assert score < 0.3


def test_reviewedness_publication_evidence():
    """Test publication detection."""
    from src.metrics.reviewedness import _check_publication_evidence

    # Test arXiv detection
    readme = "Our paper: https://arxiv.org/abs/2101.00000"
    assert _check_publication_evidence(readme) == 1.0

    # Test DOI detection
    readme = "DOI: 10.1234/example"
    assert _check_publication_evidence(readme) == 1.0

    # Test conference detection
    readme = "Published at NeurIPS 2024"
    assert _check_publication_evidence(readme) == 1.0

    # Test no publication
    readme = "Just a basic model"
    assert _check_publication_evidence(readme) == 0.0


@patch("src.metrics.reviewedness._fetch_readme_content")
@patch("src.metrics.reviewedness._compute_author_diversity_score")
@patch("src.metrics.reviewedness._compute_community_engagement_score")
def test_reviewedness_error_handling(mock_engagement, mock_authors, mock_fetch):
    """Test error handling returns 0.0."""
    mock_authors.side_effect = Exception("Test error")
    mock_engagement.return_value = 0.0
    mock_fetch.return_value = ""

    model_info = MockModelInfo("test/model")

    score = compute_reviewedness_metric(model_info)

    assert score == 0.0


def test_reviewedness_score_bounds():
    """Test that score is always within [0, 1]."""
    model_info = MockModelInfo("test/model")

    with patch("src.metrics.reviewedness._fetch_readme_content", return_value=""):
        with patch(
            "src.metrics.reviewedness._compute_author_diversity_score", return_value=0.5
        ):
            with patch(
                "src.metrics.reviewedness._compute_community_engagement_score",
                return_value=0.5,
            ):
                score = compute_reviewedness_metric(model_info)

    assert 0.0 <= score <= 1.0
