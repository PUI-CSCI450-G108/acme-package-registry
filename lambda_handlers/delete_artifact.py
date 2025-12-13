"""Lambda handler for DELETE /artifacts/{artifact_type}/{id}."""

import json
import os
from time import perf_counter
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from lambda_handlers.utils import (
    create_response,
    load_artifact_from_s3,
    log_event,
)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Delete a single artifact by ID.

    Deletes the artifact from S3 storage.

    API Gateway Event Structure:
    - event['pathParameters']['artifact_type'] - model/dataset/code
    - event['pathParameters']['id'] - artifact ID

    Returns:
    - 200: Artifact deleted successfully
    - 400: Invalid artifact_type or artifact_id
    - 404: Artifact does not exist
    - 500: Internal server error
    """
    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"delete_artifact invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        # Handle OPTIONS preflight
        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for delete_artifact",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Parse path parameters
        path_params = event.get("pathParameters", {})
        artifact_type = path_params.get("artifact_type")
        artifact_id = path_params.get("id")

        # Validate artifact_type
        if not artifact_type or artifact_type not in ["model", "dataset", "code"]:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid artifact_type supplied to delete_artifact",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or invalid"
                },
            )

        # Validate artifact_id
        if not artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact_id in delete_artifact",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_id",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_type or artifact_id or invalid"
                },
            )

        # Load artifact to verify it exists
        existing_artifact = load_artifact_from_s3(artifact_id)
        if not existing_artifact:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found when attempting delete: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify artifact type matches
        metadata_type = existing_artifact.get("metadata", {}).get("type")
        stored_type = (
            metadata_type if metadata_type is not None else existing_artifact.get("type")
        )
        if stored_type != artifact_type:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact type mismatch for id {artifact_id}: requested={artifact_type}, actual={stored_type}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_type_mismatch",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Delete artifact from S3
        bucket_name = os.environ.get("ARTIFACTS_BUCKET")
        if not bucket_name:
            latency = perf_counter() - start_time
            log_event(
                "error",
                "ARTIFACTS_BUCKET environment variable not configured",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=500,
                error_code="s3_not_configured",
            )
            return create_response(
                500, {"error": "Internal server error: S3 not configured"}
            )

        try:
            s3_client = boto3.client("s3")
            s3_key = f"artifacts/{artifact_id}.json"

            s3_client.delete_object(Bucket=bucket_name, Key=s3_key)

            latency = perf_counter() - start_time
            log_event(
                "info",
                f"Deleted artifact {artifact_id} from S3",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=200,
            )

            return create_response(200, {"message": "Artifact is deleted."})

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            latency = perf_counter() - start_time
            log_event(
                "error",
                f"S3 error deleting artifact {artifact_id}: {e}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=500,
                error_code=f"s3_delete_failed_{error_code}",
                exc_info=True,
            )
            return create_response(
                500, {"error": f"Failed to delete artifact: {str(e)}"}
            )

    except Exception as exc:  # pragma: no cover - defensive logging
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in delete_artifact: {exc}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
