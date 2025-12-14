"""
Lambda handler for POST /artifact/model/{id}/license-check

Checks license compatibility between an artifact and a GitHub repository.
"""

import json
from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import (
    create_response,
    load_artifact_from_s3,
    log_event,
)
from src.license_compatibility import (
    check_license_compatibility,
    fetch_github_license,
    normalize_license_string,
    GitHubAPIError,
    LicenseNotFoundError,
)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for POST /artifact/model/{id}/license-check

    Checks license compatibility between artifact and GitHub repository.

    API Gateway Event Structure:
    - event['pathParameters']['id'] - Artifact ID
    - event['body'] - JSON with {"github_url": "https://github.com/..."}

    Returns:
    - 200: Boolean indicating license compatibility
    - 400: Malformed request
    - 404: Artifact or GitHub repo not found
    - 502: External license info unavailable
    - 500: Internal server error
    """
    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"license_check invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        # Handle OPTIONS preflight for CORS
        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for license_check",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Parse path parameter (artifact ID)
        artifact_id = event.get("pathParameters", {}).get("id")
        if not artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact_id in license_check",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_id",
            )
            return create_response(
                400, {"error": "Missing artifact_id in path parameters"}
            )

        # Parse request body
        body_str = event.get("body", "{}")
        try:
            body = (
                json.loads(body_str) if isinstance(body_str, str) else body_str
            )
        except json.JSONDecodeError:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid JSON in license_check request body",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_json",
            )
            return create_response(400, {"error": "Invalid JSON in request body"})

        github_url = body.get("github_url", "").strip()
        if not github_url:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing github_url in license_check",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_github_url",
            )
            return create_response(
                400, {"error": "Missing required field: github_url"}
            )

        # Validate GitHub URL format
        if not github_url.startswith("https://github.com/"):
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Invalid GitHub URL format: {github_url}",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_github_url",
            )
            return create_response(
                400,
                {"error": "github_url must be a valid GitHub repository URL"},
            )

        # Load artifact from S3
        artifact = load_artifact_from_s3(artifact_id)
        if not artifact:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found for license check: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify it's a model (endpoint is /artifact/model/{id}/license-check)
        artifact_type = artifact.get("metadata", {}).get("type") or artifact.get(
            "type"
        )
        if artifact_type != "model":
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Attempted license check on non-model artifact: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(
                400, {"error": f"Artifact {artifact_id} is not a model"}
            )

        # Extract artifact license from metadata
        artifact_license_raw = artifact.get("metadata", {}).get("license")

        if not artifact_license_raw:
            # If artifact has no license, consider it incompatible
            latency = perf_counter() - start_time
            log_event(
                "info",
                f"Artifact {artifact_id} has no license, returning incompatible",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=200,
            )
            return create_response(200, False)

        # Normalize artifact license
        artifact_license = normalize_license_string(artifact_license_raw)
        if not artifact_license:
            # Failed to normalize license
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Failed to normalize artifact license: {artifact_license_raw}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=200,
            )
            return create_response(200, False)

        # Fetch GitHub repository license
        try:
            github_license = fetch_github_license(github_url)
        except LicenseNotFoundError as e:
            # GitHub repo has no license - incompatible
            latency = perf_counter() - start_time
            log_event(
                "info",
                f"GitHub repo has no license: {github_url}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=200,
            )
            return create_response(200, False)
        except GitHubAPIError as e:
            error_msg = str(e).lower()
            if "404" in error_msg or "not found" in error_msg:
                latency = perf_counter() - start_time
                log_event(
                    "warning",
                    f"GitHub repo not found: {github_url}",
                    event=event,
                    context=context,
                    model_id=artifact_id,
                    latency=latency,
                    status=404,
                    error_code="github_not_found",
                )
                return create_response(
                    404, {"error": "GitHub project could not be found."}
                )
            # Other API errors -> 502
            latency = perf_counter() - start_time
            log_event(
                "error",
                f"GitHub API error: {e}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=502,
                error_code="github_api_error",
            )
            return create_response(
                502, {"error": "External license information could not be retrieved."}
            )

        # Check compatibility
        is_compatible = check_license_compatibility(
            artifact_license, github_license
        )

        # Log and return result
        latency = perf_counter() - start_time
        log_event(
            "info",
            f"License check result for {artifact_id}: {is_compatible} "
            f"(artifact={artifact_license}, github={github_license})",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )
        return create_response(200, is_compatible)

    except Exception as e:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in license_check: {e}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
