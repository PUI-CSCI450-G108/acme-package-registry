"""Lambda handler for GET /artifact/model/{id}/lineage."""

import json
from time import perf_counter
from typing import Any, Dict, List, Set

from lambda_handlers.utils import (
    create_response,
    get_header,
    list_all_artifacts_from_s3,
    log_event,
)
from src.auth import AuthError, InvalidTokenError, get_default_auth_service


def _extract_base_models(artifact_data: Dict[str, Any]) -> List[str]:
    """
    Extract base model information from artifact data.

    The base_model can be stored in different locations:
    - In rating metadata (from HuggingFace cardData)
    - As a top-level field in artifact_data

    Args:
        artifact_data: The artifact data from S3

    Returns:
        List of base model URLs/IDs (empty if none)
    """
    # Check if base_model is stored at top level
    base_model = artifact_data.get("base_model")

    # If not, try to get it from rating/metadata
    if base_model is None:
        rating = artifact_data.get("rating", {})
        if isinstance(rating, str):
            try:
                rating = json.loads(rating)
            except (json.JSONDecodeError, TypeError):
                rating = {}
        base_model = rating.get("base_model")

    # Normalize to list
    if base_model is None:
        return []
    elif isinstance(base_model, list):
        return [str(bm) for bm in base_model if bm]
    elif isinstance(base_model, str) and base_model.strip():
        return [base_model.strip()]
    else:
        return []


def _build_lineage_graph(
    artifact_id: str,
    all_artifacts: Dict[str, Any],
    max_depth: int = 5
) -> Dict[str, Any]:
    """
    Build a lineage graph for an artifact by traversing its dependencies.

    Args:
        artifact_id: The artifact ID to build lineage for
        all_artifacts: Dictionary of all artifacts from S3
        max_depth: Maximum depth to traverse (prevents infinite recursion)

    Returns:
        Dictionary with 'nodes' and 'edges' lists
    """
    nodes = []
    edges = []
    visited: Set[str] = set()

    def _traverse(current_id: str, depth: int):
        """Recursively traverse the lineage graph."""
        if depth >= max_depth or current_id in visited:
            return

        visited.add(current_id)
        artifact_data = all_artifacts.get(current_id)

        if not artifact_data:
            # External dependency not in registry
            # Still add as a node but mark as external
            nodes.append({
                "artifact_id": current_id,
                "name": current_id,
                "source": "external"
            })
            return

        # Add node for current artifact
        metadata = artifact_data.get("metadata", {})
        artifact_name = metadata.get("name", current_id)

        nodes.append({
            "artifact_id": current_id,
            "name": artifact_name,
            "source": "artifact_store"
        })

        # Extract base models
        base_models = _extract_base_models(artifact_data)

        # Traverse each base model
        for base_model_url in base_models:
            # Try to resolve the base_model URL to an artifact_id
            # The base_model might be a HuggingFace URL or repo ID
            parent_id = _resolve_base_model_to_id(base_model_url, all_artifacts)

            if parent_id:
                # Add edge from parent to current
                edges.append({
                    "from_node_artifact_id": parent_id,
                    "to_node_artifact_id": current_id,
                    "relationship": "base_model"
                })

                # Recursively process parent
                _traverse(parent_id, depth + 1)
            else:
                # Parent not in registry - add as external node
                nodes.append({
                    "artifact_id": base_model_url,
                    "name": base_model_url,
                    "source": "external"
                })

                edges.append({
                    "from_node_artifact_id": base_model_url,
                    "to_node_artifact_id": current_id,
                    "relationship": "base_model"
                })

    # Start traversal from the requested artifact
    _traverse(artifact_id, 0)

    # Deduplicate nodes (might have been added as external then found in registry)
    seen_ids = set()
    unique_nodes = []
    for node in nodes:
        node_id = node["artifact_id"]
        if node_id not in seen_ids:
            seen_ids.add(node_id)
            unique_nodes.append(node)

    return {
        "nodes": unique_nodes,
        "edges": edges
    }


