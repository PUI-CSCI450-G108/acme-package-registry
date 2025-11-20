"""Lambda handler for admin-only user registration (/auth/register)."""

import json
from time import perf_counter
from typing import Any, Dict

from lambda_handlers.utils import (
    create_response,
    get_header,
    handle_cors_preflight,
    log_event,
)
from src.auth.exceptions import AuthError, InvalidTokenError
from src.auth.service import get_default_auth_service


def handler(event: Dict[str, Any], context: Any) -> Dict:
    # Measure handler latency for logging and monitoring.
    start_time = perf_counter()
    # Handle browser preflight requests early.
    cors_response = handle_cors_preflight(event)
    if cors_response is not None:
        return cors_response

    # Admin token is required to gate registration.
    admin_token = get_header(event, "X-Authorization")
    if not admin_token:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Registration attempted without authorization token",
            event=event,
            context=context,
            latency=latency,
            status=401,
            error_code="missing_token",
        )
        return create_response(401, {"error": "Authorization token required."})

    try:
        # Convert JSON body to a dictionary for field extraction.
        body_str = event.get("body", "{}")
        body = json.loads(body_str) if isinstance(body_str, str) else body_str
    except json.JSONDecodeError:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Invalid JSON payload for register",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="invalid_payload",
        )
        return create_response(400, {"error": "Invalid JSON payload."})

    # Split payload according to OpenAPI contract.
    user_info = body.get("user", {}) if isinstance(body, dict) else {}
    permissions = body.get("permissions", {}) if isinstance(body, dict) else {}
    secret_info = body.get("secret", {}) if isinstance(body, dict) else {}

    username = (user_info or {}).get("name")
    is_admin = bool((user_info or {}).get("is_admin"))
    password = (secret_info or {}).get("password")

    if not username or not password:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Missing registration fields",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="missing_fields",
        )
        return create_response(400, {"error": "Missing required fields."})

    can_upload = bool((permissions or {}).get("can_upload"))
    can_search = bool((permissions or {}).get("can_search"))
    can_download = bool((permissions or {}).get("can_download"))

    service = get_default_auth_service()

    try:
        user = service.register_user(
            admin_token=admin_token,
            username=username,
            password=password,
            can_upload=can_upload,
            can_search=can_search,
            can_download=can_download,
            is_admin=is_admin,
        )
    except AuthError:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Registration failed due to insufficient permissions",
            event=event,
            context=context,
            latency=latency,
            status=403,
            error_code="forbidden",
        )
        return create_response(403, {"error": "Admin privileges required."})
    except InvalidTokenError:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Registration failed due to invalid token",
            event=event,
            context=context,
            latency=latency,
            status=401,
            error_code="invalid_token",
        )
        return create_response(401, {"error": "Invalid token."})
    except ValueError as exc:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            f"Invalid registration request: {exc}",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="invalid_request",
        )
        return create_response(400, {"error": str(exc)})
    except Exception as exc:  # pragma: no cover - unexpected
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error during registration: {exc}",
            event=event,
            context=context,
            latency=latency,
            status=500,
            error_code="registration_failure",
            exc_info=True,
        )
        return create_response(500, {"error": "Internal server error."})

    latency = perf_counter() - start_time
    log_event(
        "info",
        "User registered",
        event=event,
        context=context,
        latency=latency,
        status=201,
        extra={"username": user.username},
    )

    response_body = {
        "username": user.username,
        "is_admin": user.is_admin,
        "can_upload": user.can_upload,
        "can_search": user.can_search,
        "can_download": user.can_download,
    }
    return create_response(201, response_body)
