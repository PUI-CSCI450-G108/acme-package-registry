from typing import Any, Dict, List
import os
import traceback
import src.hf_api as hf_api



def _count_commits_by_author_api(repo_id: str, repo_type: str = "model", limit: int = 1000) -> Dict[str, int]:
    """Fetch commit list via Hugging Face API and aggregate counts per author.

    This is much faster than cloning. Requires HF_TOKEN for gated/private repos.
    """
    token = os.getenv("HF_TOKEN")
    api = hf_api.HuggingFaceAPI(token=token)
    try:
        commits = api.list_repo_commits(repo_id=repo_id, repo_type=repo_type)
    except Exception as e:
        print("[bus_factor] list_repo_commits failed:", str(e))
        return {}

    counts: Dict[str, int] = {}
    for entry in commits or []:
        # Prefer explicit list of author usernames if available (GitCommitInfo.authors)
        names: List[str] = []

        try:
            authors_attr = getattr(entry, "authors", None)
            if isinstance(authors_attr, (list, tuple)):
                names = [str(x) for x in authors_attr if x]
        except Exception:
            pass

        # Count each distinct name for this commit
        for n in {str(n).lower() for n in names if n}:
            counts[n] = counts.get(n, 0) + 1

    return counts


def _gini_from_counts(counts: List[int]) -> float:
    """Compute the Gini coefficient from a list of non-negative counts.

    Returns 0.0 for edge cases (<=1 contributor or zero total commits).
    """
    values = [c for c in counts if c > 0]
    n = len(values)
    if n <= 1:
        return 0.0
    total = sum(values)
    if total == 0:
        return 0.0
    values.sort()
    weighted_sum = sum((i + 1) * v for i, v in enumerate(values))
    return (2 * weighted_sum) / (n * total) - (n + 1) / n


def compute_bus_factor_metric(model_info: Any) -> float:
    """Compute a bus-factor-like score based on commit inequality among contributors.

    Score = 1 - Gini(commit_counts_by_author). Higher is better (more shared ownership).
    Returns 1.0 when repo is unavailable or has insufficient data.
    """
    try:
        model_id = getattr(model_info, "id", None) or (model_info.get("id") if isinstance(model_info, dict) else None)
        if not isinstance(model_id, str) or not model_id:
            return 0.0

        # Fast path: try HF API first
        counts_by_author = _count_commits_by_author_api(model_id, repo_type="model")

        if not counts_by_author:
            print("[bus_factor] no counts by author")
            return 0.0

        gini = _gini_from_counts(list(counts_by_author.values()))
        if gini < 0.0:
            gini = 0.0
        if gini > 1.0:
            gini = 1.0
        # Invert: low inequality (low Gini) → high score
        score = 1.0 - gini
        return round(score, 4)
    except Exception:
        print("[bus_factor] exception", traceback.format_exc())
        # Safe fallback: avoid breaking overall scoring due to failures here
        return 0.0

if __name__ == "__main__":
    print(compute_bus_factor_metric(model_info={"id": "google/gemma-3-270m"}))

# run test with python -m src.metrics.bus_factor