def _resolve_base_model_to_id(base_model: str, all_artifacts: Dict[str, Any]) -> str:
    """
    Try to resolve a base_model reference to an artifact_id.

    This checks if any artifact in the registry has a URL matching the base_model.

    Args:
        base_model: The base model URL or ID
        all_artifacts: Dictionary of all artifacts

    Returns:
        Artifact ID if found, None otherwise
    """
    # Direct match - artifact_id equals base_model
    if base_model in all_artifacts:
        return base_model

    # Search for artifact with matching URL
    for artifact_id, artifact_data in all_artifacts.items():
        url = artifact_data.get("url", "")
        metadata = artifact_data.get("metadata", {})
        name = metadata.get("name", "")

        # Check if URL contains the base_model reference
        # HuggingFace URLs: https://huggingface.co/bert-base-uncased
        # base_model might be just "bert-base-uncased" or full URL
        if base_model in url or url.endswith(f"/{base_model}"):
            return artifact_id

        # Check if name matches
        if name == base_model:
            return artifact_id

    return None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Retrieve the lineage graph for an artifact.

    Returns a graph with nodes and edges showing the dependency tree.

    API Gateway Event Structure:
    - event['pathParameters']['id'] - artifact ID
    - event['headers']['X-Authorization'] - Auth token (required)
    """
    start_time = perf_counter()
    artifact_id = None

    try:
        log_event(
            "info",
            f"artifact_lineage invoked: {json.dumps(event)}",
            event=event,
            context=context,
        )

        if event.get("httpMethod") == "OPTIONS":
            latency = perf_counter() - start_time
            log_event(
                "info",
                "Handled OPTIONS preflight for artifact_lineage",
                event=event,
                context=context,
                latency=latency,
                status=200,
            )
            return create_response(200, {})

        # Authenticate
        token = get_header(event, "X-Authorization")
        if not token:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing authentication token in artifact_lineage",
                event=event,
                context=context,
                latency=latency,
                status=403,
                error_code="missing_auth_token",
            )
            return create_response(
                403,
                {"error": "Authentication failed due to invalid or missing AuthenticationToken."}
            )

        try:
            auth_service = get_default_auth_service()
            username = auth_service.verify_token(token)
            log_event(
                "debug",
                f"User {username} authenticated for artifact_lineage",
                event=event,
                context=context,
            )
        except (AuthError, InvalidTokenError) as e:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Authentication failed in artifact_lineage: {e}",
                event=event,
                context=context,
                latency=latency,
                status=403,
                error_code="auth_failed",
            )
            return create_response(
                403,
                {"error": "Authentication failed due to invalid or missing AuthenticationToken."}
            )

        # Extract path parameters
        path_params = event.get("pathParameters", {})
        artifact_id = path_params.get("id")

        if not artifact_id:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                "Missing artifact_id in artifact_lineage",
                event=event,
                context=context,
                latency=latency,
                status=400,
                error_code="missing_artifact_id",
            )
            return create_response(
                400,
                {
                    "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
                }
            )

        # Get all artifacts
        all_artifacts = list_all_artifacts_from_s3()

        # Check if artifact exists
        artifact_data = all_artifacts.get(artifact_id)
        if not artifact_data:
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Artifact not found when fetching lineage for id: {artifact_id}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=404,
                error_code="artifact_not_found",
            )
            return create_response(404, {"error": "Artifact does not exist."})

        # Verify it's a model (lineage endpoint is only for models per the spec)
        stored_type = artifact_data.get("metadata", {}).get("type") or artifact_data.get("type")
        if stored_type != "model":
            latency = perf_counter() - start_time
            log_event(
                "warning",
                f"Lineage requested for non-model artifact: {artifact_id}, type={stored_type}",
                event=event,
                context=context,
                model_id=artifact_id,
                latency=latency,
                status=400,
                error_code="invalid_artifact_type",
            )
            return create_response(
                400,
                {"error": "The lineage graph cannot be computed because the artifact metadata is missing or malformed."}
            )

        # Build lineage graph
        lineage_graph = _build_lineage_graph(artifact_id, all_artifacts)

        latency = perf_counter() - start_time
        log_event(
            "info",
            f"Returned lineage graph for artifact {artifact_id}: {len(lineage_graph['nodes'])} nodes, {len(lineage_graph['edges'])} edges",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=200,
        )
        return create_response(200, lineage_graph)

    except Exception as exc:  # pragma: no cover - defensive logging
        latency = perf_counter() - start_time
        log_event(
            "error",
            f"Unexpected error in artifact_lineage: {exc}",
            event=event,
            context=context,
            model_id=artifact_id,
            latency=latency,
            status=500,
            error_code="unexpected_error",
            exc_info=True,
        )
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
