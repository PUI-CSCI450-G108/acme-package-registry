"""Lambda handler for user logout (/auth/logout)."""

from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import create_response, get_header, handle_cors_preflight, log_event
from src.auth.exceptions import InvalidTokenError
from src.auth.service import get_default_auth_service


def handler(event: Dict[str, Any], context: Any) -> Dict:
    # Capture start time for structured latency logging.
    start_time = perf_counter()
    # Let OPTIONS preflight requests through without further processing.
    cors_response = handle_cors_preflight(event)
    if cors_response is not None:
        return cors_response

    # Token is required to know which session to revoke.
    token = get_header(event, "X-Authorization")
    if not token:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Logout attempted without token",
            event=event,
            context=context,
            latency=latency,
            status=401,
            error_code="missing_token",
        )
        return create_response(401, {"error": "Authorization token required."})

    service = get_default_auth_service()

    try:
        payload = service.logout(token)
    except InvalidTokenError:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Logout failed due to invalid token",
            event=event,
            context=context,
            latency=latency,
            status=401,
            error_code="invalid_token",
        )
        return create_response(401, {"error": "Invalid token."})
    except Exception as exc:  # pragma: no cover - unexpected
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error during logout: {exc}",
            event=event,
            context=context,
            latency=latency,
            status=500,
            error_code="logout_failure",
            exc_info=True,
        )
        return create_response(500, {"error": "Internal server error."})

    latency = perf_counter() - start_time
    log_event(
        "info",
        "Logout succeeded",
        event=event,
        context=context,
        latency=latency,
        status=200,
        extra={"jti": payload.jti, "username": payload.sub},
    )

    return create_response(200, {"message": "Logged out."})
