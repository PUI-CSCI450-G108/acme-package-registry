import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Tuple

# Import all the metric computation functions
from src.bus_factor import compute_bus_factor_metric
from src.code_quality import compute_code_quality_metric
from src.dataset_code_avail import compute_dataset_code_avail_metric
from src.dataset_quality import compute_dataset_quality_metric
from src.license import compute_license_metric
from src.models import NDJsonOutput
from src.net_score import calculate_net_score
from src.perf_claims import compute_perf_claims_metric
from src.ramp_up import compute_ramp_up_metric
from src.size import compute_size_metric


def _run_metric_with_timing(
    metric_func: Callable[[Any], Any], model_info: Any
) -> Tuple[Any, int]:
    """Wrapper to run a metric function and time its execution."""
    start_time = time.perf_counter()
    try:
        result = metric_func(model_info)
    except Exception as e:
        logging.error(f"Metric function {metric_func.__name__} failed: {e}")
        result = 0.0  # Default to a failing score
        if "size" in metric_func.__name__:
            result = {
                "raspberry_pi": 0.0,
                "jetson_nano": 0.0,
                "desktop_pc": 0.0,
                "aws_server": 0.0,
            }

    end_time = time.perf_counter()
    latency_ms = int((end_time - start_time) * 1000)
    return result, latency_ms


def calculate_all_metrics(model_info: Any, url: str) -> str:
    """
    Orchestrates the parallel calculation of all metrics for a given model.

    Args:
        model_info: The information object for the model from the Hugging Face API.
        url: The original URL of the model.

    Returns:
        A formatted NDJSON string representing the model's complete score card.
    """
    # Map metric names from the spec to their implementation functions
    metric_functions = {
        "ramp_up_time": compute_ramp_up_metric,
        "bus_factor": compute_bus_factor_metric,
        "license": compute_license_metric,
        "size_score": compute_size_metric,
        "dataset_and_code_score": compute_dataset_code_avail_metric,
        "dataset_quality": compute_dataset_quality_metric,
        "code_quality": compute_code_quality_metric,
        "performance_claims": compute_perf_claims_metric,
    }

    results = {}
    latencies = {}

    with ThreadPoolExecutor(max_workers=len(metric_functions)) as executor:
        # Submit all metric functions to the executor
        future_to_metric = {
            executor.submit(_run_metric_with_timing, func, model_info): name
            for name, func in metric_functions.items()
        }

        # Collect results as they complete
        for future in as_completed(future_to_metric):
            metric_name = future_to_metric[future]
            try:
                score, latency = future.result()
                results[metric_name] = score
                latencies[f"{metric_name}_latency"] = latency
            except Exception as e:
                logging.error(
                    f"Error collecting result for {metric_name} from future: {e}"
                )
                results[metric_name] = 0.0
                latencies[f"{metric_name}_latency"] = 0
                if "size" in metric_name:
                    results[metric_name] = {
                        "raspberry_pi": 0.0,
                        "jetson_nano": 0.0,
                        "desktop_pc": 0.0,
                        "aws_server": 0.0,
                    }

    # Calculate the final net score based on the collected results
    net_score, net_score_latency = calculate_net_score(results)
    results["net_score"] = net_score
    latencies["net_score_latency"] = net_score_latency

    # Prepare the final output object
    output_data = {
        "name": model_info.id,
        "category": "MODEL",  # Assuming MODEL for now
        **results,
        **latencies,
    }

    # Validate with Pydantic and serialize to JSON
    validated_output = NDJsonOutput(**output_data)
    return validated_output.model_dump_json()
