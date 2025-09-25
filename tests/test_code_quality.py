from src.metrics.code_quality import compute_code_quality_metric


def test_code_quality_default_returns_one():
    # Current implementation always returns 1.0
    result = compute_code_quality_metric({})
    assert result == 1.0


def test_code_quality_ignores_input_fields():
    # Ensure extra fields do not change the constant score
    dummy = {"files": ["a.py"], "issues": 42}
    result = compute_code_quality_metric(dummy)
    assert result == 1.0
