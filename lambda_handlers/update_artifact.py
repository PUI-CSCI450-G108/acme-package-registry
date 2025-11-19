"""Lambda handler for PUT /artifacts/{artifact_type}/{id}."""

import json
from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import (
    create_response,
    load_artifact_from_s3,
    save_artifact_to_s3,
    evaluate_model,
    generate_artifact_id,
    log_event,
)
from src.artifact_store import S3ArtifactStore, get_artifact_store


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Update an existing artifact with new source URL."""

    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"update_artifact invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        if event.get("httpMethod") == "OPTIONS":
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

        # Extract path parameters
        path_params = event.get("pathParameters", {})
        artifact_type = path_params.get("artifact_type")
        artifact_id = path_params.get("id")

        # Validate artifact_type
        if not artifact_type or artifact_type not in ["model", "dataset", "code"]:
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
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

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
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Parse request body
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid JSON in update_artifact request body",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_json",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Validate request body structure
        metadata = body.get("metadata", {})
        data = body.get("data", {})

        if not metadata or not data:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing metadata or data in update_artifact request",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_fields",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Extract and validate metadata fields
        name = metadata.get("name")
        request_id = metadata.get("id")
        request_type = metadata.get("type")

        # Extract URL from data
        url = data.get("url")

        if not url:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing URL in update_artifact data",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_url",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Verify artifact exists
        existing_artifact = load_artifact_from_s3(artifact_id)
        if not existing_artifact:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found for update: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify name and id match existing artifact
        existing_metadata = existing_artifact.get("metadata", {})
        existing_name = existing_metadata.get("name")
        existing_type = existing_metadata.get("type")

        if name and name != existing_name:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Name mismatch in update: expected {existing_name}, got {name}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="name_mismatch",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        if request_id and request_id != artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"ID mismatch in update: expected {artifact_id}, got {request_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="id_mismatch",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Verify type matches
        if existing_type != artifact_type:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Type mismatch in update: stored type {existing_type} != path type {artifact_type}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="type_mismatch",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Re-evaluate the artifact with the new URL
        log_event(
            "info",
            f"Re-evaluating artifact {artifact_id} with new URL: {url}",
            event=event,
            context=context,
            model_id=artifact_id,
        )

        try:
            artifact_store = get_artifact_store()
            rating = evaluate_model(url, artifact_store=artifact_store, event=event, context=context)
        except Exception as eval_error:
            latency = perf_counter() - start_time
            log_event(
                "error",
                f"Failed to evaluate new artifact URL: {eval_error}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="evaluation_failed",
                exc_info=True,
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
                },
            )

        # Update artifact with new data, preserving the original ID and name
        updated_artifact = {
            "metadata": {
                "name": existing_name,
                "id": artifact_id,
                "type": artifact_type,
            },
            "url": url,
            **rating,
        }

        # Save updated artifact to S3
        save_artifact_to_s3(artifact_id, updated_artifact)

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Successfully updated artifact {artifact_id}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )

        return create_response(200, {"message": "Artifact is updated."})

    except Exception as exc:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in update_artifact: {exc}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
