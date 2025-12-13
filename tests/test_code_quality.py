from unittest.mock import patch
import pytest

from src.metrics.code_quality import compute_code_quality_metric


# Mock LLM to be unavailable so tests use heuristic fallback
@pytest.fixture(autouse=True)
def mock_llm_unavailable():
    with patch("src.LLM_endpoint.is_llm_available", return_value=False):
        yield


class Sibling:
    def __init__(self, name: str):
        self.rfilename = name


class DummyModel:
    def __init__(self, rid: str, sibs=None):
        self.id = rid
        self.siblings = sibs or []


def test_code_quality_good_docs_and_style(monkeypatch):
    # README contains usage section with code examples
    readme = """# Model

## Installation
pip install this-model

## Usage
Here's how to use this model:

```python
from model import Model
model = Model()
result = model.predict(data)
```

This provides a comprehensive guide to using the model.
"""
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: readme,
    )
    model = DummyModel("org/model", [Sibling("pyproject.toml"), Sibling("utils_helper.py")])
    assert compute_code_quality_metric(model) == 1.0


def test_code_quality_some_issues_returns_half(monkeypatch):
    # No docs; code exists but not snake_case, no style files
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: "",
    )
    model = DummyModel("org/model", [Sibling("main.py")])
    assert compute_code_quality_metric(model) == 0.5


def test_code_quality_no_docs_no_code_returns_zero(monkeypatch):
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: "",
    )
    model = DummyModel("org/model", [])
    assert compute_code_quality_metric(model) == 0.0
