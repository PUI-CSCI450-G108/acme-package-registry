"""
Lambda handler for GET /health/live

Simple health check endpoint. Returns only whether the service is available.
"""

import json


def handler(event, context):
    """
    Simple liveliness check. If endpoint is reachable and returns 200, the service is considered live.
    """
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "UP"})
    }
