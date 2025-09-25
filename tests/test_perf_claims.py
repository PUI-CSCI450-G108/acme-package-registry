from src.metrics.perf_claims import compute_perf_claims_metric


def test_perf_claims_returns_one_for_empty():
    assert compute_perf_claims_metric({}) == 1.0


def test_perf_claims_ignores_input_fields():
    dummy = {"benchmarks": ["glue", "squad"], "accuracy": 0.9}
    assert compute_perf_claims_metric(dummy) == 1.0
