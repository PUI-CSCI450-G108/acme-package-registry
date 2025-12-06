"""
Lambda handler for POST /artifact/byRegEx - regex search over names & model cards.

Uses list_all_artifacts_from_s3() so results are always a subset
of the "directory" results.
"""

import json
import logging
import re
from time import perf_counter
from typing import Dict, Any, Tuple, Optional

from lambda_handlers.utils import (
    create_response,
    list_all_artifacts_from_s3,
    log_event,
)

# Configure logging for Lambda (outputs to CloudWatch Logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s %(message)s'
)

# ---------------------------------------------------------------------------
# Simple regex safety guardrails (for POST /artifact/byRegEx)
# ---------------------------------------------------------------------------

MAX_REGEX_LENGTH = 256  # prevent absurdly long patterns


def is_safe_regex(pattern: str) -> Tuple[bool, Optional[str]]:
    """
    Heuristic checks to avoid obviously dangerous regexes that can cause
    catastrophic backtracking.

    This is NOT a perfect regex safety checker, but it will catch the
    examples like:
      (a|aa)*$
      (a+)+$
      (a{1,99999}){1,99999}$
    and most similarly bad constructions.
    """
    if not pattern:
        return False, "Regex must be non-empty."
    if len(pattern) > MAX_REGEX_LENGTH:
        return False, f"Regex is too long (>{MAX_REGEX_LENGTH} characters)."

    # 1) Nested quantifiers like (a+)+, (.+)+, (a*)+, (.*)+, etc.
    nested_quantifiers = [
        r"\([^)]*?\+[^)]*?\)\s*\+",  # ( ...+... )+
        r"\([^)]*?\*[^)]*?\)\s*\+",  # ( ...*... )+
        r"\([^)]*?\+[^)]*?\)\s*\*",  # ( ...+... )*
        r"\([^)]*?\*[^)]*?\)\s*\*",  # ( ...*... )*
    ]
    for bad in nested_quantifiers:
        if re.search(bad, pattern):
            return False, "Regex contains nested quantifiers that can cause catastrophic backtracking."

    # 2) Massive numeric quantifiers like {1,99999} (upper bound with 5+ digits)
    if re.search(r"\{\s*\d+\s*,\s*\d{5,}\s*\}", pattern):
        return False, "Regex contains extremely large numeric quantifiers."

    # 3) Very broad '.*' wrapped in outer quantifiers (e.g., (.*)+)
    if re.search(r"\(\s*\.\*\s*\)\s*[\+\*]", pattern):
        return False, "Regex contains patterns like (.*)+ that are unsafe."

    return True, None


def _handle_post_by_regex(event: Dict[str, Any],
                          context: Any,
                          start_time: float) -> Dict:
    """
    New behavior: POST /artifact/byRegEx

    Request body (per spec):
    {
        "regex": "<pattern>"
    }

    Searches over artifact names and model cards.
    Results are a subset of list_all_artifacts_from_s3().
    """
    # Parse JSON body
    raw_body = event.get("body") or ""
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Invalid JSON body for artifact_by_regex",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="invalid_json",
        )
        return create_response(400, {"error": "Request body must be valid JSON."})

    # Spec: { "regex": "" }
    regex_raw = body.get("regex")

    # First: enforce that it's a string at all
    if not isinstance(regex_raw, str):
        latency = perf_counter() - start_time
        log_event(
            "warning",
            "Regex must be a string",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="regex_not_string",
        )
        return create_response(400, {"error": "Field 'regex' must be a non-empty string."})

    regex_pattern: str = regex_raw

    is_safe, reason = is_safe_regex(regex_pattern)
    if not is_safe:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            f"Unsafe or invalid regex: {reason}",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="unsafe_regex",
        )
        return create_response(400, {"error": f"Invalid or unsafe regex: {reason}"})

    # Try compiling the regex – now regex_pattern is known to be a str
    try:
        compiled = re.compile(regex_pattern, flags=re.IGNORECASE)
    except re.error as re_err:
        latency = perf_counter() - start_time
        log_event(
            "warning",
            f"Regex compilation failed: {re_err}",
            event=event,
            context=context,
            latency=latency,
            status=400,
            error_code="invalid_regex",
        )
        return create_response(400, {"error": f"Invalid regex: {str(re_err)}"})

    # Directory source of truth
    all_artifacts = list_all_artifacts_from_s3()

    matching_artifacts = []
    for artifact_id, artifact_data in all_artifacts.items():
        metadata = artifact_data.get("metadata", {})

        name = metadata.get("name", "") or ""
        model_card = (
            metadata.get("model_card", "")
            or metadata.get("card", "")
            or ""
        )

        # Add more fields to this blob if you want broader search:
        searchable_text = f"{name}\n{model_card}"

        if compiled.search(searchable_text):
            matching_artifacts.append(metadata)

    latency = perf_counter() - start_time
    log_event(
        "info",
        f"artifact_by_regex search complete. pattern={regex_pattern!r}, "
        f"matches={len(matching_artifacts)}",
        event=event,
        context=context,
        model_id=regex_pattern,
        latency=latency,
        status=200,
    )
    # Empty list is fine: "subset of directory" may be size 0.
    return create_response(200, matching_artifacts)


def handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for POST /artifact/byRegEx - regex search.

    API Gateway Event Structure (typical):
    - event['httpMethod']  - Expected to be "POST"
    - event['body']        - JSON: {"regex": "..."}
    """
    start_time = perf_counter()

    try:
        log_event(
            "info",
            f"artifact_by_regex invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        http_method = event.get("httpMethod")

        # Handle OPTIONS preflight
        if http_method == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight in artifact_by_regex",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Only POST is supported
        if http_method == "POST":
            return _handle_post_by_regex(event, context, start_time)

        # Anything else is not allowed
        latency = perf_counter() - start_time
        log_event(
            "warning",
            f"Unsupported method {http_method} in artifact_by_regex",
            event=event,
            context=context,
            latency=latency,
            status=405,
            error_code="method_not_allowed",
        )
        return create_response(405, {"error": "Method not allowed."})

    except Exception as e:
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in artifact_by_regex: {e}",
            event=event,
            context=context,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(e)}"})
