import json
from unittest.mock import patch

from src.orchestrator import calculate_all_metrics


class DummyModelInfo:
    def __init__(self, repo_id: str):
        self.id = repo_id


def test_orchestrator_smoke(monkeypatch):
    dummy = DummyModelInfo("org/model")

    # Provide deterministic fake metric outputs (patch inside orchestrator namespace because of direct imports)
    monkeypatch.setattr("src.orchestrator.compute_ramp_up_metric", lambda m: 0.5)
    monkeypatch.setattr("src.orchestrator.compute_bus_factor_metric", lambda m: 0.4)
    monkeypatch.setattr("src.orchestrator.compute_license_metric", lambda m: 1.0)
    monkeypatch.setattr(
        "src.orchestrator.compute_size_metric",
        lambda m: {"raspberry_pi": 0.2, "jetson_nano": 0.4, "desktop_pc": 0.8, "aws_server": 1.0},
    )
    monkeypatch.setattr("src.orchestrator.compute_dataset_code_avail_metric", lambda m: 0.6)
    monkeypatch.setattr("src.orchestrator.compute_dataset_quality_metric", lambda m: 0.7)
    monkeypatch.setattr("src.orchestrator.compute_code_quality_metric", lambda m: 0.9)
    monkeypatch.setattr("src.orchestrator.compute_perf_claims_metric", lambda m: 0.3)

    # Patch net score separately to isolate orchestrator flow OR let it compute
    # We'll let it compute naturally; net score uses these values.

    # Prevent README/network access in metrics that inspect repo files
    monkeypatch.setattr("src.metrics.ramp_up.HfFileSystem", lambda: type("FS", (), {"ls": lambda self, repo_id, detail=False: [f"{repo_id}/README.md"]})())
    monkeypatch.setattr("src.metrics.ramp_up.hf_hub_download", lambda **kwargs: __file__)
    monkeypatch.setattr("src.metrics.license.HfFileSystem", lambda: type("FS", (), {"ls": lambda self, repo_id, detail=False: [f"{repo_id}/README.md"]})())
    monkeypatch.setattr("src.metrics.license.hf_hub_download", lambda **kwargs: __file__)
    monkeypatch.setattr("src.metrics.dataset_code_avail.HfFileSystem", lambda: type("FS", (), {"ls": lambda self, repo_id, detail=False: [f"{repo_id}/README.md"]})())
    monkeypatch.setattr("src.metrics.dataset_code_avail.hf_hub_download", lambda **kwargs: __file__)

    output_json = calculate_all_metrics(dummy, "https://huggingface.co/org/model")
    data = json.loads(output_json)

    # Core keys present
    for key in [
        "name",
        "category",
        "net_score",
        "ramp_up_time",
        "bus_factor",
        "license",
        "size_score",
        "dataset_and_code_score",
        "dataset_quality",
        "code_quality",
        "performance_claims",
    ]:
        assert key in data

    assert data["name"] == "org/model"
    assert data["category"] == "MODEL"

    # Spot check a couple of values
    assert data["ramp_up_time"] == 0.5
    assert data["size_score"]["raspberry_pi"] == 0.2

    # Net score should be between 0 and 1
    assert 0.0 <= data["net_score"] <= 1.0

    # Latency keys exist and are integers
    latency_keys = [k for k in data.keys() if k.endswith("_latency")]
    assert latency_keys
    for lk in latency_keys:
        assert isinstance(data[lk], int)
        assert data[lk] >= 0
