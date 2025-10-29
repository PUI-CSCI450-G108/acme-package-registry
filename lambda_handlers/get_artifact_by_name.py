"""
Lambda handler for GET /artifact/byName/{name}

Returns metadata for all artifacts matching the provided name.
"""

import json
import logging
from typing import Dict, Any

from lambda_handlers.utils import (
    create_response,
    list_all_artifacts_from_s3
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /artifact/byName/{name}

    Returns metadata for all artifacts matching the provided name.

    API Gateway Event Structure:
    - event['pathParameters']['name'] - Artifact name to search for
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    try:
        logger.info(f"get_artifact_by_name invoked: {json.dumps(event)}")

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_response(200, {})

        # Parse path parameter
        name = event.get('pathParameters', {}).get('name')
        if not name:
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
            return create_response(404, {"error": "No such artifact."})

        logger.info(f"Found {len(matching_artifacts)} artifact(s) with name '{name}'")
        return create_response(200, matching_artifacts)

    except Exception as e:
        logger.error(f"Unexpected error in get_artifact_by_name: {e}", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
