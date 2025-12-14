"""
Lambda handler for GET /download/{artifact_id}

Streams `data.zip` from S3 to the client as a direct download.
"""

from typing import Any, Dict, Optional
import base64
from lambda_handlers.utils import (
    create_response,
    handle_cors_preflight,
    log_event,
    BUCKET_NAME,
    s3_client,
    ClientError,
)


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

    log_event("info", "download invoked", event=event, context=context, model_id=artifact_id)

    if not artifact_id:
        return create_response(400, {"error": "Missing required path parameter: artifact_id"})

    if not BUCKET_NAME or not s3_client:
        log_event("error", "S3 not configured for download", event=event, context=context)
        return create_response(501, {
            "error": "Download storage not configured",
            "detail": "Missing ARTIFACTS_BUCKET or S3 client"
        })

    # Expected path for the zip bundle
    key = f"artifacts/{artifact_id}/data.zip"

    try:
        obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        data = obj["Body"].read()
    except Exception as e:
        # Try to extract structured info if it's a botocore ClientError
        code = None
        message = None
        try:
            code = getattr(e, "response", {}).get("Error", {}).get("Code")
            message = getattr(e, "response", {}).get("Error", {}).get("Message")
        except Exception:
            pass

        if code in ("404", "NoSuchKey"):
            return create_response(404, {"error": "File not found: data.zip"})

        log_event(
            "error",
            f"S3 get_object error code={code} msg={message} exc={e}",
            event=event,
            context=context,
            model_id=artifact_id,
        )
        return create_response(500, {
            "error": "Storage error",
            "code": code or "Unknown",
            "message": message or str(e),
            "bucket": BUCKET_NAME,
            "key": key,
        })

    b64 = base64.b64encode(data).decode("utf-8")

    # Return binary payload with appropriate headers for browser download
    return {
        "statusCode": 200,
        "isBase64Encoded": True,
        "headers": {
            "Content-Type": "application/zip",
            "Content-Disposition": "attachment; filename=\"data.zip\"",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": b64,
    }
