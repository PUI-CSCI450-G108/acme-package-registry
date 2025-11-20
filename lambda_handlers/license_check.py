"""Lambda handler for POST /artifact/model/{id}/license-check."""

import json
from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import (
    create_response,
    load_artifact_from_s3,
    log_event,
)
from src.github_license import (
    fetch_github_license,
    check_license_compatibility,
    parse_github_url,
)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Check license compatibility between a model and a GitHub repository.

    This endpoint determines if a HuggingFace model's license is compatible
    with a GitHub repository's license for fine-tuning and inference usage.
    """

    start_time = perf_counter()
    artifact_id = None
    github_url = None

    try:
        log_event(
            "info",
            f"license_check invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

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

        # Extract path parameters
        path_params = event.get("pathParameters", {})
        artifact_id = path_params.get("id")

        # Validate artifact_id
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
                400,
                {
                    "error": "The license check request is malformed or references an unsupported usage context."
                },
            )

        # Parse request body
        try:
            body = json.loads(event.get("body", "{}"))
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
            return create_response(
                400,
                {
                    "error": "The license check request is malformed or references an unsupported usage context."
                },
            )

        # Extract github_url from request body
        github_url = body.get("github_url")

        if not github_url:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing github_url in license_check request",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="missing_github_url",
            )
            return create_response(
                400,
                {
                    "error": "The license check request is malformed or references an unsupported usage context."
                },
            )

        # Validate GitHub URL format
        parsed = parse_github_url(github_url)
        if not parsed:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Invalid GitHub URL format: {github_url}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="invalid_github_url",
            )
            return create_response(
                400,
                {
                    "error": "The license check request is malformed or references an unsupported usage context."
                },
            )

        # Load artifact from S3
        artifact_data = load_artifact_from_s3(artifact_id)
        if not artifact_data:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(
                404,
                {"error": "The artifact or GitHub project could not be found."}
            )

        # Extract model license from artifact
        # The license score is stored, but we need the actual license string
        # Try to get it from the stored artifact metadata
        model_license = None

        # Check if we have license info stored
        if "license_info" in artifact_data:
            model_license = artifact_data["license_info"]
        elif "license" in artifact_data:
            # Fallback: might be stored directly
            license_value = artifact_data["license"]
            if isinstance(license_value, str):
                model_license = license_value

        # If no license stored, we need to re-pull the model info
        if not model_license:
            log_event(
                "info",
                f"No license info stored for artifact {artifact_id}, attempting to re-fetch",
                event=event,
                context=context,
                model_id=artifact_id,
            )

            # Try to get from URL
            url = artifact_data.get("url")
            if url:
                try:
                    from src.metrics.helpers.pull_model import pull_model_info
                    model_info = pull_model_info(url)

                    if model_info:
                        # Extract license from cardData
                        if hasattr(model_info, "cardData") and model_info.cardData:
                            model_license = model_info.cardData.get("license")
                except Exception as e:
                    log_event(
                        "warning",
                        f"Error re-fetching model info: {e}",
                        event=event,
                        context=context,
                        model_id=artifact_id,
                    )

        if not model_license:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Could not determine license for artifact {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="license_not_found",
            )
            return create_response(
                404,
                {"error": "The artifact or GitHub project could not be found."}
            )

        # Fetch GitHub repository license
        log_event(
            "info",
            f"Fetching license from GitHub: {github_url}",
            event=event,
            context=context,
            model_id=artifact_id,
        )

        github_license = fetch_github_license(github_url)

        if not github_license:
            latency = perf_counter() - start_time
            log_event(
                "error",
                f"Could not fetch license from GitHub: {github_url}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=502,
                error_code="github_license_fetch_failed",
            )
            return create_response(
                502,
                {"error": "External license information could not be retrieved."}
            )

        # Check license compatibility
        is_compatible, reason = check_license_compatibility(
            model_license, github_license
        )

        log_event(
            "info",
            f"License compatibility check: model={model_license}, github={github_license}, "
            f"compatible={is_compatible}, reason={reason}",
            event=event,
            context=context,
            model_id=artifact_id,
        )

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"License check completed for artifact {artifact_id}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )

        # Return boolean result
        return create_response(200, is_compatible)

    except Exception as exc:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in license_check: {exc}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(
            500,
            {"error": "External license information could not be retrieved."}
        )
