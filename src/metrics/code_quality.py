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

    # Documentation signals
    doc_keywords = [
        "usage", "installation", "how to use", "getting started", "example", "documentation",
    ]
    documented = any(k in readme_lower for k in doc_keywords)

    # Code/file signals
    siblings = list(_safe_getattr(model_info, "siblings", []) or [])
    filenames = []
    try:
        filenames = [s.rfilename for s in siblings if hasattr(s, "rfilename")]
    except Exception:
        filenames = []

    has_code_files = any(f.endswith((".py", ".ipynb")) for f in filenames)
    snake_case_present = any(f.endswith(".py") and ("_" in f) for f in filenames)

    # Style/config presence
    style_files = {"pyproject.toml", "setup.cfg", ".flake8", ".editorconfig", ".isort.cfg", "tox.ini"}
    has_style_config = any(f in style_files for f in filenames)

    # Scoring logic (heuristic fallback)
    # High score: well documented with code structure
    if documented and has_code_files:
        # Bonus for style config
        return 1.0 if has_style_config or snake_case_present else 0.9
    # Medium score: some documentation or code present
    if documented:
        return 0.75
    if has_code_files:
        return 0.6
    # Low score: minimal code/docs but has README content
    if readme:
        return 0.4
    return 0.0
