from typing import Any, Optional
import logging
import re


def _read_readme(model_info: Any) -> str:
    try:
        from src.metrics.dataset_code_avail import _fetch_readme_content  # type: ignore
        return _fetch_readme_content(model_info) or ""
    except Exception as e:
        logging.debug(f"perf_claims: README fetch failed for {getattr(model_info, 'id', '?')}: {e}")
        return ""


def _tier1_heuristic(readme: str, model_info: Any) -> Optional[float]:
    """
    Tier 1: Quick heuristic check for clear performance claims.
    Returns:
        1.0 if clear benchmarks/metrics are present
        0.0 if definitely no performance info
        None if inconclusive (needs LLM analysis)
    """
    text = readme.lower()

    # Strong signals: tables with metric names and numeric values
    strong_keywords = [
        "accuracy", "f1", "f1-score", "precision", "recall", "bleu", "rouge", "cer", "wer",
        "latency", "throughput", "ms", "fps", "samples/s", "glue", "squad", "mmlu", "hellaswag",
        "loss", "perplexity", "score", "metric", "eval",
    ]
    has_table = "|" in text and "---" in text  # markdown table heuristic
    numbers = re.findall(r"\b\d{1,3}(?:\.\d+)?%?\b", text)

    # More lenient: if there's a table OR strong keywords with numbers
    strong_hit = (has_table and len(numbers) >= 1) or (any(k in text for k in strong_keywords) and len(numbers) >= 2)

    # cardData may contain evaluation results too
    try:
        card = getattr(model_info, "cardData", None)
        if isinstance(card, dict):
            if any(key in card for key in ("metrics", "evaluation", "results", "model-index")):
                strong_hit = True
    except Exception:
        pass

    if strong_hit:
        return 1.0

    # Check if there's any mention of performance-related terms
    medium_keywords = ["benchmark", "evaluation", "results", "sota", "state-of-the-art", "compare", "comparison", "performance", "tested"]
    has_any_perf_mention = any(k in text for k in medium_keywords) or any(k in text for k in strong_keywords)

    # More lenient: if README is very short and has no mentions, score 0
    if not has_any_perf_mention and len(readme.strip()) > 200:
        return 0.0

    # Inconclusive - has some mentions but not clear enough
    return None


def _tier2_llm_analysis(readme: str, model_info: Any) -> float:
    """
    Tier 2: Use LLM for nuanced analysis when heuristics are inconclusive.
    Returns:
        1.0 if benchmarks/evaluation results are present and clear
        0.5 if some claims are present but vague or partial
        0.0 if no performance info
    """
    try:
        from src.LLM_endpoint import score_with_llm, is_llm_available  # type: ignore
        if is_llm_available():
            context = {"card_data": getattr(model_info, "cardData", None) or {}}
            llm_score = score_with_llm("perf_claims", readme, context)
            if llm_score is not None:
                return float(llm_score)
    except Exception as e:
        logging.debug(f"perf_claims: LLM scoring failed: {e}")

    # Fallback if LLM unavailable: check for medium signals
    text = readme.lower()
    medium_keywords = ["benchmark", "evaluation", "results", "sota", "state-of-the-art", "compare", "comparison", "performance", "tested", "metric"]
    strong_keywords = ["accuracy", "f1", "precision", "recall", "bleu", "rouge", "loss", "perplexity"]

    # If any strong keyword present, give 1.0
    if any(k in text for k in strong_keywords):
        return 1.0
    # If any medium keyword present, give 0.5
    if any(k in text for k in medium_keywords):
        return 0.5
    return 0.0


def compute_perf_claims_metric(model_info: Any) -> float:
    """
    Score presence and clarity of performance claims or benchmarks using a tiered approach:

    Tier 1 (Heuristics):
        - 1.0 if clear benchmarks/metrics with tables and numbers are present
        - 0.0 if definitely no performance-related content
        - None if inconclusive

    Tier 2 (LLM - only if Tier 1 inconclusive):
        - 1.0 if benchmarks/evaluation results are present and clear
        - 0.5 if some claims are present but vague or partial
        - 0.0 if no performance info
    """
    readme = _read_readme(model_info)

    # Tier 1: Quick heuristic check
    tier1_result = _tier1_heuristic(readme, model_info)
    if tier1_result is not None:
        return tier1_result

    # Tier 2: LLM analysis for inconclusive cases
    return _tier2_llm_analysis(readme, model_info)
