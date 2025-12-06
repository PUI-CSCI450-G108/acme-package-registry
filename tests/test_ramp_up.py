from unittest.mock import Mock, patch
import pytest

from src.metrics.ramp_up import compute_ramp_up_metric


class MockModelInfo:
    def __init__(self, repo_id, siblings=None, tags=None):
        self.id = repo_id
        self.siblings = siblings or []
        self.tags = tags or []


class MockSibling:
    def __init__(self, filename):
        self.rfilename = filename


# ===== LLM Path Tests (3 tests) =====

@patch("src.metrics.ramp_up._fetch_readme_content")
@patch("src.LLM_endpoint.is_llm_available")
@patch("src.LLM_endpoint.score_with_llm")
def test_ramp_up_llm_continuous_score(mock_llm, mock_available, mock_fetch):
    """Test LLM path returns continuous score (e.g., 0.85)."""
    mock_available.return_value = True
    mock_llm.return_value = 0.85
    mock_fetch.return_value = """
# Awesome Model

## Quick Start
Get started quickly with this model.

## Installation
pip install awesome-model

## Usage
```python
from awesome import Model
model = Model()
```
"""

    model = MockModelInfo("org/model")
    score = compute_ramp_up_metric(model)

    assert score == 0.85
    mock_llm.assert_called_once()
    # Verify correct task and context structure
    call_args = mock_llm.call_args
    assert call_args[0][0] == "ramp_up"
    assert "has_examples" in call_args[0][2]


@patch("src.metrics.ramp_up._fetch_readme_content")
@patch("src.LLM_endpoint.is_llm_available")
@patch("src.LLM_endpoint.score_with_llm")
def test_ramp_up_llm_failure_falls_back_to_heuristic(mock_llm, mock_available, mock_fetch):
    """Test fallback to heuristic when LLM fails."""
    mock_available.return_value = True
    mock_llm.return_value = None  # LLM failure
    mock_fetch.return_value = """
# Model

## Installation
pip install package

## Usage
```python
import package
```
"""

    model = MockModelInfo("org/model")
    score = compute_ramp_up_metric(model)

    # Should fall back to heuristic
    # Installation (0.3) + Usage (0.3) + Code blocks (0.25) + Structure partial (0.075) = 0.925
    assert score == 0.925


@patch("src.metrics.ramp_up._fetch_readme_content")
@patch("src.LLM_endpoint.is_llm_available")
@patch("src.LLM_endpoint.score_with_llm")
def test_ramp_up_llm_with_various_scores(mock_llm, mock_available, mock_fetch):
    """Test LLM can return various continuous scores."""
    mock_available.return_value = True
    mock_fetch.return_value = "# Model\n\nSome documentation."

    model = MockModelInfo("org/model")

    # Test score 0.3 (poor)
    mock_llm.return_value = 0.3
    assert compute_ramp_up_metric(model) == 0.3

    # Test score 0.65 (adequate)
    mock_llm.return_value = 0.65
    assert compute_ramp_up_metric(model) == 0.65

    # Test score 0.95 (excellent)
    mock_llm.return_value = 0.95
    assert compute_ramp_up_metric(model) == 0.95


# ===== Heuristic Path Tests (3 tests) =====

@patch("src.metrics.ramp_up._fetch_readme_content")
@patch("src.LLM_endpoint.is_llm_available")
def test_ramp_up_heuristic_excellent(mock_available, mock_fetch):
    """Test heuristic scoring for excellent README (all sections)."""
    mock_available.return_value = False  # Force heuristic path
    mock_fetch.return_value = """
# Awesome Model

## Getting Started
Quick introduction to the model.

## Installation
pip install awesome-model

## Usage
Here's how to use it:
```python
from awesome import Model
model = Model()
result = model.predict(data)
```

## Examples
More examples here.

## API Reference
Detailed API docs.
"""

    model = MockModelInfo("org/model")
    score = compute_ramp_up_metric(model)

    # Installation (0.3) + Usage (0.3) + Code (0.25) + Structure (0.15) = 1.0
    assert score == 1.0


@patch("src.metrics.ramp_up._fetch_readme_content")
@patch("src.LLM_endpoint.is_llm_available")
def test_ramp_up_heuristic_partial(mock_available, mock_fetch):
    """Test heuristic scoring for partial README (some sections)."""
    mock_available.return_value = False
    mock_fetch.return_value = """
# Model

## Usage
You can use this model for inference.

Some additional text about the model capabilities.
"""

    model = MockModelInfo("org/model")
    score = compute_ramp_up_metric(model)

    # Usage (0.3) + Structure partial (0.075) = 0.375
    assert score == pytest.approx(0.375, abs=0.01)


@patch("src.metrics.ramp_up._fetch_readme_content")
@patch("src.LLM_endpoint.is_llm_available")
def test_ramp_up_heuristic_with_example_files_bonus(mock_available, mock_fetch):
    """Test heuristic gives bonus when code example files exist."""
    mock_available.return_value = False
    mock_fetch.return_value = """
# Model

## Installation
pip install model

## Usage
Run the example.py file to see it in action.
"""

    siblings = [MockSibling("example.py"), MockSibling("inference.ipynb")]
    model = MockModelInfo("org/model", siblings=siblings)
    score = compute_ramp_up_metric(model)

    # Installation (0.3) + Usage (0.3) + Structure partial (0.075) + Example files (0.1) = 0.775
    assert score == pytest.approx(0.775, abs=0.01)


# ===== Edge Cases (2 tests) =====

@patch("src.metrics.ramp_up._fetch_readme_content")
def test_ramp_up_no_readme(mock_fetch):
    """Test score is 0.0 when no README exists."""
    mock_fetch.return_value = ""

    model = MockModelInfo("org/model")
    score = compute_ramp_up_metric(model)

    assert score == 0.0


@patch("src.metrics.ramp_up._fetch_readme_content")
@patch("src.LLM_endpoint.is_llm_available")
def test_ramp_up_empty_or_very_short_readme(mock_available, mock_fetch):
    """Test score is 0.0 for empty or very short README."""
    mock_available.return_value = False

    model = MockModelInfo("org/model")

    # Whitespace only
    mock_fetch.return_value = "   \n\n  "
    assert compute_ramp_up_metric(model) == 0.0

    # Very short (< 50 chars)
    mock_fetch.return_value = "Model"
    assert compute_ramp_up_metric(model) == 0.0
