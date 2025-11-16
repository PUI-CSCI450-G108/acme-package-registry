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
    Lambda handler for GET /artifacts/{artifact_type}/{id}

    API Gateway Event Structure:
    - event['pathParameters']['artifact_type'] - Type of artifact (model/dataset/code)
    - event['pathParameters']['id'] - ID of the artifact to fetch
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    try:
        logger.info(f"get_artifact_by_id invoked: {json.dumps(event)}")

        # Handle OPTIONS preflight
        if event.get("httpMethod") == "OPTIONS":
            return create_response(200, {})

        # Parse path parameters
        path_params = event.get("pathParameters", {})
        artifact_type = path_params.get("artifact_type")
        artifact_id = path_params.get("id")

        if not artifact_type or artifact_type not in ['model', 'dataset', 'code']:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_type or it is formed improperly, or is invalid."
            })

        if not artifact_id:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Load all artifacts from S3 (registry-style)
        all_artifacts = list_all_artifacts_from_s3()

        artifact_data = all_artifacts.get(artifact_id)
        if not artifact_data:
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify artifact type matches
        stored_type = artifact_data.get("metadata", {}).get("type") or artifact_data.get("type")
        if stored_type != artifact_type:
            return create_response(404, {"error": "Artifact does not exist."})

        # Return artifact in OpenAPI spec format (metadata + data)
        response_data = {
            "metadata": artifact_data.get("metadata", {}),
            "data": {"url": artifact_data.get("url", "")}
        }
        return create_response(200, response_data)

    except Exception as exc:
        logger.error("Unexpected error in get_artifact_by_id", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})