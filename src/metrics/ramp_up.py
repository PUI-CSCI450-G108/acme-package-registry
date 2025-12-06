import logging
from typing import Any

from huggingface_hub import HfFileSystem, hf_hub_download


def _fetch_readme_content(model_info: Any) -> str:
    """Fetches the README content for a given model."""
    try:
        # Check if README.md exists
        fs = HfFileSystem()
        paths = fs.ls(model_info.id, detail=False)
        if not any(p.endswith("README.md") for p in paths):
            logging.warning(f"No README.md file found for model {model_info.id}")
            return ""

        readme_file = hf_hub_download(
            repo_id=model_info.id, filename="README.md", repo_type="model"
        )
        with open(readme_file, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"Could not download or read README for {model_info.id}: {e}")
        return ""


def _compute_heuristic_ramp_up_score(readme: str, model_info: Any) -> float:
    """
    Heuristic scoring of README documentation quality for developer onboarding.
    Uses weighted continuous scoring for different documentation elements.

    Scoring Components (additive, max 1.0):
    - Installation instructions: +0.3
    - Usage/quickstart section: +0.3
    - Code blocks/examples: +0.25
    - Well-structured organization: +0.15
    - Example files bonus: +0.1 (capped at 1.0)

    Returns:
        Float score in range [0.0, 1.0]
    """
    if not readme or len(readme.strip()) < 50:
        return 0.0

    readme_lower = readme.lower()
    score = 0.0

    # +0.3 for installation instructions
    has_installation = any(
        keyword in readme_lower
        for keyword in ["install", "pip install", "setup", "requirements"]
    )
    if has_installation:
        score += 0.3

    # +0.3 for usage/quickstart section
    has_usage = any(
        keyword in readme_lower
        for keyword in ["quick start", "quickstart", "getting started", "get started",
                        "usage", "how to use", "example", "basic usage"]
    )
    if has_usage:
        score += 0.3

    # +0.25 for code blocks (practical examples)
    has_code_blocks = (
        "```" in readme or  # Markdown code blocks
        readme.count("    ") >= 3 or  # Indented code (at least 3 occurrences)
        "`import " in readme  # Inline code with imports
    )
    if has_code_blocks:
        score += 0.25

    # +0.15 for well-structured organization (multiple headers)
    header_count = readme.count("##")
    if header_count >= 3:
        score += 0.15
    elif header_count >= 1:
        score += 0.075  # Partial credit for some structure

    # Bonus: +0.1 if example files (.py/.ipynb) present
    try:
        siblings = getattr(model_info, "siblings", []) or []
        has_example_files = any(
            getattr(s, "rfilename", "").endswith((".py", ".ipynb"))
            for s in siblings
        )
        if has_example_files:
            score += 0.1
    except Exception:
        pass

    # Cap at 1.0
    return round(min(score, 1.0), 4)


def compute_ramp_up_metric(model_info: Any) -> float:
    """
    Computes the ramp-up time score based on README documentation quality.

    Uses LLM-based assessment when available to evaluate how well the README
    supports developer onboarding (installation, usage, examples, clarity).
    Falls back to weighted heuristic scoring when LLM is unavailable.

    Returns:
        Float in range [0.0, 1.0] representing documentation quality for ramp-up
    """
    readme_content = _fetch_readme_content(model_info)
    if not readme_content:
        return 0.0

    # Try LLM-based assessment first if available
    try:
        from src.LLM_endpoint import score_with_llm, is_llm_available  # type: ignore
        if is_llm_available():
            context = {
                "model_id": getattr(model_info, "id", ""),
                "tags": getattr(model_info, "tags", []),
                "has_examples": any(
                    getattr(s, "rfilename", "").endswith((".py", ".ipynb"))
                    for s in (getattr(model_info, "siblings", []) or [])
                )
            }
            llm_score = score_with_llm("ramp_up", readme_content, context)
            if llm_score is not None:
                return round(float(llm_score), 4)
    except Exception as e:
        logging.debug(f"ramp_up: LLM scoring unavailable: {e}")

    # Fallback to heuristic
    return _compute_heuristic_ramp_up_score(readme_content, model_info)
