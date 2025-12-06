from unittest.mock import patch

import pytest

from src.metrics.dataset_quality import compute_dataset_quality_metric


# Mock LLM to be unavailable so tests use heuristic fallback
@pytest.fixture(autouse=True)
def mock_llm_unavailable():
    with patch("src.LLM_endpoint.is_llm_available", return_value=False):
        yield


class MockModelInfo:
    def __init__(self, repo_id, cardData=None):
        self.id = repo_id
        self.cardData = cardData if cardData is not None else {}


def test_no_dataset_in_carddata_returns_zero():
    """If no dataset is linked in cardData, score is 0.0 regardless of README."""
    mi = MockModelInfo("mock/repo", cardData={})  # no 'datasets' key
    assert compute_dataset_quality_metric(mi) == 0.0


@patch("src.metrics.dataset_quality._fetch_readme_content")
@pytest.mark.parametrize("datasets_value", [["some-dataset"], "some-dataset"])
def test_dataset_named_but_no_readme_returns_half(mock_fetch, datasets_value):
    """If dataset exists but README can't be fetched, score is 0.5."""
    mock_fetch.return_value = ""  # simulate missing/failed README fetch
    mi = MockModelInfo("mock/repo", cardData={"datasets": datasets_value})
    assert compute_dataset_quality_metric(mi) == 0.5


@patch("src.metrics.dataset_quality._fetch_readme_content")
@pytest.mark.parametrize("datasets_value", [["some-dataset"], "some-dataset"])
def test_dataset_named_but_no_quality_keywords_returns_half(mock_fetch, datasets_value):
    """If dataset exists but README lacks quality keywords, score is 0.5."""
    # Updated: "dataset" is now a quality keyword, so this needs to not contain any keywords
    mock_fetch.return_value = (
        "This README mentions it but has no detailed fields."
    )
    mi = MockModelInfo("mock/repo", cardData={"datasets": datasets_value})
    assert compute_dataset_quality_metric(mi) == 0.5


@patch("src.metrics.dataset_quality._fetch_readme_content")
@pytest.mark.parametrize("datasets_value", [["some-dataset"], "some-dataset"])
def test_exactly_one_quality_keyword_returns_point_75(mock_fetch, datasets_value):
    """If one quality keyword is present, score is 0.75."""
    # One keyword: "size" - returns 0.75 (more discriminating)
    mock_fetch.return_value = "The dataset size is considerable."
    mi = MockModelInfo("mock/repo", cardData={"datasets": datasets_value})
    assert compute_dataset_quality_metric(mi) == 0.75


@patch("src.metrics.dataset_quality._fetch_readme_content")
@pytest.mark.parametrize("datasets_value", [["some-dataset"], "some-dataset"])
def test_two_or_more_quality_keywords_returns_one(mock_fetch, datasets_value):
    """If two or more quality keywords are present, score is 1.0."""
    # At least two: "size" and "split" (+ "features" for good measure)
    mock_fetch.return_value = (
        "We report dataset size, list of features, and the train/validation split."
    )
    mi = MockModelInfo("mock/repo", cardData={"datasets": datasets_value})
    assert compute_dataset_quality_metric(mi) == 1.0
