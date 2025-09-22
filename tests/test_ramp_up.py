import pytest
from unittest.mock import patch, mock_open
from src.metrics.ramp_up import compute_ramp_up_metric

# Mock model_info object for testing
class MockModelInfo:
    def __init__(self, repo_id):
        self.id = repo_id

@pytest.fixture
def mock_model_info():
    """Provides a mock model_info object."""
    return MockModelInfo("mock/repo")

@patch("src.ramp_up.hf_hub_download")
@patch("builtins.open", new_callable=mock_open)
def test_ramp_up_ideal_word_count(mock_file, mock_download, mock_model_info):
    """
    Tests the ramp-up score for a README with an ideal word count.
    The score should be very close to 1.0.
    """
    # Create a dummy README content with 1000 words
    ideal_readme = "word " * 1000
    mock_file.return_value.read.return_value = ideal_readme
    mock_download.return_value = "dummy/path/README.md"

    # The mock for fs.ls() needs to return a list containing a readme
    with patch("src.ramp_up.HfFileSystem") as mock_fs:
        mock_fs.return_value.ls.return_value = ["mock/repo/README.md"]
        score = compute_ramp_up_metric(mock_model_info)
        assert score == pytest.approx(1.0)

@patch("src.ramp_up.hf_hub_download")
@patch("builtins.open", new_callable=mock_open)
def test_ramp_up_very_short_readme(mock_file, mock_download, mock_model_info):
    """
    Tests the ramp-up score for a very short README.
    The score should be low.
    """
    short_readme = "word " * 10
    mock_file.return_value.read.return_value = short_readme
    mock_download.return_value = "dummy/path/README.md"

    with patch("src.ramp_up.HfFileSystem") as mock_fs:
        mock_fs.return_value.ls.return_value = ["mock/repo/README.md"]
        score = compute_ramp_up_metric(mock_model_info)
        assert score < 0.2

@patch("src.ramp_up.HfFileSystem")
def test_ramp_up_no_readme(mock_fs, mock_model_info):
    """
    Tests the ramp-up score when no README file is found.
    The score should be 0.0.
    """
    # Mock HfFileSystem().ls() to return an empty list
    mock_fs.return_value.ls.return_value = []
    score = compute_ramp_up_metric(mock_model_info)
    assert score == 0.0