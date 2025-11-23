"""Lambda handler for user login (/authenticate)."""

import json
from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import create_response, handle_cors_preflight, log_event
from src.auth.exceptions import AuthError
from src.auth.service import get_default_auth_service


def handler(event: Dict[str, Any], context: Any) -> Dict:
    # Track elapsed time for structured logging.
    start_time = perf_counter()
    # Short-circuit OPTIONS requests before doing any parsing.
    cors_response = handle_cors_preflight(event)
    if cors_response is not None:
        return cors_response

    try:
        # Body arrives as a JSON string from API Gateway; normalize to a dict.
        body_str = event.get("body", "{}")
        body = json.loads(body_str) if isinstance(body_str, str) else body_str
    except json.JSONDecodeError:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Invalid JSON payload for login",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="invalid_payload",
        )
        return create_response(400, {"error": "Invalid JSON payload."})

    # OpenAPI schema nests credentials under "user" and "secret" objects.
    user_info = body.get("user", {}) if isinstance(body, dict) else {}
    secret_info = body.get("secret", {}) if isinstance(body, dict) else {}
    username = (user_info or {}).get("name")
    password = (secret_info or {}).get("password")

    if not username or not password:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Missing credentials for login",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="missing_credentials",
        )
        return create_response(400, {"error": "Missing username or password."})

    service = get_default_auth_service()

    try:
        token, payload = service.login(username, password)
    except AuthError:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Login failed",
            event=event,
            context=context,
            latency=latency,
            status=401,
            error_code="invalid_credentials",
        )
        return create_response(401, {"error": "Invalid username or password."})
    except Exception as exc:  # pragma: no cover - unexpected
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error during login: {exc}",
            event=event,
            context=context,
            latency=latency,
            status=500,
            error_code="login_failure",
            exc_info=True,
        )
        return create_response(500, {"error": "Internal server error."})

    latency = perf_counter() - start_time
    log_event(
        "info",
        "Login succeeded",
        event=event,
        context=context,
        latency=latency,
        status=200,
        extra={"jti": payload.jti, "username": username},
    )
    return create_response(200, f"bearer {token}")
