"""
Tree Score metric.

Measures supply chain health by averaging the net_scores of all parent models
in the lineage graph.

This metric only considers parent models that are already registered in the
artifact store (S3 bucket). Models not in the registry are ignored.

Scoring:
- 1.0: No dependencies (trained from scratch) OR all parents have high scores
- 0.5: Parents declared but none found in registry (unknown quality)
- 0.25: Parents declared but none in registry (incentivize publishing deps)
- Average of parent scores: If parents found in registry
"""

import logging
from typing import Any, List, Optional, Set

from src.artifact_store import ArtifactStore
from src.artifact_utils import generate_artifact_id

logger = logging.getLogger(__name__)

# Module-level cache, cleared per evaluation
_parent_cache = {}


def _extract_base_models(model_info: Any) -> List[str]:
    """
    Extract base model ID(s) from model cardData.

    The base_model field can be:
    - None: Model trained from scratch
    - String: Single base model
    - List: Multiple base models (for merged models)

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        List of base model IDs (empty if none)
    """
    try:
        card_data = getattr(model_info, "cardData", None) or {}
        base_model = card_data.get("base_model")

        if base_model is None:
            return []
        elif isinstance(base_model, list):
            return [str(bm) for bm in base_model if bm]
        elif isinstance(base_model, str) and base_model.strip():
            return [base_model.strip()]
        else:
            return []
    except Exception as e:
        logger.debug(f"Error extracting base models: {e}")
        return []


def _get_parent_score(
    parent_url: str,
    artifact_store: ArtifactStore,
    depth: int,
    max_depth: int,
    visited: Set[str],
) -> Optional[float]:
    """
    Recursively get the net_score for a parent model and its ancestors.

    Args:
        parent_url: URL or ID of the parent model
        artifact_store: Artifact storage backend
        depth: Current recursion depth
        max_depth: Maximum recursion depth
        visited: Set of already-visited model IDs (cycle detection)

    Returns:
        Net score of parent (averaged with its ancestors), or None if not found
    """
    global _parent_cache

    # Check cache first
    if parent_url in _parent_cache:
        logger.debug(f"Cache hit for parent: {parent_url}")
        return _parent_cache[parent_url]

    # Check depth limit
    if depth >= max_depth:
        logger.debug(f"Max depth {max_depth} reached for parent: {parent_url}")
        return None

    # Check for cycles
    if parent_url in visited:
        logger.warning(
            f"Circular dependency detected: {parent_url} already in lineage"
        )
        return None

    visited.add(parent_url)

    try:
        # Generate artifact ID for parent
        # Assume parent is a model (most common case)
        artifact_id = generate_artifact_id("model", parent_url)

        # Query artifact store
        artifact_data = artifact_store.get_artifact(artifact_id)

        if not artifact_data:
            logger.debug(f"Parent {parent_url} not found in registry")
            return None

        # Extract net_score from parent artifact
        parent_net_score = artifact_data.get("net_score")

        if parent_net_score is None:
            logger.warning(
                f"Parent {parent_url} found but missing net_score field"
            )
            return None

        # Try to get parent's base models (recursive)
        parent_base_models = artifact_data.get("base_model", [])
        if isinstance(parent_base_models, str):
            parent_base_models = [parent_base_models]
        elif not isinstance(parent_base_models, list):
            parent_base_models = []

        # Recursively get scores for parent's ancestors
        ancestor_scores = []
        for ancestor_url in parent_base_models:
            ancestor_score = _get_parent_score(
                ancestor_url, artifact_store, depth + 1, max_depth, visited.copy()
            )
            if ancestor_score is not None:
                ancestor_scores.append(ancestor_score)

        # Average parent's score with its ancestors' scores
        if ancestor_scores:
            # Include parent's own score in the average
            all_scores = [parent_net_score] + ancestor_scores
            avg_score = sum(all_scores) / len(all_scores)
        else:
            # No ancestors found, just use parent's score
            avg_score = parent_net_score

        # Cache result
        _parent_cache[parent_url] = avg_score

        logger.debug(
            f"Parent {parent_url}: score={parent_net_score:.4f}, "
            f"ancestors={len(ancestor_scores)}, avg={avg_score:.4f}"
        )

        return avg_score

    except Exception as e:
        logger.error(f"Error getting score for parent {parent_url}: {e}")
        return None


def compute_tree_score_metric(
    model_info: Any, artifact_store: Optional[ArtifactStore] = None
) -> float:
    """
    Compute tree score based on parent model quality.

    This metric averages the net_scores of all parent models (and their ancestors)
    that are found in the artifact registry. Only models already registered are
    considered.

    Scoring logic:
    - No base_model declared: 1.0 (trained from scratch = perfect supply chain)
    - base_model(s) declared but none in registry: 0.25 (unknown quality)
    - base_model(s) found in registry: average of their net_scores
    - artifact_store unavailable (CLI context): 0.5 (default)

    Args:
        model_info: HuggingFace ModelInfo object
        artifact_store: Artifact storage backend (None in CLI context)

    Returns:
        Tree score between 0.0 and 1.0
    """
    global _parent_cache
    _parent_cache.clear()  # Fresh cache per evaluation

    try:
        # Check if artifact store is available
        if artifact_store is None:
            logger.warning(
                "No artifact store available - tree_score unavailable (CLI context)"
            )
            return 0.5

        # Extract base models
        base_models = _extract_base_models(model_info)

        if not base_models:
            # No dependencies = perfect supply chain
            logger.debug("No base models - returning 1.0")
            return 1.0

        logger.debug(f"Found {len(base_models)} base model(s): {base_models}")

        # Get scores for all parent models
        parent_scores = []
        for parent_url in base_models:
            score = _get_parent_score(
                parent_url,
                artifact_store,
                depth=0,
                max_depth=3,
                visited=set(),
            )
            if score is not None:
                parent_scores.append(score)

        if not parent_scores:
            # base_model declared but none found in registry
            logger.warning(
                f"Base models {base_models} declared but none found in registry"
            )
            return 0.25

        # Average scores of all parents found
        final_score = sum(parent_scores) / len(parent_scores)

        # Ensure score is within bounds
        final_score = max(0.0, min(1.0, final_score))

        logger.debug(
            f"Tree score computed: {len(parent_scores)} parents found, "
            f"avg score: {final_score:.4f}"
        )

        return round(final_score, 4)

    except Exception as e:
        logger.error(f"Error computing tree_score metric: {e}")
        return 0.5


# Clear cache function for testing
def clear_cache():
    """Clear the parent score cache. Useful for testing."""
    global _parent_cache
    _parent_cache.clear()
