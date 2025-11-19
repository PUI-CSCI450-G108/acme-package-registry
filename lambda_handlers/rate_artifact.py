"""
Lambda handler for GET /artifact/model/{id}/rate

Returns the rating for a registered model artifact.
"""

import json
from time import perf_counter
from typing import Dict, Any

from lambda_handlers.utils import (
    create_response,
    evaluate_model,
    load_artifact_from_s3,
    save_artifact_to_s3,
    log_event,
)


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /artifact/model/{id}/rate

    Returns the rating for a registered model artifact.

    API Gateway Event Structure:
    - event['pathParameters']['id'] - Artifact ID
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"rate_artifact invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for rate_artifact",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Parse path parameter
        artifact_id = event.get('pathParameters', {}).get('id')
        if not artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact_id in rate_artifact",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_id",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Load artifact from S3
        artifact = load_artifact_from_s3(artifact_id)
        if not artifact:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Artifact not found for rating",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify it's a model
        if artifact.get("type") != "model":
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Attempted to rate non-model artifact",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(400, {
                "error": f"Artifact {artifact_id} is not a model"
            })

        # Get cached rating or re-evaluate
        rating = artifact.get("rating")
        if not rating:
            url = artifact.get("url")
            try:
                rating = evaluate_model(url, event=event, context=context)
                # Update S3 with new rating
                artifact["rating"] = rating
                save_artifact_to_s3(artifact_id, artifact)
            except Exception as e:
                latency = perf_counter() - start_time
                log_event(
                    "error",
                    f"Error evaluating artifact {artifact_id}: {e}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    latency=latency,
                    status=500,
                    error_code="model_evaluation_failed",
                    exc_info=True,
                )
                return create_response(500, {
                    "error": "The artifact rating system encountered an error while computing at least one metric."
                })

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Returning rating for artifact {artifact_id}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )
        return create_response(200, rating)

    except Exception as e:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in rate_artifact: {e}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
