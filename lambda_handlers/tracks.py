"""
Lambda handler for GET /tracks endpoint.

Returns the list of implementation tracks planned by the student.
"""

from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import create_response, handle_cors_preflight, log_event


# List of tracks planned for implementation
PLANNED_TRACKS = ["Access control track"]


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle GET /tracks requests.

    Returns a JSON response with the list of planned implementation tracks.

    Args:
        event: API Gateway event containing request details
        context: Lambda context object

    Returns:
        API Gateway response with status code and JSON body
    """
    start_time = perf_counter()

    log_event("info", "tracks endpoint invoked", event=event, context=context)

    # Handle CORS preflight
    cors_response = handle_cors_preflight(event)
    if cors_response:
        latency = perf_counter() - start_time
        log_event(
            "info",
            "Handled OPTIONS preflight for tracks",
            event=event,
            context=context,
            latency=latency,
            status=200,
        )
        return cors_response

    # Return track list
    latency = perf_counter() - start_time
    log_event(
        "info",
        "tracks endpoint succeeded",
        event=event,
        context=context,
        latency=latency,
        status=200,
    )

    body = {"plannedTracks": PLANNED_TRACKS}
    return create_response(200, body)
