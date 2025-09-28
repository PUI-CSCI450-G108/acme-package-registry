from src.metrics.code_quality import compute_code_quality_metric


class Sibling:
    def __init__(self, name: str):
        self.rfilename = name


class DummyModel:
    def __init__(self, rid: str, sibs=None):
        self.id = rid
        self.siblings = sibs or []


def test_code_quality_good_docs_and_style(monkeypatch):
    # README contains usage section, repo has pyproject.toml (style) and snake_case file
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: "# Model\n\n## Usage\nRun this example...",
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
