"""
Lambda handler for POST /artifact/{artifact_type}

Registers a new artifact and evaluates it.
"""

import json
from time import perf_counter
import logging
import os
from typing import Dict, Any
from huggingface_hub import snapshot_download

from lambda_handlers.utils import (
    create_response,
    evaluate_model,
    artifact_exists_in_s3,
    save_artifact_to_s3,
    MIN_NET_SCORE_THRESHOLD,
    log_event,
    is_valid_artifact_url,
    upload_hf_files_to_s3,
    s3_client,
    BUCKET_NAME,
)
from src.artifact_utils import generate_artifact_id
from src.artifact_store import S3ArtifactStore
from io import BytesIO
import zipfile


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for POST /artifact/{artifact_type}

    Registers a new artifact and evaluates it.

    API Gateway Event Structure:
    - event['pathParameters']['artifact_type'] - model/dataset/code
    - event['body'] - JSON string with {"url": "..."}
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"create_artifact invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for create_artifact",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Parse path parameter
        artifact_type = event.get('pathParameters', {}).get('artifact_type')
        if not artifact_type or artifact_type not in ['model', 'dataset', 'code']:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid artifact_type supplied",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(400, {
                "error": "Invalid artifact_type. Must be model, dataset, or code."
            })

        # Parse request body
        body_str = event.get('body', '{}')
        try:
            body = json.loads(body_str) if isinstance(body_str, str) else body_str
        except json.JSONDecodeError:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid JSON payload for create_artifact",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_payload",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
            })

        url = body.get('url', '').strip()
        if not url:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing URL in create_artifact payload",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_url",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
            })

        # Extract optional name from request body
        provided_name = body.get('name', '').strip() if body.get('name') else None

        # Validate URL format based on artifact type (if validation is enabled)
        url_validation_enabled = os.environ.get('URL_VALIDATION_ENABLED', 'true').lower() == 'true'
        if url_validation_enabled and not is_valid_artifact_url(url, artifact_type):
            latency = perf_counter() - start_time
            error_msg = {
                "model": "Invalid URL. Must be a valid HuggingFace model URL (e.g., https://huggingface.co/org/model).",
                "dataset": "Invalid URL. Must be a valid HuggingFace dataset URL (e.g., https://huggingface.co/datasets/org/dataset).",
                "code": "Invalid URL. Must be a valid GitHub repository URL (e.g., https://github.com/owner/repo)."
            }.get(artifact_type, "Invalid URL.")
            log_event(
                "warning",
                f"Invalid URL provided for {artifact_type}",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_artifact_url",
            )
            return create_response(400, {"error": error_msg})

        # Generate artifact ID (deterministic UUID based on type+URL)
        artifact_id = generate_artifact_id(artifact_type, url)

        # Check if already exists in S3
        if artifact_exists_in_s3(artifact_id):
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact already exists: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=409,
                error_code="artifact_exists",
            )
            return create_response(409, {"error": "Artifact exists already."})
        
        # Download URL pointing to API endpoint
        download_url = f"https://436cwsdtp3.execute-api.us-east-1.amazonaws.com/download/{artifact_id}"
       
        # Evaluate the artifact (only models supported for now)
        if artifact_type == 'model':
            try:
                # Create artifact store for tree_score metric
                bucket_name = os.environ.get('ARTIFACTS_BUCKET')
                artifact_store = S3ArtifactStore(bucket_name) if bucket_name else None

                rating = evaluate_model(url, artifact_store=artifact_store)

                # Check if rating is acceptable (if threshold is enabled)
                threshold_enabled = os.environ.get('THRESHOLD_ENABLED', 'true').lower() == 'true'
                if threshold_enabled and rating.get("net_score", 0) < MIN_NET_SCORE_THRESHOLD:
                    latency = perf_counter() - start_time
                    log_event(
                        "warning",
                        "Artifact net_score below threshold",
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

                # Use provided name if available, otherwise use name from rating
                name = provided_name if provided_name else rating.get("name", "unknown")

                # Extract base_model for lineage tracking (if present in rating)
                # Note: base_model is not part of ModelRating schema but is added by evaluate_model
                base_model = rating.pop("base_model", None)
            except Exception as e:
                latency = perf_counter() - start_time
                log_event(
                    "error",
                    f"Error evaluating artifact: {e}",
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
            try:
                # Upload essential files from HF model repo to S3 for future use
                if os.environ.get('ENABLE_FULL_MODEL_DOWNLOAD', 'true').lower() == 'true':
                    upload_hf_files_to_s3(artifact_id, url)
                    log_event(
                        "info",
                        f"Uploaded essential HF files for artifact {artifact_id}",
                        event=event,
                        context=context,
                        model_id=artifact_id,
                    )
            except Exception as e:
                latency = perf_counter() - start_time
                log_event(
                    "error",
                    f"Error uploading HF files: {e}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    latency=latency,
                    status=500,
                    error_code="hf_files_upload_failed",
                    exc_info=True,
                )
                return create_response(500, {
                    "error": f"Error uploading essential HF files: {str(e)}"
                })
        else:
            # For dataset/code, use provided name or extract from URL
            if provided_name:
                name = provided_name
            else:
                name = url.split("/")[-1] if "/" in url else "unknown"
            rating = None
            base_model = None

        # Create artifact data
        artifact_data = {
            "metadata": {
                "name": name,
                "id": artifact_id,
                "type": artifact_type,
            },
            "data": {
                "url": url,
                "download_url": download_url, 
            },
        }
        storage_data = {
            "url": url,
            "rating": rating,
            "metadata": artifact_data.get("metadata", {}),
            "data": artifact_data.get("data", {}),
            "type": artifact_type,
        }

        # Add base_model to artifact data if present (for lineage tracking)
        if base_model is not None:
            artifact_data["base_model"] = base_model

        save_artifact_to_s3(artifact_id, storage_data)

        # Also create a small ZIP bundle with a data.txt containing the artifact_id
        try:
            zip_key = f"artifacts/{artifact_id}/data.zip"
            if not BUCKET_NAME:
                log_event(
                    "warning",
                    "ARTIFACTS_BUCKET env var not set; skipping data.zip storage",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    error_code="missing_bucket_env",
                )
            elif not s3_client:
                log_event(
                    "warning",
                    "S3 client not initialized; skipping data.zip storage",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    error_code="missing_s3_client",
                )
            else:
                log_event(
                    "info",
                    f"Preparing data.zip for {artifact_id} to store at s3://{BUCKET_NAME}/{zip_key}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                )
                buffer = BytesIO()
                with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("data.txt", f"artifact_id={artifact_id}\n")
                buffer.seek(0)
                s3_client.put_object(
                    Bucket=BUCKET_NAME,
                    Key=zip_key,
                    Body=buffer.read(),
                    ContentType="application/zip"
                )
                log_event(
                    "info",
                    f"Stored data.zip at s3://{BUCKET_NAME}/{zip_key}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                )
        except Exception as e:
            log_event(
                "warning",
                f"Failed to create/store data.zip for {artifact_id} at s3://{BUCKET_NAME}/{zip_key}: {e}",
                event=event,
                context=context,
                model_id=artifact_id,
                error_code="zip_store_failed",
            )

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Registered artifact Data {artifact_id}: {name}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=201,
        )

        # Return artifact envelope
        return create_response(201, artifact_data)

    except Exception as e:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in create_artifact: {e}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
