"""
Lambda handler for GET /artifact/{artifact_id}

Returns the full artifact (metadata + url + rating) for the given ID.
"""

import json
import logging
from typing import Any, Dict

from lambda_handlers.utils import (
    create_response,
    list_all_artifacts_from_s3,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for GET /artifact/{artifact_id}

    API Gateway Event Structure:
    - event['pathParameters']['artifact_id'] - ID of the artifact to fetch
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    try:
        logger.info(f"get_artifact_by_id invoked: {json.dumps(event)}")

        # Handle OPTIONS preflight
        if event.get("httpMethod") == "OPTIONS":
            return create_response(200, {})

        # Parse path parameter
        artifact_id = event.get("pathParameters", {}).get("artifact_id")
        if not artifact_id:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Load all artifacts from S3 (registry-style)
        all_artifacts = list_all_artifacts_from_s3()

        artifact_data = all_artifacts.get(artifact_id)
        if not artifact_data:
            return create_response(404, {"error": "No such artifact."})

        # Return the entire artifact envelope (metadata, url, rating, type, etc.)
        return create_response(200, artifact_data)

    except Exception as exc:
        logger.error("Unexpected error in get_artifact_by_id", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})