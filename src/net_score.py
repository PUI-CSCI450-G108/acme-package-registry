import time
from typing import Any, Dict, Tuple


def calculate_net_score(metrics: Dict[str, Any]) -> Tuple[float, int]:
    """
    Calculates the final net score based on the weighted formula
    from the project plan.

    Args:
        metrics: A dictionary containing the results of all sub-metric calculations.

    Returns:
        A tuple containing the final net score and the latency of this calculation.
    """
    start_time = time.perf_counter()

    # Weights as defined in the project plan
    weights = {
        "size_score": 0.1,  # Note: Size score itself is a dict. We'll average it for the net score.
        "ramp_up_time": 0.15,
        "bus_factor": 0.15,
        "dataset_and_code_score": 0.15,
        "dataset_quality": 0.15,
        "code_quality": 0.15,
        "performance_claims": 0.15,
    }

    license_score = metrics.get("license", 0.0)
    if not isinstance(license_score, (int, float)):
        license_score = 0.0

    # For size_score, we average the compatibility scores across devices for the net score calculation
    size_scores = metrics.get("size_score", {})
    avg_size_score = (
        sum(size_scores.values()) / len(size_scores) if size_scores else 0.0
    )

    weighted_sum = avg_size_score * weights["size_score"]

    for key, weight in weights.items():
        if key != "size_score":
            score = metrics.get(key, 0.0)
            if not isinstance(score, (int, float)):
                score = 0.0
            weighted_sum += score * weight

    # The license score is a multiplier
    final_score = license_score * weighted_sum

    # Ensure the score is within the [0, 1] bounds
    final_score = max(0.0, min(1.0, final_score))

    end_time = time.perf_counter()
    latency_ms = int((end_time - start_time) * 1000)

    return round(final_score, 4), latency_ms
