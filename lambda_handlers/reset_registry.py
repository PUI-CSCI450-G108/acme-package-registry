"""Lambda handler for DELETE /reset.

Resets the registry by deleting all persisted artifacts.
"""

import json
from time import perf_counter
from typing import Any, Dict

from botocore.exceptions import ClientError

from lambda_handlers.utils import create_response, delete_all_artifacts_from_s3, log_event


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle DELETE /reset requests."""

    start_time = perf_counter()

    try:
        log_event(
            "info",
            f"reset_registry invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for reset_registry",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        try:
            deleted = delete_all_artifacts_from_s3()
        except ClientError:
            latency = perf_counter() - start_time
            log_event(
                "error",
                "Failed to delete artifacts during registry reset",
                event=event,
                context=context,
                latency=latency,
                status=500,
                error_code="reset_failed",
            )
            return create_response(500, {"error": "Failed to reset registry storage."})

        body = {
            "status": "reset",
            "deleted_artifacts": deleted,
        }
        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Registry reset completed, deleted {deleted} artifacts",
            event=event,
            context=context,
            latency=latency,
            status=200,
        )
        return create_response(200, body)
    except Exception as exc:  # pragma: no cover - safety net for unexpected errors
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in reset_registry: {exc}",
            event=event,
            context=context,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})

