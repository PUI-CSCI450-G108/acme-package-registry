"""
Lambda handler for GET /artifact/byName/{name}

Returns metadata for all artifacts matching the provided name.
"""

import json
import logging
from time import perf_counter
from typing import Dict, Any

from lambda_handlers.utils import (
    create_response,
    list_all_artifacts_from_s3,
    log_event,
)

# Configure logging for Lambda (outputs to CloudWatch Logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s %(message)s'
)


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /artifact/byName/{name}

    Returns metadata for all artifacts matching the provided name.

    API Gateway Event Structure:
    - event['pathParameters']['name'] - Artifact name to search for
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    start_time = perf_counter()
    artifact_name = None

    try:
        log_event(
            "info",
            f"get_artifact_by_name invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for get_artifact_by_name",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Parse path parameter
        name = event.get('pathParameters', {}).get('name')
        artifact_name = name
        if not name:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact name in get_artifact_by_name",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_name",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_name or it is formed improperly, or is invalid."
            })

        # Search for artifacts with matching name in S3
        all_artifacts = list_all_artifacts_from_s3()
        matching_artifacts = []
        for artifact_id, artifact_data in all_artifacts.items():
            artifact_metadata = artifact_data.get("metadata", {})
            artifact_name = artifact_metadata.get("name", "")

            # Case-insensitive comparison
            if artifact_name.lower() == name.lower():
                matching_artifacts.append(artifact_metadata)

        # Return 404 if no matches found
        if not matching_artifacts:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "No artifacts found matching requested name",
                event=event,
                context=context,
                model_id=None,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "No such artifact."})

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Found {len(matching_artifacts)} artifact(s) with name '{name}'",
            event=event,
            context=context,
            model_id=None,
            latency=latency,
            status=200,
        )
        return create_response(200, matching_artifacts)

    except Exception as e:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in get_artifact_by_name: {e}",
            event=event,
            context=context,
            model_id=artifact_name,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
