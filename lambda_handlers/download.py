"""
Lambda handler for GET /download

Skeleton endpoint returning a placeholder response.
"""

from typing import Any, Dict, Optional
from lambda_handlers.utils import create_response, handle_cors_preflight, log_event


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Minimal download endpoint skeleton.

    - Handles CORS preflight
    - Returns a 200 with a placeholder body
    """
    # Handle CORS preflight
    cors_response = handle_cors_preflight(event)
    if cors_response:
        log_event(
            "info",
            "Handled OPTIONS preflight for download",
            event=event,
            context=context,
            status=cors_response.get("statusCode"),
        )
        return cors_response

    path_params: Optional[Dict[str, Any]] = event.get("pathParameters") or {}
    artifact_id = None
    try:
        # HTTP API v2: event["pathParameters"]["artifact_id"]
        artifact_id = (event.get("pathParameters") or {}).get("artifact_id")
        # REST API fallback: sometimes under event["pathParameters"] as dict
    except Exception:
        artifact_id = None

    log_event("info", "download skeleton invoked", event=event, context=context, artifact_id=artifact_id)

    if not artifact_id:
        return create_response(400, {"error": "Missing required path parameter: artifact_id"})

    body = {
        "status": "ok",
        "artifact_id": artifact_id,
        "message": "Download endpoint is not yet implemented.",
    }

    return create_response(200, body)
