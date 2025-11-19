"""Lambda handler for GET /artifact/{artifact_type}/{id}/cost."""

import json
from time import perf_counter
from typing import Any, Dict, Optional, Set

from lambda_handlers.utils import (
    create_response,
    load_artifact_from_s3,
    log_event,
)
from src.metrics.helpers.pull_model import pull_model_info
from src.metrics.size import (
    _bytes_from_safetensors_params,
    _bytes_from_repo_files,
    _bytes_from_dataset,
    _bytes_from_space,
)


def _get_artifact_size_mb(artifact_data: dict) -> Optional[float]:
    """
    Calculate artifact size in MB from stored artifact data.

    Args:
        artifact_data: Stored artifact data from S3

    Returns:
        Size in MB, or None if cannot be determined
    """
    try:
        # Try to get size from URL by re-pulling model info
        url = artifact_data.get("url")
        if not url:
            return None

        model_info = pull_model_info(url)
        if not model_info:
            return None

        # Try different size extraction methods based on artifact type
        total_bytes = None

        # Spaces first (detected by runtime attribute)
        if getattr(model_info, "runtime", None) is not None:
            total_bytes = _bytes_from_space(model_info)

        # Models: prefer parameter-based estimate; fallback to files
        if total_bytes is None and getattr(model_info, "safetensors", None) is not None:
            total_bytes = _bytes_from_safetensors_params(model_info)
            if total_bytes is None:
                total_bytes = _bytes_from_repo_files(model_info)

        # Datasets: prefer files metadata; fallback to siblings
        if total_bytes is None:
            total_bytes = _bytes_from_dataset(model_info)

        if total_bytes is None or total_bytes <= 0:
            return None

        # Convert bytes to MB
        size_mb = total_bytes / (1024 * 1024)
        return round(size_mb, 2)

    except Exception as e:
        log_event(
            "warning",
            f"Error calculating artifact size: {e}",
            event=None,
            context=None,
            exc_info=True,
        )
        return None


def _get_dependencies(
    artifact_data: dict,
    visited: Optional[Set[str]] = None,
    max_depth: int = 5,
    current_depth: int = 0
) -> Dict[str, dict]:
    """
    Recursively get all dependencies for an artifact.

    Args:
        artifact_data: Artifact data dictionary
        visited: Set of already-visited artifact IDs (cycle detection)
        max_depth: Maximum recursion depth
        current_depth: Current recursion depth

    Returns:
        Dictionary mapping artifact_id -> artifact_data for all dependencies
    """
    if visited is None:
        visited = set()

    if current_depth >= max_depth:
        return {}

    dependencies = {}

    # Extract base models from artifact data
    base_models = artifact_data.get("base_model", [])
    if isinstance(base_models, str):
        base_models = [base_models]
    elif not isinstance(base_models, list):
        base_models = []

    # For each base model, try to find it in the registry
    for base_model_url in base_models:
        if not base_model_url or base_model_url in visited:
            continue

        visited.add(base_model_url)

        # Generate artifact ID for this dependency
        # Try to load from S3
        from src.artifact_utils import generate_artifact_id
        dep_id = generate_artifact_id("model", base_model_url)

        dep_artifact = load_artifact_from_s3(dep_id)
        if dep_artifact:
            dependencies[dep_id] = dep_artifact

            # Recursively get dependencies of this dependency
            nested_deps = _get_dependencies(
                dep_artifact,
                visited=visited.copy(),
                max_depth=max_depth,
                current_depth=current_depth + 1
            )
            dependencies.update(nested_deps)

    return dependencies


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get the cost (size in MB) of an artifact and optionally its dependencies."""

    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"get_artifact_cost invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for get_artifact_cost",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Extract path parameters
        path_params = event.get("pathParameters", {})
        artifact_type = path_params.get("artifact_type")
        artifact_id = path_params.get("id")

        # Extract query parameters
        query_params = event.get("queryStringParameters") or {}
        include_dependencies = query_params.get("dependency", "false").lower() in ["true", "1", "yes"]

        # Validate artifact_type
        if not artifact_type or artifact_type not in ["model", "dataset", "code"]:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid artifact_type supplied to get_artifact_cost",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Validate artifact_id
        if not artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact_id in get_artifact_cost",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_id",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Load artifact from S3
        artifact_data = load_artifact_from_s3(artifact_id)
        if not artifact_data:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify type matches
        stored_metadata = artifact_data.get("metadata", {})
        stored_type = stored_metadata.get("type") or artifact_data.get("type")

        if stored_type != artifact_type:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact type mismatch for id {artifact_id}: requested={artifact_type}, actual={stored_type}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_type_mismatch",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Calculate size for the main artifact
        size_mb = _get_artifact_size_mb(artifact_data)

        if size_mb is None:
            latency = perf_counter() - start_time
            log_event(
                "error",
                f"Could not determine size for artifact {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=500,
                error_code="size_calculation_failed",
            )
            return create_response(
                500,
                {"error": "The artifact cost calculator encountered an error."}
            )

        # Build response
        cost_response = {}

        if include_dependencies:
            # Get all dependencies
            dependencies = _get_dependencies(artifact_data)

            # Calculate sizes for all dependencies
            dependency_sizes = {}
            for dep_id, dep_data in dependencies.items():
                dep_size = _get_artifact_size_mb(dep_data)
                if dep_size is not None:
                    dependency_sizes[dep_id] = dep_size

            # Calculate total cost (main artifact + all dependencies)
            total_cost = size_mb + sum(dependency_sizes.values())

            # Main artifact entry
            cost_response[artifact_id] = {
                "standalone_cost": size_mb,
                "total_cost": total_cost
            }

            # Add dependency entries
            for dep_id, dep_size in dependency_sizes.items():
                cost_response[dep_id] = {
                    "standalone_cost": dep_size,
                    "total_cost": dep_size
                }
        else:
            # Just return the standalone cost
            cost_response[artifact_id] = {
                "total_cost": size_mb
            }

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Calculated cost for artifact {artifact_id}: {size_mb} MB",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )

        return create_response(200, cost_response)

    except Exception as exc:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in get_artifact_cost: {exc}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(
            500,
            {"error": "The artifact cost calculator encountered an error."}
        )
