import datetime
from typing import Any, Dict, List, Optional
import os
from pathlib import Path

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from huggingface_hub import HfApi


def _clone_or_open_repo(model_id: str, token: Optional[str] = None) -> Optional[Repo]:
    """Clone or open the Hugging Face repo for the given model id.

    Uses a simple on-disk cache at .hf_git_cache/<org>__<name>.
    Returns None on failure (e.g., gated/private or network issues).
    """
    try:
        cache_dir = Path(".hf_git_cache") / model_id.replace("/", "__")
        cache_dir.mkdir(parents=True, exist_ok=True)

        # If repo already exists, open and fetch latest
        if (cache_dir / ".git").exists():
            repo = Repo(cache_dir)
            try:
                repo.remote().fetch(prune=True)
            except Exception:
                pass
            return repo

        # Public clone URL. For private/gated repos, this may fail without credentials
        base_url = f"https://huggingface.co/{model_id}"
        try:
            return Repo.clone_from(base_url, cache_dir)
        except GitCommandError:
            # Retry with token if provided (embed token in URL as password)
            if token:
                # Using placeholder username 'oauth2' is common convention
                authed = f"https://oauth2:{token}@huggingface.co/{model_id}"
                # Clone only the last year of commits
                year_ago = datetime.now() - datetime.timedelta(days=365)
                year_ago_str = year_ago.strftime("%Y-%m-%d")
                try:
                    return Repo.clone_from(authed, cache_dir, multi_options=[f"--shallow-since={year_ago_str}"])
                except GitCommandError:
                    return None
            return None
    except (InvalidGitRepositoryError, NoSuchPathError, OSError):
        return None


def _detect_default_ref(repo: Repo) -> str:
    """Best-effort to find a reasonable default ref to iterate commits."""
    for ref_name in ("main", "master"):
        try:
            repo.commit(ref_name)
            return ref_name
        except Exception:
            continue
    # Fall back to HEAD
    return "HEAD"


def _count_commits_by_author(repo: Repo, ref: Optional[str] = None, max_count: int = 2000) -> Dict[str, int]:
    """Return a mapping of author identifier -> commit count.

    Identifies authors by lower-cased email when available, else by name.
    Limits to last max_count commits for performance.
    """
    if ref is None:
        ref = _detect_default_ref(repo)

    counts: Dict[str, int] = {}
    try:
        for c in repo.iter_commits(ref, max_count=max_count):
            author_str = (c.author.email or c.author.name or "unknown").lower()
            counts[author_str] = counts.get(author_str, 0) + 1
    except Exception:
        # If commit iteration fails for any reason, return what we have (possibly empty)
        return counts
    return counts


def _count_commits_by_author_api(repo_id: str, repo_type: str = "model", limit: int = 1000) -> Dict[str, int]:
    """Fetch commit list via Hugging Face API and aggregate counts per author.

    This is much faster than cloning. Requires HF_TOKEN for gated/private repos.
    """
    print("[bus_factor] list_repo_commits: repo_id=", repo_id, "repo_type=", repo_type)
    print("[bus_factor] os.getenv(GIT_LFS_SKIP_SMUDGE)=", os.getenv("GIT_LFS_SKIP_SMUDGE"))
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    print("[bus_factor] token=", token)
    api = HfApi(token=token)
    try:
        commits = api.list_repo_commits(repo_id=repo_id, repo_type=repo_type)
    except Exception as e:
        print("[bus_factor] list_repo_commits failed:", str(e))
        return {}

    counts: Dict[str, int] = {}
    for entry in commits or []:
        # Handle both object-style and dict-style responses
        author_obj = getattr(entry, "author", None)
        email = getattr(author_obj, "email", None)
        name = getattr(author_obj, "name", None)
        if email is None and name is None and isinstance(entry, dict):
            author_dict = entry.get("author") or {}
            email = author_dict.get("email")
            name = author_dict.get("name")
        author_key = (email or name or "unknown").lower()
        counts[author_key] = counts.get(author_key, 0) + 1

    print("[bus_factor] API authors=", len(counts), "total_commits=", sum(counts.values()))
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
            return 1.0

        # Fast path: try HF API first
        counts_by_author = _count_commits_by_author_api(model_id, repo_type="model")

        if not counts_by_author:
            return 1.0

        gini = _gini_from_counts(list(counts_by_author.values()))
        score = 1.0 - gini
        if score < 0.0:
            score = 0.0
        if score > 1.0:
            score = 1.0
        return round(score, 4)
    except Exception:
        # Safe fallback: avoid breaking overall scoring due to failures here
        return 1.0

if __name__ == "__main__":
    print(compute_bus_factor_metric(model_info={"id": "google/gemma-3-270m"}))

# run test with python -m src.metrics.bus_factor