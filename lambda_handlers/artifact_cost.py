"""Lambda handler for GET /artifact/{artifact_type}/{id}/cost."""

import json
from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import (
    create_response,
    list_all_artifacts_from_s3,
    log_event,
)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Calculate the cost (storage size in MB) for an artifact.

    For now, this returns a static cost value while the internal download
    mechanism is being fixed. In the future, this should calculate the actual
    size from the download_url.

    Query parameters:
        - dependency (bool): If true, include costs for all dependencies
    """

    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"artifact_cost invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for artifact_cost",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        path_params = event.get("pathParameters", {})
        artifact_type = path_params.get("artifact_type")
        artifact_id = path_params.get("id")

        if not artifact_type or artifact_type not in ["model", "dataset", "code"]:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid artifact_type supplied to artifact_cost",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or it is formed improperly, or is invalid."
                },
            )

        if not artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact_id in artifact_cost",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_id",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Get the dependency query parameter (defaults to false)
        query_params = event.get("queryStringParameters") or {}
        include_dependencies = query_params.get("dependency", "false").lower() == "true"

        all_artifacts = list_all_artifacts_from_s3()

        artifact_data = all_artifacts.get(artifact_id)
        if not artifact_data:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found when fetching cost for id: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        stored_type = artifact_data.get("metadata", {}).get("type") or artifact_data.get("type")
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

        # STATIC VALUE: Replace with actual size calculation when download is fixed
        # This represents the size in MB
        static_cost = 100.0

        if include_dependencies:
            # For now, return a response showing the artifact has no dependencies
            # In the future, this should traverse the lineage graph
            response_data = {
                artifact_id: {
                    "standalone_cost": static_cost,
                    "total_cost": static_cost
                }
            }
        else:
            # Return only total_cost when dependency=false
            response_data = {
                artifact_id: {
                    "total_cost": static_cost
                }
            }

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Returned cost for artifact {artifact_id}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )
        return create_response(200, response_data)

    except Exception as exc:  # pragma: no cover - defensive logging
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in artifact_cost: {exc}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
