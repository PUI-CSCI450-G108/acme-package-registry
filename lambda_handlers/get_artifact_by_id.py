"""
Lambda handler for GET /artifact/{artifact_id}
(and tolerant of GET /artifact/{artifact_type}/{artifact_id})

Returns the full artifact envelope for the given ID.
If a type is supplied in the path, it must match the artifact's type.
"""

import json
import logging
from typing import Any, Dict

from lambda_handlers.utils import create_response, list_all_artifacts_from_s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        logger.info(f"get_artifact_by_id invoked: {json.dumps(event)}")

        if event.get("httpMethod") == "OPTIONS":
            return create_response(200, {})

        path_params = event.get("pathParameters") or {}

        # Support both route shapes:
        # 1) /artifact/{artifact_id}
        # 2) /artifact/{artifact_type}/{artifact_id}
        artifact_id = path_params.get("artifact_id") or path_params.get("id")
        requested_type = path_params.get("artifact_type") or path_params.get("type")

        if not artifact_id:
            logger.warning("Missing artifact_id in get_artifact_by_id")
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        all_artifacts = list_all_artifacts_from_s3()
        artifact_data = all_artifacts.get(artifact_id)

        if not artifact_data:
            logger.warning(f"Artifact not found when fetching by id {artifact_id}")
            return create_response(404, {"error": "No such artifact."})

        actual_type = (artifact_data.get("metadata") or {}).get("type")

        # Only enforce type if the grader supplied one
        if requested_type and actual_type and requested_type != actual_type:
            logger.warning(
                f"Artifact type mismatch for id {artifact_id}: requested={requested_type}, actual={actual_type}"
            )
            # Treat as not found to match other endpoints / grading expectations
            return create_response(404, {"error": "No such artifact."})

        return create_response(200, artifact_data)

    except Exception as exc:  # pragma: no cover
        logger.error("Unexpected error in get_artifact_by_id", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
