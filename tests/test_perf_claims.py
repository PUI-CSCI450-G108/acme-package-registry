from src.metrics.perf_claims import compute_perf_claims_metric


class DummyModel:
    def __init__(self, rid: str, card=None):
        self.id = rid
        self.cardData = card or {}


def test_perf_claims_strong_from_table(monkeypatch):
    # README with markdown table and metrics and numbers
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: """
        | Benchmark | Accuracy |
        |-----------|----------|
        | GLUE      | 92.3%    |
        """,
    )
    model = DummyModel("org/model")
    assert compute_perf_claims_metric(model) == 1.0


def test_perf_claims_medium_when_vague(monkeypatch):
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: "This model has strong benchmark performance and good evaluation results.",
    )
    model = DummyModel("org/model")
    assert compute_perf_claims_metric(model) == 0.5


def test_perf_claims_carddata_counts_as_strong(monkeypatch):
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: "",
    )
    model = DummyModel("org/model", card={"metrics": {"accuracy": 0.9}})
    assert compute_perf_claims_metric(model) == 1.0


def test_perf_claims_none_returns_zero(monkeypatch):
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: "",
    )
    model = DummyModel("org/model")
    assert compute_perf_claims_metric(model) == 0.0


def test_perf_claims_tier1_returns_zero_for_substantial_readme_no_perf(monkeypatch):
    # Substantial README with no performance mentions should return 0.0 from Tier 1
    monkeypatch.setattr(
        "src.metrics.dataset_code_avail._fetch_readme_content",
        lambda m: """
        This is a language model for text generation.
        It was trained on a large corpus of text data.
        The model uses a transformer architecture.
        You can use it for various natural language processing tasks.
        Installation is simple: pip install our-package
        """,
    )
    model = DummyModel("org/model")
    assert compute_perf_claims_metric(model) == 0.0
