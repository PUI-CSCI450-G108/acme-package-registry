from unittest.mock import patch

import pytest

from src.metrics.dataset_code_avail import compute_dataset_code_avail_metric


# Mock LLM to be unavailable so tests use heuristic fallback
@pytest.fixture(autouse=True)
def mock_llm_unavailable():
    with patch("src.LLM_endpoint.is_llm_available", return_value=False):
        yield


class MockSibling:
    def __init__(self, rfilename):
        self.rfilename = rfilename


class MockModelInfo:
    def __init__(self, repo_id, cardData=None, siblings=None):
        self.id = repo_id
        self.cardData = cardData if cardData is not None else {}
        self.siblings = siblings if siblings is not None else []


@patch("src.metrics.dataset_code_avail._fetch_readme_content")
def test_both_dataset_and_code_exist(mock_fetch):
    """Score should be 1.0 if dataset is in cardData and .py file exists."""
    mock_fetch.return_value = "Some readme content."
    model_info = MockModelInfo(
        "mock/repo",
        cardData={"datasets": ["some-dataset"]},
        siblings=[MockSibling("train.py")],
    )
    score = compute_dataset_code_avail_metric(model_info)
    assert score == 1.0


@patch("src.metrics.dataset_code_avail._fetch_readme_content")
def test_dataset_from_readme_and_code_from_ipynb(mock_fetch):
    """Score should be 1.0 if dataset is in README and .ipynb file exists."""
    mock_fetch.return_value = "This model was trained on the xyz dataset."
    model_info = MockModelInfo("mock/repo", siblings=[MockSibling("example.ipynb")])
    score = compute_dataset_code_avail_metric(model_info)
    assert score == 1.0


@patch("src.metrics.dataset_code_avail._fetch_readme_content")
def test_only_dataset_available(mock_fetch):
    """Score should be 0.5 if only dataset is mentioned in cardData."""
    mock_fetch.return_value = "Some readme content."
    model_info = MockModelInfo("mock/repo", cardData={"datasets": ["some-dataset"]})
    score = compute_dataset_code_avail_metric(model_info)
    assert score == 0.5


@patch("src.metrics.dataset_code_avail._fetch_readme_content")
def test_only_code_available(mock_fetch):
    """Score should be 0.5 if only a notebook is present."""
    mock_fetch.return_value = "Some readme content."
    model_info = MockModelInfo("mock/repo", siblings=[MockSibling("example.ipynb")])
    score = compute_dataset_code_avail_metric(model_info)
    assert score == 0.5


@patch("src.metrics.dataset_code_avail._fetch_readme_content")
def test_neither_available(mock_fetch):
    """Score should be 0.0 if neither dataset nor code is found."""
    mock_fetch.return_value = "This is a model."
    model_info = MockModelInfo("mock/repo")
    score = compute_dataset_code_avail_metric(model_info)
    assert score == 0.0
