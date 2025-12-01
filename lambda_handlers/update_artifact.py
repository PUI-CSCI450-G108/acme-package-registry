"""
Lambda handler for PUT /artifacts/{artifact_type}/{id}

Updates an existing artifact's URL and re-evaluates it if it's a model.
"""

import json
import os
from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import (
    create_response,
    evaluate_model,
    get_header,
    is_valid_artifact_url,
    load_artifact_from_s3,
    log_event,
    save_artifact_to_s3,
    MIN_NET_SCORE_THRESHOLD,
)
from src.artifact_store import S3ArtifactStore
from src.auth import AuthError, InvalidTokenError, get_default_auth_service


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for PUT /artifacts/{artifact_type}/{id}

    Updates an existing artifact. For models, re-runs full evaluation pipeline.
    Type cannot be changed. Only URL is updated; name is preserved.

    API Gateway Event Structure:
    - event['pathParameters']['artifact_type'] - model/dataset/code
    - event['pathParameters']['id'] - artifact ID
    - event['body'] - JSON string with {"url": "..."}
    - event['headers']['X-Authorization'] - Auth token (required)
    """
    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"update_artifact invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for update_artifact",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Parse path parameters
        path_params = event.get('pathParameters', {})
        artifact_type = path_params.get('artifact_type')
        artifact_id = path_params.get('id')

        # Validate artifact_type
        if not artifact_type or artifact_type not in ['model', 'dataset', 'code']:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid artifact_type supplied to update_artifact",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_type or it is formed improperly, or is invalid."
            })

        # Validate artifact_id
        if not artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact_id in update_artifact",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_id",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Authenticate and authorize
        token = get_header(event, "X-Authorization")
        if not token:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Update attempted without authorization token",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=403,
                error_code="missing_token",
            )
            return create_response(403, {
                "error": "Authentication failed due to invalid or missing AuthenticationToken."
            })

        try:
            service = get_default_auth_service()
            payload, user = service.authenticate_token(token)

            # Check upload permission
            if not user.can_upload:
                latency = perf_counter() - start_time
                log_event(
                    "warning",
                    f"User '{user.username}' attempted update without can_upload permission",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    latency=latency,
                    status=403,
                    error_code="insufficient_permissions",
                )
                return create_response(403, {
                    "error": "Authentication failed due to invalid or missing AuthenticationToken."
                })
        except (AuthError, InvalidTokenError) as e:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Authentication failed in update_artifact: {e}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=403,
                error_code="auth_failed",
            )
            return create_response(403, {
                "error": "Authentication failed due to invalid or missing AuthenticationToken."
            })

        # Parse request body
        body_str = event.get('body', '{}')
        try:
            body = json.loads(body_str) if isinstance(body_str, str) else body_str
        except json.JSONDecodeError:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid JSON payload for update_artifact",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="invalid_payload",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
            })

        # Validate URL presence
        new_url = body.get('url', '').strip()
        if not new_url:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing URL in update_artifact payload",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="missing_url",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
            })

        # Validate URL format for artifact type
        if not is_valid_artifact_url(new_url, artifact_type):
            latency = perf_counter() - start_time
            error_msg = {
                "model": "Invalid URL. Must be a valid HuggingFace model URL (e.g., https://huggingface.co/org/model).",
                "dataset": "Invalid URL. Must be a valid HuggingFace dataset URL (e.g., https://huggingface.co/datasets/org/dataset).",
                "code": "Invalid URL. Must be a valid GitHub repository URL (e.g., https://github.com/owner/repo)."
            }.get(artifact_type, "Invalid URL.")
            log_event(
                "warning",
                f"Invalid URL provided for {artifact_type} in update_artifact",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="invalid_artifact_url",
            )
            return create_response(400, {"error": error_msg})

        # Load existing artifact from S3
        existing_artifact = load_artifact_from_s3(artifact_id)
        if not existing_artifact:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found when attempting update: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify type immutability
        stored_type = existing_artifact.get("metadata", {}).get("type") or existing_artifact.get("type")
        if stored_type != artifact_type:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Attempted to change artifact type for {artifact_id}: {stored_type} → {artifact_type}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="type_immutable",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
            })

        # Preserve name from existing artifact
        name = existing_artifact.get("metadata", {}).get("name", "unknown")

        # Re-evaluate artifact (models only)
        if artifact_type == 'model':
            try:
                # Create artifact store for tree_score metric
                bucket_name = os.environ.get('ARTIFACTS_BUCKET')
                artifact_store = S3ArtifactStore(bucket_name) if bucket_name else None

                # Run full evaluation pipeline
                rating = evaluate_model(new_url, artifact_store=artifact_store)

                # Check if rating meets threshold
                if rating.get("net_score", 0) < MIN_NET_SCORE_THRESHOLD:
                    latency = perf_counter() - start_time
                    log_event(
                        "warning",
                        f"Updated artifact net_score below threshold: {artifact_id}",
                        event=event,
                        context=context,
                        model_id=artifact_id,
                        latency=latency,
                        status=424,
                        error_code="rating_below_threshold",
                    )
                    return create_response(424, {
                        "error": f"Artifact is not registered due to the disqualified rating (net_score={rating.get('net_score', 0):.2f} < {MIN_NET_SCORE_THRESHOLD})."
                    })
            except Exception as e:
                latency = perf_counter() - start_time
                log_event(
                    "error",
                    f"Error re-evaluating artifact during update: {e}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    latency=latency,
                    status=500,
                    error_code="model_evaluation_failed",
                    exc_info=True,
                )
                return create_response(500, {
                    "error": f"Error evaluating artifact: {str(e)}"
                })
        else:
            # For dataset/code, preserve existing rating (should be None)
            rating = existing_artifact.get("rating")

        # Update artifact data
        updated_artifact = {
            "url": new_url,
            "metadata": {
                "name": name,
                "id": artifact_id,
                "type": artifact_type
            },
            "rating": rating,
            "type": artifact_type
        }

        # Save updated artifact to S3 (S3 versioning preserves history)
        save_artifact_to_s3(artifact_id, updated_artifact)

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Updated artifact {artifact_id}: {name}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )

        # Return artifact envelope
        return create_response(200, {
            "metadata": updated_artifact["metadata"],
            "data": {"url": new_url}
        })

    except Exception as e:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in update_artifact: {e}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
