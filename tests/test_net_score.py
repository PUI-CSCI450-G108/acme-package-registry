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
        "license": 1.0,
    }
    score, latency = calculate_net_score(metrics)
    # Weighted sum: 0.1 + (6 * 0.15) = 0.1 + 0.9 = 1.0 then * license(1)=1
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
        "license": 1.0,
    }
    score, _ = calculate_net_score(metrics)
    # Weighted sum without size contributes only other metrics: 6*0.15 = 0.9
    assert math.isclose(score, 0.9, rel_tol=1e-4)


def test_net_score_size_average():
    metrics = {
        "size_score": {"cpu": 0.0, "gpu": 1.0},  # average 0.5 -> weighted 0.05
        "ramp_up_time": 0.5,  # 0.075
        "bus_factor": 0.5,  # 0.075
        "dataset_and_code_score": 1.0,  # 0.15
        "dataset_quality": 0.0,  # 0.0
        "code_quality": 1.0,  # 0.15
        "performance_claims": 0.5,  # 0.075
        "license": 1.0,
    }
    # Expected sum = 0.05 + 0.075 + 0.075 + 0.15 + 0 + 0.15 + 0.075 = 0.575
    score, _ = calculate_net_score(metrics)
    assert math.isclose(score, 0.575, rel_tol=1e-4)


def test_net_score_clamped_at_one():
    metrics = {
        "size_score": {"cpu": 1.0},
        "ramp_up_time": 1.2,  # >1 should still just count as 1.2*0.15 in raw but final clamp after license
        "bus_factor": 1.2,
        "dataset_and_code_score": 1.2,
        "dataset_quality": 1.2,
        "code_quality": 1.2,
        "performance_claims": 1.2,
        "license": 2.0,  # exaggerate license to ensure overshoot
    }
    score, _ = calculate_net_score(metrics)
    # Even if overweight, final result must be <=1
    assert 0.0 <= score <= 1.0
    assert score == 1.0
