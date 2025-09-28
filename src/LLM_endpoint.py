"""
Lightweight client for Purdue GenAI Studio (or compatible chat API).

This module is optional: if no API key is present or requests is not installed,
callers can detect unavailability and fall back to heuristics.
"""

from __future__ import annotations

import json
import os
import typing as t


GENAI_API_URL = os.environ.get("GENAI_API_URL", "https://genai.rcac.purdue.edu/api/chat/completions")


def _get_api_key() -> t.Optional[str]:
    # Support a couple of common env var names
    return os.environ.get("GEN_AI_STUDIO_API_KEY") or os.environ.get("GENAI_STUDIO_API_KEY")


def is_llm_available() -> bool:
    # Check API key and requests presence
    if not _get_api_key():
        return False
    try:
        import requests  # noqa: F401
    except Exception:
        return False
    return True


def _post_chat(payload: dict) -> dict:
    import requests  # Local import to avoid hard dependency when unused

    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }
    resp = requests.post(GENAI_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def _build_prompt(task: str, readme: str, context: dict) -> t.List[dict]:
    if task == "code_quality":
        system = (
            "You are a strict code quality reviewer. Score the repository's code quality "
            "based on README and file listing. Output ONLY a compact JSON object with keys: "
            "score (one of 0, 0.5, 1) and reason (short). Criteria: 1 if readable, basic style followed, documented; "
            "0.5 if some readability or documentation issues; 0 if messy or undocumented."
        )
    elif task == "perf_claims":
        system = (
            "You are a model evaluation auditor. Assess performance claims from README and metadata. "
            "Output ONLY a JSON with keys: score (0, 0.5, 1) and reason. Criteria: 1 if benchmarks/evaluation results "
            "are present and clear (tables/metrics); 0.5 if vague or partial claims; 0 if none."
        )
    else:
        system = (
            "You are an assistant that returns a JSON with 'score' (0, 0.5, 1) and 'reason' based on the user instructions."
        )

    user = {
        "task": task,
        "readme": readme or "",
        "context": context or {},
        "instructions": "Return only a JSON object like {\"score\": 1, \"reason\": \"...\"}. No extra text.",
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user)},
    ]


def _parse_choice_content(resp: dict) -> str:
    # Try common shapes
    try:
        return resp["choices"][0]["message"]["content"]
    except Exception:
        pass
    try:
        # Some providers stream or return alternative shapes
        return resp.get("content", "")
    except Exception:
        return ""


def score_with_llm(task: str, readme: str, context: dict, model: str | None = None) -> t.Optional[float]:
    """Call the chat API to get a score in {0, 0.5, 1}. Returns None on failure."""
    if not is_llm_available():
        return None

    payload = {
        "model": model or os.environ.get("GENAI_MODEL", os.environ.get("GEN_AI_MODEL", "llama3.1:latest")),
        "messages": _build_prompt(task, readme, context),
        "stream": False,
    }
    try:
        resp = _post_chat(payload)
        content = _parse_choice_content(resp)
        # Extract JSON-like content
        data = None
        try:
            data = json.loads(content)
        except Exception:
            # Attempt to find JSON substring
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(content[start : end + 1])
        if not isinstance(data, dict):
            return None
        score = data.get("score")
        if score in (0, 0.0, 0.5, 1, 1.0):
            return float(score)
        # Try to coerce numeric
        try:
            val = float(score)
            if val in (0.0, 0.5, 1.0):
                return val
        except Exception:
            return None
    except Exception:
        return None

    return None
