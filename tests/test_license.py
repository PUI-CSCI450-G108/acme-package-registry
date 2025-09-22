import pytest
from unittest.mock import patch

from src.metrics.license import compute_license_metric

class MockModelInfo:
    def __init__(self, repo_id, cardData=None):
        self.id = repo_id
        self.cardData = cardData if cardData is not None else {}

@pytest.mark.parametrize(
    "license_id, expected_score",
    [
        ("apache-2.0", 1.0), # Compatible
        ("mit", 1.0),        # Compatible
        ("lgpl-2.1", 1.0),   # Compatible
        ("gpl-3.0", 0.0),    # Incompatible
        ("agpl-3.0", 0.0),   # Incompatible
        ("cc-by-nc-sa-4.0", 0.0), # Incompatible
        ("unknown-license", 0.5), # Unclear
        (None, 0.5),         # Unclear
    ],
)
def test_license_from_card_data(license_id, expected_score):
    """Tests license metric using the structured cardData."""
    model_info = MockModelInfo("mock/repo", cardData={"license": license_id})
    score = compute_license_metric(model_info)
    assert score == expected_score

@patch("src.license._fetch_readme_content")
def test_license_from_readme_compatible(mock_fetch):
    """Tests finding a compatible license in the README."""
    mock_fetch.return_value = "## License\nThis model is licensed under the Apache 2.0 license."
    model_info = MockModelInfo("mock/repo")
    score = compute_license_metric(model_info)
    assert score == 1.0

@patch("src.license._fetch_readme_content")
def test_license_from_readme_incompatible(mock_fetch):
    """Tests finding an incompatible license in the README."""
    mock_fetch.return_value = "## License\nThis is AGPL-3.0."
    model_info = MockModelInfo("mock/repo")
    score = compute_license_metric(model_info)
    assert score == 0.0

@patch("src.license._fetch_readme_content")
def test_license_unclear_from_readme(mock_fetch):
    """Tests when the README has no license section."""
    mock_fetch.return_value = "This is a model."
    model_info = MockModelInfo("mock/repo")
    score = compute_license_metric(model_info)
    assert score == 0.5

def test_license_no_info():
    """Tests when there is no cardData and the README can't be fetched."""
    # The mock will default to returning an empty string, simulating a failed fetch
    with patch("src.license._fetch_readme_content", return_value=""):
        model_info = MockModelInfo("mock/repo")
        score = compute_license_metric(model_info)
        assert score == 0.5