"""Lambda handler for DELETE /reset.

Resets the registry by deleting all persisted artifacts.
"""

import json
import logging
from typing import Any, Dict

from botocore.exceptions import ClientError

from lambda_handlers.utils import create_response, delete_all_artifacts_from_s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle DELETE /reset requests."""

    try:
        logger.info(f"reset_registry invoked: {json.dumps(event)}")

        if event.get("httpMethod") == "OPTIONS":
            return create_response(200, {})

        try:
            deleted = delete_all_artifacts_from_s3()
        except ClientError:
            return create_response(500, {"error": "Failed to reset registry storage."})

        body = {
            "status": "reset",
            "deleted_artifacts": deleted,
        }
        return create_response(200, body)
    except Exception as exc:  # pragma: no cover - safety net for unexpected errors
        logger.error("Unexpected error in reset_registry", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})

