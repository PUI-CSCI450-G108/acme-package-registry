"""
Lambda handler for GET /health

Simple health check endpoint.
"""

from time import perf_counter
from typing import Any, Dict
from datetime import datetime, timedelta, timezone
from lambda_handlers.utils import BUCKET_NAME, create_response, handle_cors_preflight, s3_client, log_event


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /health

    Simple health check endpoint.
    """
    start_time = perf_counter()

    log_event(
        "info",
        "health_check invoked",
        event=event,
        context=context,
    )

    # Handle CORS preflight
    cors_response = handle_cors_preflight(event)
    if cors_response:
        latency = perf_counter() - start_time
        log_event(
            "info",
            "Handled OPTIONS preflight for health_check",
            event=event,
            context=context,
            latency=latency,
            status=cors_response.get("statusCode"),
        )
        return cors_response

    # Count artifacts in S3
    artifact_count = 0
    if s3_client and BUCKET_NAME:
        try:
            response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME, Prefix="artifacts/"
            )
            artifact_count = response.get("KeyCount", 0)
        except Exception as e:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Failed to count artifacts in S3 during health check: {e}",
                event=event,
                context=context,
                latency=latency,
                status=200,
                error_code="artifact_count_failed",
                exc_info=True,
            )
    latency = perf_counter() - start_time
    log_event(
        "info",
        "health_check succeeded",
        event=event,
        context=context,
        latency=latency,
        status=200,
    )


    now = datetime.now(timezone.utc)
    window_minutes = 60
    window_start = now - timedelta(minutes=window_minutes)

    return create_response(
        200,
        {
            "status": "healthy",
            "service": "acme-package-registry",
            "artifacts_count": artifact_count,"timestamp": now.isoformat().replace("+00:00", "Z"),
            "window_minutes": window_minutes,
            "window_start": window_start.isoformat().replace("+00:00", "Z"),
            "window_end": now.isoformat().replace("+00:00", "Z"),
        },
    )
