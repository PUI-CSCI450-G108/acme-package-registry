from types import SimpleNamespace
from typing import List

import pytest

import src.metrics.bus_factor as bus_factor
from src.metrics.bus_factor import compute_bus_factor_metric


class DummyModelInfo:
    def __init__(self, repo_id: str) -> None:
        self.id = repo_id


class FakeApi:
    def __init__(self, commits: List[object]) -> None:
        self._commits = commits

    def list_repo_commits(self, repo_id: str, repo_type: str = "model"):
        return self._commits


def test_bus_factor_multiple_authors(monkeypatch: pytest.MonkeyPatch) -> None:
    # authors list present in entries (GitCommitInfo-like)
    commits = [
        SimpleNamespace(authors=["alice"]),
        SimpleNamespace(authors=["bob", "carol"]),
        SimpleNamespace(authors=["alice"]),
        SimpleNamespace(authors=["bob"]),
    ]

    # Patch the API used inside the module under test
    monkeypatch.setattr(
        "src.metrics.bus_factor.hf_api.HuggingFaceAPI",  # type: ignore[attr-defined]
        lambda token=None: FakeApi(commits),
        raising=True,
    )

    model = DummyModelInfo("org/model")
    # counts: alice=2, bob=2, carol=1 → gini ≈ 0.1333
    score = compute_bus_factor_metric(model)
    assert pytest.approx(score, rel=1e-3, abs=1e-3) == 0.1333


def test_bus_factor_no_commits_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    commits: List[object] = []
    monkeypatch.setattr(
        "src.metrics.bus_factor.hf_api.HuggingFaceAPI",  # type: ignore[attr-defined]
        lambda token=None: FakeApi(commits),
        raising=True,
    )

    model = DummyModelInfo("org/empty")
    score = compute_bus_factor_metric(model)
    assert score == 0.0


def test_count_commits_api_handles_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class RaisingApi:
        def list_repo_commits(self, repo_id: str, repo_type: str = "model"):
            raise RuntimeError("network down")

    monkeypatch.setenv("HF_TOKEN", "dummy")
    monkeypatch.setattr(
        "src.metrics.bus_factor.hf_api.HuggingFaceAPI",  # type: ignore[attr-defined]
        lambda token=None: RaisingApi(),
        raising=True,
    )

    counts = bus_factor._count_commits_by_author_api("org/model")
    assert counts == {}


def test_gini_edge_cases() -> None:
    # single contributor → 0.0
    assert bus_factor._gini_from_counts([5]) == 0.0
    # zero totals → 0.0
    assert bus_factor._gini_from_counts([0, 0, 0]) == 0.0


def test_invalid_model_returns_zero() -> None:
    assert compute_bus_factor_metric({}) == 0.0


def test_gini_clamped_via_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force gini out of bounds to hit clamp branches
    monkeypatch.setattr("src.metrics.bus_factor._count_commits_by_author_api", lambda *a, **k: {"a": 1}, raising=True)
    monkeypatch.setattr("src.metrics.bus_factor._gini_from_counts", lambda counts: -0.5, raising=True)
    assert compute_bus_factor_metric({"id": "org/model"}) == 0.0

    monkeypatch.setattr("src.metrics.bus_factor._gini_from_counts", lambda counts: 1.5, raising=True)
    assert compute_bus_factor_metric({"id": "org/model"}) == 1.0


def test_top_level_exception_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Make the internal API function raise to exercise the outer try/except
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.metrics.bus_factor._count_commits_by_author_api", boom, raising=True)
    assert compute_bus_factor_metric({"id": "org/model"}) == 0.0


