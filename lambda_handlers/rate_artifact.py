"""
Lambda handler for GET /artifact/model/{id}/rate

Returns the rating for a registered model artifact.
"""

import json
import logging
from typing import Dict, Any

from lambda_handlers.utils import (
    create_response,
    evaluate_model,
    load_artifact_from_s3,
    save_artifact_to_s3
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /artifact/model/{id}/rate

    Returns the rating for a registered model artifact.

    API Gateway Event Structure:
    - event['pathParameters']['id'] - Artifact ID
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    try:
        logger.info(f"rate_artifact invoked: {json.dumps(event)}")

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_response(200, {})

        # Parse path parameter
        artifact_id = event.get('pathParameters', {}).get('id')
        if not artifact_id:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Validate ID format
        if not artifact_id.replace("-", "").replace("_", "").isalnum():
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Load artifact from S3
        artifact = load_artifact_from_s3(artifact_id)
        if not artifact:
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify it's a model
        if artifact.get("type") != "model":
            return create_response(400, {
                "error": f"Artifact {artifact_id} is not a model"
            })

        # Get cached rating or re-evaluate
        rating = artifact.get("rating")
        if not rating:
            url = artifact.get("url")
            try:
                rating = evaluate_model(url)
                # Update S3 with new rating
                artifact["rating"] = rating
                save_artifact_to_s3(artifact_id, artifact)
            except Exception as e:
                logger.error(f"Error evaluating artifact {artifact_id}: {e}", exc_info=True)
                return create_response(500, {
                    "error": "The artifact rating system encountered an error while computing at least one metric."
                })

        logger.info(f"Returning rating for artifact {artifact_id}")
        return create_response(200, rating)

    except Exception as e:
        logger.error(f"Unexpected error in rate_artifact: {e}", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
