"""
Lambda handler for POST /artifact/byRegEx

Searches for artifacts using regex over artifact names and READMEs.
Returns matching artifact *metadata* entries (id, name, type).
"""

import json
import re
from time import perf_counter
from typing import Any, Dict, Iterable, List

from lambda_handlers.utils import create_response, list_all_artifacts_from_s3, log_event


# Regex complexity limits
MAX_PATTERN_LENGTH = 200
MAX_QUANTIFIER_VALUE = 1000
MAX_NESTING_DEPTH = 3


class UnsafeRegexError(Exception):
    """Raised when regex pattern is deemed unsafe due to complexity."""
    pass


def _check_regex_complexity(pattern: str) -> None:
    """
    Check if a regex pattern is safe to execute.

    Detects patterns that could cause catastrophic backtracking or excessive
    resource consumption. This is necessary because signal-based timeouts
    don't work in AWS Lambda.

    Args:
        pattern: Regular expression pattern string

    Raises:
        UnsafeRegexError: If pattern is deemed unsafe

    Checks performed:
    1. Pattern length limit
    2. Nested quantifiers (e.g., (a+)+, (a*)*)
    3. Large quantifier ranges (e.g., a{1,99999})
    4. Overlapping alternations with quantifiers (e.g., (a|aa)*)
    5. Excessive nesting depth
    """
    # Check 1: Pattern length
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise UnsafeRegexError(
            f"Pattern too long ({len(pattern)} chars, max {MAX_PATTERN_LENGTH})"
        )

    # Check 2: Detect nested quantifiers - common cause of catastrophic backtracking
    # Patterns like (a+)+, (a*)*, (a+)*, ((a)+)+, etc.
    nested_quantifier_patterns = [
        r'\([^)]*[*+?]\)[*+?{]',  # (...)+ or (...)* or (...)?
        r'\([^)]*\{[^}]+\}\)[*+?{]',  # (...{n,m})+ patterns
        r'\([^)]*[*+?][^)]*\)[*+?{]',  # Multiple quantifiers in group
    ]

    for check_pattern in nested_quantifier_patterns:
        if re.search(check_pattern, pattern):
            raise UnsafeRegexError(
                "Nested quantifiers detected - potential catastrophic backtracking"
            )

    # Check 3: Detect large quantifier ranges
    # Patterns like a{1,99999} or a{9999,}
    quantifier_ranges = re.findall(r'\{(\d+)(?:,(\d*))?\}', pattern)
    for min_val, max_val in quantifier_ranges:
        min_int = int(min_val) if min_val else 0
        max_int = int(max_val) if max_val else min_int

        if min_int > MAX_QUANTIFIER_VALUE:
            raise UnsafeRegexError(
                f"Quantifier minimum too large ({min_int}, max {MAX_QUANTIFIER_VALUE})"
            )
        if max_val and max_int > MAX_QUANTIFIER_VALUE:
            raise UnsafeRegexError(
                f"Quantifier maximum too large ({max_int}, max {MAX_QUANTIFIER_VALUE})"
            )

    # Check 4: Detect overlapping alternations with quantifiers
    # Patterns like (a|aa)*, (ab|abc)+, etc.
    # This is a simplified check - looks for alternation groups followed by quantifiers
    if re.search(r'\([^)]*\|[^)]*\)[*+{]', pattern):
        # Further check if alternations might overlap
        # Extract the alternation group
        alt_groups = re.findall(r'\(([^)]*\|[^)]*)\)[*+{]', pattern)
        for group in alt_groups:
            alternatives = group.split('|')
            # Check if any alternative is a prefix of another
            for i, alt1 in enumerate(alternatives):
                for alt2 in alternatives[i+1:]:
                    if alt1.startswith(alt2) or alt2.startswith(alt1):
                        raise UnsafeRegexError(
                            "Overlapping alternations with quantifiers detected - "
                            "potential catastrophic backtracking"
                        )

    # Check 5: Detect excessive nesting depth
    max_depth = 0
    current_depth = 0
    for char in pattern:
        if char == '(':
            current_depth += 1
            max_depth = max(max_depth, current_depth)
        elif char == ')':
            current_depth -= 1

    if max_depth > MAX_NESTING_DEPTH:
        raise UnsafeRegexError(
            f"Pattern nesting too deep ({max_depth} levels, max {MAX_NESTING_DEPTH})"
        )


def _search_artifacts_by_regex(
    artifacts: Iterable[Dict[str, Any]],
    regex_pattern: str,
) -> List[Dict[str, Any]]:
    """
    Search artifacts using regex over artifact names.

    Note: The spec mentions searching READMEs as well, but README data
    is not currently stored in artifacts. This implementation searches
    only artifact names.

    Args:
        artifacts: Iterable of artifact dictionaries
        regex_pattern: Regular expression pattern to match

    Returns:
        List of matching artifact metadata dicts, sorted by name

    Raises:
        ValueError: If regex pattern is invalid
        UnsafeRegexError: If regex pattern is too complex/dangerous
    """
    # Check complexity before compiling
    _check_regex_complexity(regex_pattern)

    try:
        pattern = re.compile(regex_pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    results_by_id: Dict[str, Dict[str, Any]] = {}

    for artifact in artifacts:
        md = artifact.get("metadata", {}) or {}
        artifact_id = str(md.get("id", "") or "")
        artifact_name = str(md.get("name", "") or "")
        artifact_type = md.get("type")

        if not artifact_name or not artifact_id:
            continue

        # Search artifact name
        if pattern.search(artifact_name):
            results_by_id[artifact_id] = {
                "name": artifact_name,
                "id": artifact_id,
                "type": artifact_type
            }

    return sorted(
        results_by_id.values(),
        key=lambda m: str(m.get("name", "")).lower()
    )


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for POST /artifact/byRegEx

    Request body (JSON):
    {
      "regex": "<required regex pattern>"
    }

    Response: Array of matching artifact metadata
    [
      {"name": "...", "id": "...", "type": "..."},
      ...
    ]
    """
    start_time = perf_counter()

    try:
        log_event(
            "info",
            f"search_artifacts (byRegEx) invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        # CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for search_artifacts",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Parse JSON body
        raw = event.get("body", "{}")
        try:
            body = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid JSON payload for search_artifacts",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_payload",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"
            })

        # Validate regex field
        regex_pattern = body.get("regex")
        if not isinstance(regex_pattern, str) or not regex_pattern.strip():
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing or invalid regex field",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_regex",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"
            })

        # Load artifacts from S3
        artifacts_map = list_all_artifacts_from_s3()

        # Execute search with complexity protection
        try:
            results = _search_artifacts_by_regex(
                artifacts_map.values(),
                regex_pattern=regex_pattern,
            )
        except UnsafeRegexError as e:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Unsafe regex pattern rejected: {e}",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="unsafe_regex",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"
            })
        except ValueError as e:
            # Invalid regex pattern
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Invalid regex provided: {e}",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_regex",
            )
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"
            })

        if not results:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "No matching artifacts found",
                event=event,
                context=context,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {
                "error": "No artifact found under this regex."
            })

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Found {len(results)} matching artifact(s) for regex '{regex_pattern}'",
            event=event,
            context=context,
            latency=latency,
            status=200,
        )
        return create_response(200, results)

    except Exception as exc:  # pragma: no cover
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in search_artifacts: {exc}",
            event=event,
            context=context,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
