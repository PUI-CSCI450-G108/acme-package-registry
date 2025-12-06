from typing import Any
import logging


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _read_readme(model_info: Any) -> str:
    try:
        from src.metrics.dataset_code_avail import _fetch_readme_content  # type: ignore
        return _fetch_readme_content(model_info) or ""
    except Exception as e:
        logging.debug(f"code_quality: README fetch failed for {getattr(model_info, 'id', '?')}: {e}")
        return ""


def compute_code_quality_metric(model_info: Any) -> float:
    """
    Heuristic scoring of code quality and documentation:
    - 1.0 if readable, basic style followed, documented
    - 0.5 if some readability or documentation issues
    - 0.0 if messy or undocumented

    Signals considered:
    - README presence with usage/installation/examples sections
    - Presence of style/config files: pyproject.toml, setup.cfg, .flake8, .editorconfig, .isort.cfg
    - Presence of code files (.py/.ipynb), prefer snake_case names
    """
    readme = _read_readme(model_info)

    # Try LLM-based assessment first if available
    try:
        from src.LLM_endpoint import score_with_llm, is_llm_available  # type: ignore
        if is_llm_available():
            context = {
                "file_list": [getattr(s, "rfilename", "") for s in (getattr(model_info, "siblings", []) or [])],
                "card_data": getattr(model_info, "cardData", None) or {},
            }
            llm_score = score_with_llm("code_quality", readme, context)
            if llm_score is not None:
                return float(llm_score)
    except Exception as e:
        logging.debug(f"code_quality: LLM scoring unavailable: {e}")
    readme_lower = readme.lower()
    readme_length = len(readme.strip())

    # Code/file signals - check these first
    siblings = list(_safe_getattr(model_info, "siblings", []) or [])
    filenames = []
    try:
        filenames = [s.rfilename for s in siblings if hasattr(s, "rfilename")]
    except Exception:
        filenames = []

    has_code_files = any(f.endswith((".py", ".ipynb")) for f in filenames)

    # Style/config presence
    style_files = {"pyproject.toml", "setup.cfg", ".flake8", ".editorconfig", ".isort.cfg", "tox.ini", "requirements.txt", "setup.py"}
    has_style_config = any(f in style_files for f in filenames)

    # If README is very short, check if there's code structure at least
    if readme_length < 100:
        if has_code_files or has_style_config:
            return 0.5  # Has code but minimal docs
        else:
            return 0.0  # Nothing substantial

    # Strong documentation signals (more than just basic keywords)
    strong_doc_keywords = [
        "usage", "installation", "how to use", "getting started", "quickstart",
        "## usage", "## installation", "## example", "## quick start"
    ]
    has_strong_docs = any(k in readme_lower for k in strong_doc_keywords)

    # Check for actual code examples in README
    has_code_examples = "```" in readme and ("import" in readme_lower or "from" in readme_lower)

    # More discriminating scoring logic
    if has_strong_docs and has_code_examples:
        return 1.0  # Well documented with examples
    elif has_strong_docs or has_code_examples:
        return 0.5  # Some documentation
    elif has_code_files or has_style_config or readme_length > 500:
        return 0.5  # Has some structure
    else:
        return 0.0  # Minimal quality
