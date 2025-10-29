"""
Lambda handler for POST /artifact/{artifact_type}

Registers a new artifact and evaluates it.
"""

import json
import logging
from typing import Dict, Any

from lambda_handlers.utils import (
    create_response,
    evaluate_model,
    generate_artifact_id,
    artifact_exists_in_s3,
    save_artifact_to_s3,
    MIN_NET_SCORE_THRESHOLD
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for POST /artifact/{artifact_type}

    Registers a new artifact and evaluates it.

    API Gateway Event Structure:
    - event['pathParameters']['artifact_type'] - model/dataset/code
    - event['body'] - JSON string with {"url": "..."}
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    try:
        logger.info(f"create_artifact invoked: {json.dumps(event)}")

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_response(200, {})

        # Parse path parameter
        artifact_type = event.get('pathParameters', {}).get('artifact_type')
        if not artifact_type or artifact_type not in ['model', 'dataset', 'code']:
            return create_response(400, {
                "error": "Invalid artifact_type. Must be model, dataset, or code."
            })

        # Parse request body
        body_str = event.get('body', '{}')
        try:
            body = json.loads(body_str) if isinstance(body_str, str) else body_str
        except json.JSONDecodeError:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
            })

        url = body.get('url', '').strip()
        if not url:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
            })

        # Generate artifact ID (deterministic UUID based on type+URL)
        artifact_id = generate_artifact_id(artifact_type, url)

        # Check if already exists in S3
        if artifact_exists_in_s3(artifact_id):
            return create_response(409, {"error": "Artifact exists already."})

        # Evaluate the artifact (only models supported for now)
        if artifact_type == 'model':
            try:
                rating = evaluate_model(url)

                # Check if rating is acceptable
                if rating.get("net_score", 0) < MIN_NET_SCORE_THRESHOLD:
                    return create_response(424, {
                        "error": f"Artifact is not registered due to the disqualified rating (net_score={rating.get('net_score', 0):.2f} < {MIN_NET_SCORE_THRESHOLD})."
                    })

                name = rating.get("name", "unknown")
            except Exception as e:
                logger.error(f"Error evaluating artifact: {e}", exc_info=True)
                return create_response(500, {
                    "error": f"Error evaluating artifact: {str(e)}"
                })
        else:
            # For dataset/code, just extract name from URL
            name = url.split("/")[-1] if "/" in url else "unknown"
            rating = None

        # Create artifact metadata
        metadata = {
            "name": name,
            "version": "1.0.0",
            "id": artifact_id,
            "type": artifact_type
        }

        # Store artifact in S3
        artifact_data = {
            "url": url,
            "metadata": metadata,
            "rating": rating,
            "type": artifact_type
        }
        save_artifact_to_s3(artifact_id, artifact_data)

        logger.info(f"Registered artifact {artifact_id}: {name}")

        # Return artifact envelope
        return create_response(201, {
            "metadata": metadata,
            "data": {"url": url}
        })

    except Exception as e:
        logger.error(f"Unexpected error in create_artifact: {e}", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
