"""Lambda handler for POST /artifacts/detailed.

Returns paginated detailed artifact information including metadata and ratings.
"""

import json
import os
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Sequence

from lambda_handlers.utils import create_response, list_all_artifacts_from_s3, log_event

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
        if types_filter and metadata.get("type") not in types_filter:
            return False

    return True


def _build_detailed_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Build a detailed artifact response with metadata and data fields."""
    metadata = artifact.get("metadata", {})
    rating = artifact.get("rating", {})
    url = artifact.get("url", "")

    # Build data field with scores from rating
    data = {
        "url": url,
        "net_score": rating.get("net_score") if rating else None,
    }

    # Add version if available in rating
    if rating and "net_score_version" in rating:
        metadata["version"] = rating["net_score_version"]

    return {
        "metadata": metadata,
        "data": data
    }


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
                results[artifact_id] = _build_detailed_artifact(artifact)

    return sorted(
        results.values(),
        key=lambda item: (
            str(item.get("metadata", {}).get("name", "")).lower(),
            str(item.get("metadata", {}).get("id", ""))
        )
    )


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle POST /artifacts/detailed requests."""

    start_time = perf_counter()

    try:
        log_event(
            "info",
            f"list_artifacts_detailed invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for list_artifacts_detailed",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        offset_param = event.get("queryStringParameters", {}).get("offset") if event.get("queryStringParameters") else None
        offset = _normalize_offset(offset_param)
        if offset is None:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid offset parameter supplied",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_offset",
            )
            return create_response(400, {"error": "Invalid offset parameter."})

        body_content = event.get("body", "[]")
        if body_content is None:
            body_content = "[]"

        try:
            queries = json.loads(body_content) if isinstance(body_content, str) else body_content
        except json.JSONDecodeError:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Invalid JSON payload for list_artifacts_detailed",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_payload",
            )
            return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})

        if not isinstance(queries, list) or not queries:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Artifact queries missing or not a list",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="invalid_query",
            )
            return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})

        for query in queries:
            if not isinstance(query, dict) or not isinstance(query.get("name"), str) or not query.get("name"):
                latency = perf_counter() - start_time
                log_event(
                    "warning",
                    "Invalid artifact query entry",
                    event=event,
                    context=context,
                    latency=latency,
                    status=400,
                    error_code="invalid_query_entry",
                )
                return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})
            if "types" in query and (
                not isinstance(query["types"], list)
                or not all(isinstance(item, str) and item for item in query["types"])
            ):
                latency = perf_counter() - start_time
                log_event(
                    "warning",
                    "Invalid artifact types filter",
                    event=event,
                    context=context,
                    latency=latency,
                    status=400,
                    error_code="invalid_types_filter",
                )
                return create_response(400, {"error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."})

        artifacts_map = list_all_artifacts_from_s3()
        matches = _collect_matches(artifacts_map.values(), queries)

        if len(matches) > MAX_RESULTS:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Artifact query exceeded max results",
                event=event,
                context=context,
                latency=latency,
                status=413,
                error_code="too_many_results",
            )
            return create_response(413, {"error": "Too many artifacts returned."})

        page = matches[offset : offset + PAGE_SIZE]
        headers: Dict[str, str] = {}

        next_offset = offset + len(page)
        if next_offset < len(matches):
            headers["offset"] = str(next_offset)

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Returning {len(page)} detailed artifact(s) for list_artifacts_detailed",
            event=event,
            context=context,
            latency=latency,
            status=200,
        )
        return create_response(200, page, headers=headers if headers else None)
    except Exception as exc:  # pragma: no cover - guard against unexpected failures
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in list_artifacts_detailed: {exc}",
            event=event,
            context=context,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
