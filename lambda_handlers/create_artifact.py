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
import boto3

from lambda_handlers.utils import (
    create_response,
    evaluate_model,
    artifact_exists_in_s3,
    save_artifact_to_s3,
    MIN_NET_SCORE_THRESHOLD,
    log_event,
    is_valid_artifact_url,
    upload_essential_hf_files_to_s3,
)
from src.artifact_utils import generate_artifact_id
from src.artifact_store import S3ArtifactStore


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
        else:
            # For dataset/code, use provided name or extract from URL
            if provided_name:
                name = provided_name
            else:
                name = url.split("/")[-1] if "/" in url else "unknown"
            rating = None

        # Create artifact metadata
        metadata = {
            "name": name,
            "id": artifact_id,
            "type": artifact_type
        }

        # Store artifact data in S3
        artifact_data = {
            "url": url,
            "metadata": metadata,
            "rating": rating,
            "type": artifact_type
        }
        save_artifact_to_s3(artifact_id, artifact_data)

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

        # Feature flag: Check if full model download is enabled
        enable_full_download = os.environ.get("ENABLE_FULL_MODEL_DOWNLOAD", "false").lower() == "true"
        
        # Extract repo_id from HuggingFace URL and download if enabled
        if enable_full_download and url.startswith("https://huggingface.co/"):
            try:
                # Extract repo_id (check datasets URL first, then models)
                if url.startswith("https://huggingface.co/datasets/"):
                    repo_id = url.replace("https://huggingface.co/datasets/", "")
                else:
                    repo_id = url.replace("https://huggingface.co/", "")

                # Remove /tree/<branch> if present
                if "/tree/" in repo_id:
                    repo_id = repo_id.split("/tree/")[0]
                
                # Determine repo type
                repo_type = "dataset" if artifact_type == "dataset" else "model"
                
                # Download snapshot with authentication
                local_dir = snapshot_download(
                    repo_id=repo_id,
                    repo_type=repo_type,
                    token=os.environ.get("HF_TOKEN")
                )
                
                s3_prefix = f"artifacts/{artifact_id}"
                manifest = upload_essential_hf_files_to_s3(local_dir, s3_prefix=s3_prefix)
            except Exception as e:
                latency = perf_counter() - start_time
                log_event(
                    "error",
                    f"Failed to download/upload HF files for artifact {artifact_id}: {e}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    latency=latency,
                    status=500,
                    error_code="hf_download_upload_error",
                    exc_info=True,
                )
                return create_response(500, {"error": f"Failed to download/upload HF files: {str(e)}"})
            latency = perf_counter() - start_time
            log_event(
                "info",
                f"Uploaded essential HF files for artifact {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=201,
            )

        # Generate download_url as presigned S3 URL
        download_url = None
        if enable_full_download:
            try:
                bucket_name = os.environ.get('ARTIFACTS_BUCKET')
                manifest_key = f'artifacts/{artifact_id}/artifact_files_manifest.json'
                s3_client = boto3.client('s3')

                # Generate 1-hour presigned URL for manifest
                download_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket_name, 'Key': manifest_key},
                    ExpiresIn=3600
                )
            except Exception as e:
                log_event(
                    "warning",
                    f"Failed to generate download_url for {artifact_id}: {e}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                )

        # Return artifact envelope with download_url
        response_data = {
            "metadata": metadata,
            "data": {"url": url}
        }
        if download_url:
            response_data["data"]["download_url"] = download_url

        return create_response(201, response_data)

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
