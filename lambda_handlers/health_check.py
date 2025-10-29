"""
Lambda handler for GET /health

Simple health check endpoint.
"""

import logging
from typing import Dict, Any

from lambda_handlers.utils import s3_client, BUCKET_NAME

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /health

    Simple health check endpoint.
    """
    # Count artifacts in S3
    artifact_count = 0
    if s3_client and BUCKET_NAME:
        try:
            response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="artifacts/")
            artifact_count = response.get("KeyCount", 0)
        except Exception as e:
            # Ignore errors in artifact count for health check, but log for debugging
            logger.warning(f"Failed to count artifacts in S3 during health check: {e}", exc_info=True)
    return {
        "status": "healthy",
        "service": "acme-package-registry",
        "artifacts_count": artifact_count
    }
