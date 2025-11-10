import math

from src.net_score import calculate_net_score


def test_net_score_all_max_scores():
    metrics = {
        "size_score": {"cpu": 1.0, "gpu": 1.0},
        "ramp_up_time": 1.0,
        "bus_factor": 1.0,
        "dataset_and_code_score": 1.0,
        "dataset_quality": 1.0,
        "code_quality": 1.0,
        "performance_claims": 1.0,
        "reproducibility": 1.0,
        "reviewedness": 1.0,
        "tree_score": 1.0,
        "license": 1.0,
    }
    score, latency = calculate_net_score(metrics)
    # Weighted sum: (0.08 + 6*0.12 + 3*0.10) / 1.10 = 1.10 / 1.10 = 1.0 then * license(1)=1
    assert score == 1.0
    assert latency >= 0


def test_net_score_license_zero_nullifies():
    metrics = {
        "size_score": {"cpu": 1.0},
        "ramp_up_time": 1.0,
        "bus_factor": 1.0,
        "dataset_and_code_score": 1.0,
        "dataset_quality": 1.0,
        "code_quality": 1.0,
        "performance_claims": 1.0,
        "reproducibility": 1.0,
        "reviewedness": 1.0,
        "tree_score": 1.0,
        "license": 0.0,
    }
    score, _ = calculate_net_score(metrics)
    assert score == 0.0


def test_net_score_missing_size_treated_as_zero():
    metrics = {
        # size_score missing
        "ramp_up_time": 1.0,
        "bus_factor": 1.0,
        "dataset_and_code_score": 1.0,
        "dataset_quality": 1.0,
        "code_quality": 1.0,
        "performance_claims": 1.0,
        "reproducibility": 1.0,
        "reviewedness": 1.0,
        "tree_score": 1.0,
        "license": 1.0,
    }
    score, _ = calculate_net_score(metrics)
    # Weighted sum without size: (0 + 6*0.12 + 3*0.10) / 1.10 = 1.02 / 1.10 ≈ 0.9273
    assert math.isclose(score, 0.9273, rel_tol=1e-4)


def test_net_score_size_average():
    metrics = {
        "size_score": {"cpu": 0.0, "gpu": 1.0},  # average 0.5
        "ramp_up_time": 0.5,
        "bus_factor": 0.5,
        "dataset_and_code_score": 1.0,
        "dataset_quality": 0.0,
        "code_quality": 1.0,
        "performance_claims": 0.5,
        "reproducibility": 0.5,
        "reviewedness": 0.5,
        "tree_score": 0.5,
        "license": 1.0,
    }
    # Weighted sum = (0.04 + 0.06 + 0.06 + 0.12 + 0 + 0.12 + 0.06 + 0.05 + 0.05 + 0.05) / 1.10
    # = 0.61 / 1.10 ≈ 0.5545
    score, _ = calculate_net_score(metrics)
    assert math.isclose(score, 0.5545, rel_tol=1e-4)


def test_net_score_clamped_at_one():
    metrics = {
        "size_score": {"cpu": 1.0},
        "ramp_up_time": 1.2,  # >1 should still contribute 1.2 * weight
        "bus_factor": 1.2,
        "dataset_and_code_score": 1.2,
        "dataset_quality": 1.2,
        "code_quality": 1.2,
        "performance_claims": 1.2,
        "reproducibility": 1.2,
        "reviewedness": 1.2,
        "tree_score": 1.2,
        "license": 2.0,  # exaggerate license to ensure overshoot
    }
    score, _ = calculate_net_score(metrics)
    # Even if overweight, final result must be <=1
    assert 0.0 <= score <= 1.0
    assert score == 1.0
