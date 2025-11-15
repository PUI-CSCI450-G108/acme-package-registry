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
@patch("src.metrics.reviewedness._compute_discussion_activity_score")
@patch("src.metrics.reviewedness._compute_model_card_completeness")
def test_reviewedness_high_score(mock_completeness, mock_discussions, mock_engagement, mock_authors, mock_fetch):
    """Test high reviewedness score with all factors."""
    mock_authors.return_value = 1.0  # 5+ authors
    mock_engagement.return_value = 0.8  # High engagement
    mock_discussions.return_value = 1.0  # Many discussions
    mock_completeness.return_value = 1.0  # Complete model card
    mock_fetch.return_value = "Paper: https://arxiv.org/abs/2101.00000 at NeurIPS conference"

    model_info = MockModelInfo("test/model", likes=5000, downloads=100000)

    score = compute_reviewedness_metric(model_info)

    # New weights: 0.30*1.0 + 0.20*0.8 + 0.20*1.0 + 0.20*1.0 + 0.10*1.0 = 0.96
    assert 0.90 <= score <= 1.0


@patch("src.metrics.reviewedness._fetch_readme_content")
@patch("src.metrics.reviewedness._compute_author_diversity_score")
@patch("src.metrics.reviewedness._compute_community_engagement_score")
@patch("src.metrics.reviewedness._compute_discussion_activity_score")
@patch("src.metrics.reviewedness._compute_model_card_completeness")
def test_reviewedness_low_score(mock_completeness, mock_discussions, mock_engagement, mock_authors, mock_fetch):
    """Test low reviewedness score with minimal factors."""
    mock_authors.return_value = 0.0  # 1 author
    mock_engagement.return_value = 0.1  # Low engagement
    mock_discussions.return_value = 0.0  # No discussions
    mock_completeness.return_value = 0.2  # Minimal documentation
    mock_fetch.return_value = "Basic model"

    model_info = MockModelInfo("test/model", likes=5, downloads=100)

    score = compute_reviewedness_metric(model_info)

    # New weights: 0.30*0.0 + 0.20*0.1 + 0.20*0.0 + 0.20*0.0 + 0.10*0.2 = 0.04
    assert 0.0 <= score <= 0.1


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

    # With new formula: engagement = 10000/2000 + 1000000/50000 = 5 + 20 = 25
    # score = 1/(1 + exp(-0.5*25 + 3)) = very close to 1.0
    # High engagement should give high score, but allow for some variation
    assert score > 0.9


def test_reviewedness_community_engagement_low():
    """Test community engagement with low metrics."""
    from src.metrics.reviewedness import _compute_community_engagement_score

    model_info = MockModelInfo("test/model", likes=0, downloads=0)
    score = _compute_community_engagement_score(model_info)

    # Low engagement should give low score
    assert score < 0.3


def test_reviewedness_publication_evidence():
    """Test publication detection with graduated scoring."""
    from src.metrics.reviewedness import _check_publication_evidence

    # Test full evidence (venue + identifier) = 1.0
    readme = "Our paper: https://arxiv.org/abs/2101.00000 at NeurIPS 2024"
    assert _check_publication_evidence(readme) == 1.0

    # Test DOI with venue = 1.0
    readme = "DOI: 10.1234/example. Published in journal."
    assert _check_publication_evidence(readme) == 1.0

    # Test arXiv only (identifier without venue) = 0.5
    readme = "Our paper: https://arxiv.org/abs/2101.00000"
    assert _check_publication_evidence(readme) == 0.5

    # Test conference only (venue without identifier) = 0.5
    readme = "Published at NeurIPS 2024"
    assert _check_publication_evidence(readme) == 0.5

    # Test no publication = 0.0
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
                with patch(
                    "src.metrics.reviewedness._compute_discussion_activity_score",
                    return_value=0.5,
                ):
                    with patch(
                        "src.metrics.reviewedness._compute_model_card_completeness",
                        return_value=0.5,
                    ):
                        score = compute_reviewedness_metric(model_info)

    assert 0.0 <= score <= 1.0


def test_reviewedness_model_card_completeness():
    """Test model card completeness scoring."""
    from src.metrics.reviewedness import _compute_model_card_completeness

    # Create mock model with complete metadata
    class CompleteModel:
        id = "test/model"
        tags = ["tag1", "tag2"]
        cardData = {
            "license": "MIT",
            "datasets": ["dataset1"],
            "base_model": "parent/model"
        }

    long_readme = "x" * 1500  # >1000 chars
    score = _compute_model_card_completeness(CompleteModel(), long_readme)

    # 0.3 (readme) + 0.2 (tags) + 0.2 (license) + 0.2 (datasets) + 0.1 (base_model) = 1.0
    assert score == pytest.approx(1.0)

    # Test minimal model
    class MinimalModel:
        id = "test/model"
        tags = []
        cardData = {}

    score = _compute_model_card_completeness(MinimalModel(), "")
    assert score == pytest.approx(0.0)


def test_reviewedness_discussion_activity():
    """Test discussion activity scoring."""
    from src.metrics.reviewedness import _compute_discussion_activity_score

    # Test with get_repo_discussions available
    with patch("src.metrics.reviewedness.get_repo_discussions") as mock_get_discussions:
        # Test no discussions
        mock_get_discussions.return_value = []
        model_info = MockModelInfo("test/model")
        score = _compute_discussion_activity_score(model_info)
        assert score == 0.0

        # Test 1-2 discussions
        mock_discussions = [MagicMock() for _ in range(2)]
        mock_get_discussions.return_value = mock_discussions
        score = _compute_discussion_activity_score(model_info)
        assert score == 0.2

        # Test 3-5 discussions
        mock_discussions = [MagicMock() for _ in range(4)]
        mock_get_discussions.return_value = mock_discussions
        score = _compute_discussion_activity_score(model_info)
        assert score == 0.4

        # Test 21+ discussions
        mock_discussions = [MagicMock() for _ in range(25)]
        mock_get_discussions.return_value = mock_discussions
        score = _compute_discussion_activity_score(model_info)
        assert score == 1.0
