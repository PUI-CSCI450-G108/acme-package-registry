"""
Lambda handler for POST /artifact/search

Searches for artifacts using regex (name and/or id) and semantic version constraints.
Returns matching artifact *metadata* entries (id, name, version, type).
"""

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from packaging import version as pkg_version
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion

from lambda_handlers.utils import create_response, list_all_artifacts_from_s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
    Lambda handler for POST /artifact/search

    Request body (JSON):
    {
      "name_regex": "<required regex>",
      "version": "<optional version spec>",
      "types": ["model","dataset","code"],     # optional
      "id_regex": "<optional regex>"
    }
    """
    try:
        logger.info(f"search_artifacts invoked: {json.dumps(event)}")

        # CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return create_response(200, {})

        # Parse JSON body
        raw = event.get("body", "{}")
        try:
            body = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return create_response(400, {"error": "Invalid JSON body."})

        name_regex = body.get("name_regex")
        if not isinstance(name_regex, str) or not name_regex.strip():
            # Match your existing wording style for 400s
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."
            })

        version_expr = body.get("version")
        id_regex = body.get("id_regex")
        types = body.get("types")

        # Validate 'types' if present
        if types is not None:
            if not isinstance(types, list) or not all(isinstance(t, str) and t for t in types):
                return create_response(400, {
                    "error": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."
                })

        # Load artifacts from S3
        artifacts_map = list_all_artifacts_from_s3()

        # Execute search
        try:
            results = _search_artifacts_with_regex_and_version(
                artifacts_map.values(),
                name_regex=name_regex,
                version_expr=version_expr,
                types=types,
                id_regex=id_regex,
            )
        except ValueError as e:
            # invalid regex -> 400
            return create_response(400, {"error": str(e)})

        if not results:
            return create_response(404, {"error": "No matching artifacts found."})

        logger.info(f"Found {len(results)} matching artifact(s) for regex '{name_regex}'")
        return create_response(200, results)

    except Exception as exc:  # pragma: no cover
        logger.error("Unexpected error in search_artifacts", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
