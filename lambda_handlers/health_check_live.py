"""
Lambda handler for GET /health/live

Simple health check endpoint. Returns only whether the service is available.
"""

import json
from typing import Dict, Any
from lambda_handlers.utils import handle_cors_preflight
	
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Simple liveness check. If endpoint is reachable and returns 200, the service is considered live.
    """
    if event.get("httpMethod", "") == "OPTIONS":
        return handle_cors_preflight(event)
    
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "UP"})
    }
