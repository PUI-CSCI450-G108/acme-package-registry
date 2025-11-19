"""
Lambda handler for GET /audit/package-confusion

Returns a list of suspicious "packages" (typically code artifacts) that might be
attempting package confusion/typosquatting. Heuristics include:
- Name similarity to popular packages but lower popularity.
- Anomalous download spikes inconsistent with search interest.

Expected artifact shape (best-effort, all optional):
{
  "metadata": {"id": "...", "name": "...", "type": "code", "version": "..."},
  "metrics": {
    "search_hits_30d": <int>,
    "downloads_30d": <int>,
    "downloads_timeseries_30d": [int, int, ...]  # daily counts, length ~30
  }
}
"""

import json
import logging
import math
import os
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from lambda_handlers.utils import create_response, list_all_artifacts_from_s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# -----------------------------
# Config via environment
# -----------------------------
AUDIT_SCORE_THRESHOLD = float(os.getenv("AUDIT_SCORE_THRESHOLD", "0.60"))
MAX_AUDIT_RESULTS = int(os.getenv("MAX_AUDIT_RESULTS", "200"))
# Comma-separated list of canonical/popular package names to compare against.
# Example: "requests,numpy,pandas,tensorflow,torch,flask,react,express"
TOP_PACKAGE_NAMES = [x.strip() for x in os.getenv("TOP_PACKAGE_NAMES", "").split(",") if x.strip()]

# If true, limit audit to artifacts where metadata.type == "code"
AUDIT_CODE_ONLY = os.getenv("AUDIT_CODE_ONLY", "true").lower() in ("1", "true", "yes")


# -----------------------------
# Utilities
# -----------------------------

def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance (O(len(a)*len(b)))."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


def _normalized_similarity(a: str, b: str) -> float:
    """Return similarity in [0,1], 1 means identical; based on normalized Levenshtein."""
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein(a, b)
    denom = max(len(a), len(b))
    return max(0.0, 1.0 - dist / denom)


def _spike_factor(ts: List[int]) -> float:
    """
    Compute spike factor = max(ts) / (median(ts)+1).
    Higher means a sharper spike relative to baseline (bot-like bursts).
    """
    if not ts:
        return 0.0
    try:
        m = median(ts)
    except Exception:
        m = 0
    denom = (m if m is not None else 0) + 1
    return (max(ts) if ts else 0) / denom


def _suspicion_score(
    name: str,
    search_hits_30d: Optional[int],
    downloads_30d: Optional[int],
    spike: float,
    best_name_sim: float,
) -> Tuple[float, List[str]]:
    """
    Combine signals into a score in [0,1] and reasons list.
    Heuristics (tunable):
    - High name similarity to top packages but low search interest → suspicious.
    - High spike factor with low search interest → suspicious.
    - Low downloads with high similarity still suspicious (typosquat), but
      also allow "inflated" downloads (spike) to add suspicion.
    """

    reasons = []
    # Normalize features
    hits = max(0, int(search_hits_30d or 0))
    dls = max(0, int(downloads_30d or 0))
    # Map counts to [0,1] using log scaling
    def log_norm(x: int) -> float:
        return min(1.0, math.log1p(x) / 10.0)  # log base ~e, 10 is arbitrary cap

    hits_norm = log_norm(hits)          # popularity proxy
    dls_norm = log_norm(dls)            # volume proxy
    spike_norm = min(1.0, spike / 10.0) # spike of 10x median → 1.0 (cap)
    sim = best_name_sim                 # already [0,1]

    # Signals
    looks_like_real = sim >= 0.82
    low_search = hits_norm < 0.15
    low_dl = dls_norm < 0.15
    big_spike = spike_norm > 0.3  # roughly >3x median

    # Score components (weights can be tuned)
    score = 0.0
    if looks_like_real and (low_search or low_dl):
        score += 0.55
        reasons.append("High name similarity to popular package but low popularity")
    if big_spike and low_search:
        score += 0.35
        reasons.append("Anomalous download spike with low search interest")
    if looks_like_real and big_spike:
        score += 0.20
        reasons.append("Name similarity combined with spike")

    # Clip
    score = max(0.0, min(1.0, score))
    if score == 0.0 and looks_like_real and (low_search or big_spike):
        # ensure borderline cases surface a bit
        score = 0.35

    # Add detail for transparency
    reasons.append(f"similarity={sim:.2f}, hits_norm={hits_norm:.2f}, dls_norm={dls_norm:.2f}, spike={spike:.2f}")
    return score, reasons


