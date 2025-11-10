"""
Tests for reproducibility metric.
"""

import pytest
from unittest.mock import patch
from src.metrics.reproducibility import compute_reproducibility_metric


class MockSibling:
    def __init__(self, filename):
        self.rfilename = filename


class MockModelInfo:
    def __init__(self, repo_id, cardData=None, siblings=None):
        self.id = repo_id
        self.cardData = cardData if cardData is not None else {}
        self.siblings = siblings if siblings is not None else []


@patch("src.metrics.reproducibility._fetch_readme_content")
def test_reproducibility_all_elements_present(mock_fetch):
    """Test perfect reproducibility score with all elements."""
    mock_fetch.return_value = """
    # Training

    This model was trained with the following hyperparameters:
    - Random seed: 42
    - Training procedure described below

    ## Fine-tuning

    Instructions for reproducing results.
    """

    siblings = [
        MockSibling("train.py"),
        MockSibling("config.json"),
        MockSibling("requirements.txt"),
        MockSibling("model.safetensors"),
    ]

    model_info = MockModelInfo(
        "test/model",
        cardData={"datasets": ["squad", "glue"]},
        siblings=siblings,
    )

    score = compute_reproducibility_metric(model_info)

    # Should have high score with all elements
    assert 0.8 <= score <= 1.0


@patch("src.metrics.reproducibility._fetch_readme_content")
def test_reproducibility_partial_elements(mock_fetch):
    """Test partial reproducibility score."""
    mock_fetch.return_value = "Basic model description."

    siblings = [
        MockSibling("config.json"),
        MockSibling("model.safetensors"),
    ]

    model_info = MockModelInfo(
        "test/model", cardData={"datasets": ["squad"]}, siblings=siblings
    )

    score = compute_reproducibility_metric(model_info)

    # Should have moderate score with some elements
    assert 0.3 <= score <= 0.7


@patch("src.metrics.reproducibility._fetch_readme_content")
def test_reproducibility_no_elements(mock_fetch):
    """Test zero reproducibility score with no elements."""
    mock_fetch.return_value = ""

    model_info = MockModelInfo("test/model", cardData={}, siblings=[])

    score = compute_reproducibility_metric(model_info)

    # Should have very low or zero score
    assert 0.0 <= score <= 0.2


@patch("src.metrics.reproducibility._fetch_readme_content")
def test_reproducibility_training_code_detection(mock_fetch):
    """Test detection of training scripts."""
    mock_fetch.return_value = ""

    siblings = [
        MockSibling("train_model.py"),
        MockSibling("finetune.py"),
        MockSibling("inference.py"),  # Not training
    ]

    model_info = MockModelInfo("test/model", siblings=siblings)

    score = compute_reproducibility_metric(model_info)

    # Should have non-zero score for training code
    assert score > 0.2


@patch("src.metrics.reproducibility._fetch_readme_content")
def test_reproducibility_config_files(mock_fetch):
    """Test detection of configuration files."""
    mock_fetch.return_value = ""

    siblings = [
        MockSibling("config.json"),
        MockSibling("training_args.json"),
        MockSibling("hyperparams.yaml"),
    ]

    model_info = MockModelInfo("test/model", siblings=siblings)

    score = compute_reproducibility_metric(model_info)

    # Should have non-zero score for config files
    assert score > 0.2


@patch("src.metrics.reproducibility._fetch_readme_content")
def test_reproducibility_error_handling(mock_fetch):
    """Test error handling returns 0.0."""
    mock_fetch.side_effect = Exception("Test error")

    model_info = MockModelInfo("test/model")

    score = compute_reproducibility_metric(model_info)

    assert score == 0.0


def test_reproducibility_score_bounds():
    """Test that score is always within [0, 1]."""
    model_info = MockModelInfo("test/model")

    with patch("src.metrics.reproducibility._fetch_readme_content", return_value=""):
        score = compute_reproducibility_metric(model_info)

    assert 0.0 <= score <= 1.0
