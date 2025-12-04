"""
Lambda handler for GET /artifact/model/{id}/rate

Returns the rating for a registered model artifact.
"""

import json
import time
from time import perf_counter
from typing import Dict, Any

from lambda_handlers.utils import (
    create_response,
    evaluate_model,
    load_artifact_from_s3,
    save_artifact_to_s3,
    log_event,
)
from src.artifact_store import get_artifact_store


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
            # Double-check pattern: reload artifact to see if a concurrent request just cached it
            # This prevents duplicate evaluations when multiple requests arrive simultaneously
            log_event(
                "info",
                f"Rating not cached for {artifact_id}, checking for concurrent update",
                event=event,
                context=context,
                model_id=artifact_id,
            )

            # Brief pause to let any in-flight concurrent evaluation complete
            time.sleep(0.2)

            # Reload artifact from S3
            artifact = load_artifact_from_s3(artifact_id)
            if not artifact:
                latency = perf_counter() - start_time
                log_event(
                    "warning",
                    "Artifact disappeared during rating check",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    latency=latency,
                    status=404,
                    error_code="artifact_not_found",
                )
                return create_response(404, {"error": "Artifact does not exist."})

            rating = artifact.get("rating")

            if not rating:
                # Still no rating after double-check, proceed with evaluation
                url = artifact.get("url")
                log_event(
                    "info",
                    f"No concurrent rating found, proceeding with evaluation for {artifact_id}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                )
                try:
                    # Get artifact store for tree_score metric
                    artifact_store = get_artifact_store()
                    rating = evaluate_model(url, artifact_store=artifact_store, event=event, context=context)
                    # Update S3 with new rating
                    artifact["rating"] = rating
                    save_artifact_to_s3(artifact_id, artifact)
                    log_event(
                        "info",
                        f"Successfully cached rating for {artifact_id}",
                        event=event,
                        context=context,
                        model_id=artifact_id,
                    )
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
            else:
                log_event(
                    "info",
                    f"Found rating cached by concurrent request for {artifact_id}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                )

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
