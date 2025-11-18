"""
Lambda handler for POST /artifact/byRegEx

Searches for artifacts using regex over artifact names.
Returns matching artifact *metadata* entries (id, name, version, type).
"""

import json
import re
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Sequence

from packaging import version as pkg_version
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion

from lambda_handlers.utils import create_response, list_all_artifacts_from_s3, log_event


# -------------------------
# Inlined semver + search helpers
# -------------------------

def _build_specifier(range_expression: str) -> Optional[SpecifierSet]:
    expr = (range_expression or "").strip()
    if not expr or expr == "*":
        return None
    try:
        if expr.startswith("^"):
            spec = _caret_to_specifier(expr[1:].strip())
        elif expr.startswith("~"):
            spec = _tilde_to_specifier(expr[1:].strip())
        elif " - " in expr:
            lo, hi = (p.strip() for p in expr.split(" - ", 1))
            if not lo or not hi:
                raise ValueError("Invalid range expression")
            spec = f">={lo},<={hi}"
        else:
            spec = f"=={expr}"
        return SpecifierSet(spec)
    except (InvalidSpecifier, InvalidVersion, ValueError):
        return None


def _caret_to_specifier(base_version: str) -> str:
    base = pkg_version.Version(base_version)
    release = list(base.release)
    if not release:
        raise InvalidVersion(f"Invalid version: {base_version}")
    first_non_zero = 0
    for i, v in enumerate(release):
        if v != 0:
            first_non_zero = i
            break
    else:
        # all zeros -> exact match only
        return f"=={base_version}"
    upper = release[: first_non_zero + 1]
    upper[first_non_zero] += 1
    upper_bound = ".".join(str(p) for p in upper)
    return f">={base_version},<{upper_bound}"


def _tilde_to_specifier(base_version: str) -> str:
    base = pkg_version.Version(base_version)
    release = list(base.release)
    if not release:
        raise InvalidVersion(f"Invalid version: {base_version}")
    if len(release) == 1:
        upper = [release[0] + 1]
    else:
        upper = release[:2]
        upper[1] += 1
    upper_bound = ".".join(str(p) for p in upper)
    return f">={base_version},<{upper_bound}"


def _version_matches(ver: str, range_expression: Optional[str]) -> bool:
    if not range_expression or range_expression == "*":
        return True
    spec = _build_specifier(range_expression)
    if spec is None:
        # Fallback to literal equality on invalid range expressions
        return ver == (range_expression or "").strip()
    try:
        pv = pkg_version.Version(ver)
    except InvalidVersion:
        # If stored version isn't parseable, fall back to literal equality
        return ver == (range_expression or "").strip()
    return pv in spec


def _search_artifacts_with_regex_and_version(
    artifacts: Iterable[Dict[str, Any]],
    *,
    name_regex: str,
    version_expr: Optional[str] = None,
    types: Optional[Sequence[str]] = None,
    id_regex: Optional[str] = None,
    flags: int = re.IGNORECASE,
) -> List[Dict[str, Any]]:
    """
    Core search: regex over name/id + semver constraints over version.
    Returns a sorted list of metadata dicts (by name, then version).
    """
    try:
        name_pat = re.compile(name_regex, flags)
    except re.error as e:
        raise ValueError(f"Invalid name_regex: {e}")

    id_pat = None
    if id_regex:
        try:
            id_pat = re.compile(id_regex, flags)
        except re.error as e:
            raise ValueError(f"Invalid id_regex: {e}")

    allow_types = set(t.strip() for t in (types or [])) or None
    results_by_id: Dict[str, Dict[str, Any]] = {}

    for artifact in artifacts:
        md = artifact.get("metadata", {}) or {}
        aid = str(md.get("id", "") or "")
        aname = str(md.get("name", "") or "")
        aver = str(md.get("version", "") or "")
        atype = md.get("type")

        if not aname or not aid:
            continue
        if allow_types is not None and atype not in allow_types:
            continue
        if not name_pat.search(aname):
            continue
        if id_pat and not id_pat.search(aid):
            continue
        if not _version_matches(aver, version_expr):
            continue

        results_by_id[aid] = md

    return sorted(
        results_by_id.values(),
        key=lambda m: (str(m.get("name", "")).lower(), str(m.get("version", ""))),
    )


# -------------------------
# Lambda handler
# -------------------------

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for POST /artifact/byRegEx

    Request body (JSON):
    {
      "regex": "<required regex>"
    }
    """
    start_time = perf_counter()

    try:
        log_event(
            "info",
            f"search_artifacts invoked: {json.dumps(event)}",
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
            return create_response(400, {"error": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"})

        # Extract regex from request body (per OpenAPI spec)
        regex = body.get("regex")
        if not isinstance(regex, str) or not regex.strip():
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing or invalid regex",
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

        # Execute search over artifact names
        try:
            results = _search_artifacts_with_regex_and_version(
                artifacts_map.values(),
                name_regex=regex,
                version_expr=None,
                types=None,
                id_regex=None,
            )
        except ValueError as e:
            # invalid regex -> 400
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
            return create_response(400, {"error": "There is missing field(s) in the artifact_regex or it is formed improperly, or is invalid"})

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
            return create_response(404, {"error": "No artifact found under this regex."})

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Found {len(results)} matching artifact(s) for regex '{regex}'",
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