def _best_similarity_to_top(name: str) -> float:
    if not TOP_PACKAGE_NAMES:
        return 0.0
    return max((_normalized_similarity(name, base) for base in TOP_PACKAGE_NAMES), default=0.0)


# -----------------------------
# Lambda Handler
# -----------------------------

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /audit/package-confusion

    Optional query params:
      - limit: int max results (<= MAX_AUDIT_RESULTS)
      - threshold: float override for AUDIT_SCORE_THRESHOLD
      - types: comma-separated types to include (default: "code" if AUDIT_CODE_ONLY=true)

    Returns: 200 with list of suspicious packages sorted by score desc.
    """
    try:
        logger.info(f"PackageConfusionAudit invoked: {json.dumps(event)}")

        # CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return create_response(200, {})

        # Parse query params
        qs_raw = event.get("queryStringParameters")
        qs: Dict[str, str] = qs_raw if isinstance(qs_raw, dict) else {}

        limit_param = qs.get("limit")
        if isinstance(limit_param, str) and limit_param.strip():
            try:
                limit = int(limit_param)
            except ValueError:
                limit = MAX_AUDIT_RESULTS
        else:
            limit = MAX_AUDIT_RESULTS

        threshold_param = qs.get("threshold")
        if isinstance(threshold_param, str) and threshold_param.strip():
            try:
                threshold = float(threshold_param)
            except ValueError:
                threshold = AUDIT_SCORE_THRESHOLD
        else:
            threshold = AUDIT_SCORE_THRESHOLD
        
        # Types filter
        types_param = qs.get("types")
        if types_param:
            allowed_types = {t.strip() for t in types_param.split(",") if t.strip()}
        else:
            allowed_types = {"code"} if AUDIT_CODE_ONLY else None

        artifacts_map = list_all_artifacts_from_s3()
        suspicious: List[Dict[str, Any]] = []

        for art in artifacts_map.values():
            md = art.get("metadata") or {}
            aid = md.get("id")
            name = (md.get("name") or "").strip()
            atype = md.get("type")

            if not aid or not name:
                continue
            if allowed_types is not None and atype not in allowed_types:
                continue

            metrics = art.get("metrics") or {}
            search_hits = metrics.get("search_hits_30d")
            downloads = metrics.get("downloads_30d")
            ts = metrics.get("downloads_timeseries_30d") or []
            if not isinstance(ts, list):
                ts = []

            sim = _best_similarity_to_top(name)
            spike = _spike_factor([int(x) for x in ts if isinstance(x, (int, float))])

            score, reasons = _suspicion_score(
                name=name,
                search_hits_30d=search_hits,
                downloads_30d=downloads,
                spike=spike,
                best_name_sim=sim,
            )

            if score >= threshold:
                suspicious.append({
                    "id": aid,
                    "name": name,
                    "type": atype,
                    "version": md.get("version"),
                    "score": round(score, 3),
                    "reasons": reasons,
                    "metrics": {
                        "search_hits_30d": search_hits,
                        "downloads_30d": downloads,
                        "spike_factor": round(spike, 3),
                        "similarity_to_top": round(sim, 3),
                    },
                })

        suspicious.sort(key=lambda x: x["score"], reverse=True)
        if limit and limit > 0:
            suspicious = suspicious[: min(limit, MAX_AUDIT_RESULTS)]

        return create_response(200, suspicious)

    except Exception as exc:  # pragma: no cover
        logger.error("Unexpected error in PackageConfusionAudit", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(exc)}"})
