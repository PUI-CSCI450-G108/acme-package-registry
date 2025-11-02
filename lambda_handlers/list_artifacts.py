"""Lambda handler for POST /artifacts.

Returns paginated metadata for artifacts that match the supplied queries.
"""

import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

from packaging import version as pkg_version
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion

from lambda_handlers.utils import create_response, list_all_artifacts_from_s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PAGE_SIZE = int(os.getenv("ARTIFACTS_PAGE_SIZE", "50"))
MAX_RESULTS = int(os.getenv("ARTIFACTS_MAX_RESULTS", "250"))


def _normalize_offset(value: Optional[str]) -> Optional[int]:
    if value in (None, ""):
        return 0

    try:
        offset = int(value)
    except (TypeError, ValueError):
        return None

    return offset if offset >= 0 else None


def _build_specifier(range_expression: str) -> Optional[SpecifierSet]:
    expression = range_expression.strip()
    if not expression or expression == "*":
        return None

    try:
        if expression.startswith("^"):
            spec = _caret_to_specifier(expression[1:].strip())
        elif expression.startswith("~"):
            spec = _tilde_to_specifier(expression[1:].strip())
        elif "-" in expression:
            lower, upper = (part.strip() for part in expression.split("-", 1))
            if not lower or not upper:
                raise ValueError("Invalid range expression")
            spec = f">={lower},<={upper}"
        else:
            spec = f"=={expression}"

        return SpecifierSet(spec)
    except (InvalidSpecifier, InvalidVersion, ValueError):
        return None


def _caret_to_specifier(base_version: str) -> str:
    base = pkg_version.Version(base_version)
    release = list(base.release)
    if not release:
        raise InvalidVersion(f"Invalid version: {base_version}")

    first_non_zero = 0
    for idx, value in enumerate(release):
        if value != 0:
            first_non_zero = idx
            break
    else:
        # All parts are zero; caret should only match the exact version
        return f"=={base_version}"

    upper_release = release[: first_non_zero + 1]
    upper_release[first_non_zero] += 1
    upper_bound = ".".join(str(part) for part in upper_release)
    return f">={base_version},<{upper_bound}"


def _tilde_to_specifier(base_version: str) -> str:
    base = pkg_version.Version(base_version)
    release = list(base.release)
    if not release:
        raise InvalidVersion(f"Invalid version: {base_version}")

    if len(release) == 1:
        upper_release = [release[0] + 1]
    else:
        upper_release = release[:2]
        upper_release[1] += 1

    upper_bound = ".".join(str(part) for part in upper_release)
    return f">={base_version},<{upper_bound}"


def _version_matches(version: str, range_expression: Optional[str]) -> bool:
    if not range_expression:
        return True

    specifier = _build_specifier(range_expression)
    if specifier is None:
        return version == range_expression.strip()

    try:
        parsed_version = pkg_version.Version(version)
    except InvalidVersion:
        return version == range_expression.strip()

    return parsed_version in specifier


def _matches_query(metadata: Dict[str, Any], query: Dict[str, Any]) -> bool:
    name_query = query.get("name")
    if not isinstance(name_query, str) or not name_query:
        return False

    artifact_name = str(metadata.get("name", ""))
    if name_query != "*" and artifact_name.lower() != name_query.lower():
        return False

    types_filter = query.get("types")
    if types_filter is not None:
        if not isinstance(types_filter, list) or not all(isinstance(t, str) for t in types_filter):
            return False
        if metadata.get("type") not in types_filter:
            return False

    version_query = query.get("version")
    if version_query is not None:
        if not isinstance(version_query, str) or not _version_matches(str(metadata.get("version", "")), version_query):
            return False

    return True


def _collect_matches(
    artifacts: Iterable[Dict[str, Any]], queries: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}

    for query in queries:
        if not isinstance(query, dict):
            continue
        name_query = query.get("name")
        if not isinstance(name_query, str) or not name_query:
            continue

        for artifact in artifacts:
            metadata = artifact.get("metadata", {})
            artifact_id = metadata.get("id")
            if not artifact_id:
                continue

            if _matches_query(metadata, query):
                results[artifact_id] = metadata

    return sorted(
        results.values(), key=lambda item: (str(item.get("name", "")).lower(), str(item.get("version", "")))
    )


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle POST /artifacts requests."""

    try:
        logger.info(f"list_artifacts invoked: {json.dumps(event)}")

        if event.get("httpMethod") == "OPTIONS":
            return create_response(200, {})

        offset_param = event.get("queryStringParameters", {}).get("offset") if event.get("queryStringParameters") else None
        offset = _normalize_offset(offset_param)
        if offset is None:
            return create_response(400, {"error": "Invalid offset parameter."})

        body_content = event.get("body", "[]")
        if body_content is None:
            body_content = "[]"

        try:
            queries = json.loads(body_content) if isinstance(body_content, str) else body_content
        except json.JSONDecodeError:
            return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})

        if not isinstance(queries, list) or not queries:
            return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})

        for query in queries:
            if not isinstance(query, dict) or not isinstance(query.get("name"), str) or not query.get("name"):
                return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})
            if "types" in query and (
                not isinstance(query["types"], list)
                or not all(isinstance(item, str) and item for item in query["types"])
            ):
                return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})
            if "version" in query and query["version"] is not None and not isinstance(query["version"], str):
                return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})

        artifacts_map = list_all_artifacts_from_s3()
        matches = _collect_matches(artifacts_map.values(), queries)

        if len(matches) > MAX_RESULTS:
            return create_response(413, {"error": "Too many artifacts returned."})

        page = matches[offset : offset + PAGE_SIZE]
        headers: Dict[str, str] = {}

        next_offset = offset + len(page)
        if next_offset < len(matches):
            headers["offset"] = str(next_offset)

        return create_response(200, page, headers=headers if headers else None)
    except Exception as exc:  # pragma: no cover - guard against unexpected failures
        logger.error("Unexpected error in list_artifacts", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})

