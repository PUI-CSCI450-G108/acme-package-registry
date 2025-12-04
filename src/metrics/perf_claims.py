from typing import Any
import logging
import re


def _read_readme(model_info: Any) -> str:
    try:
        from src.metrics.dataset_code_avail import _fetch_readme_content  # type: ignore
        return _fetch_readme_content(model_info) or ""
    except Exception as e:
        logging.debug(f"perf_claims: README fetch failed for {getattr(model_info, 'id', '?')}: {e}")
        return ""


def compute_perf_claims_metric(model_info: Any) -> float:
    """
    Score presence and clarity of performance claims or benchmarks:
    - 1.0 if benchmarks/evaluation results are present and clear
    - 0.5 if some claims are present but vague or partial
    - 0.0 if no performance info
    """
    readme = _read_readme(model_info)

    # Try LLM-based assessment first if available
    try:
        from src.LLM_endpoint import score_with_llm, is_llm_available  # type: ignore
        if is_llm_available():
            context = {"card_data": getattr(model_info, "cardData", None) or {}}
            llm_score = score_with_llm("perf_claims", readme, context)
            if llm_score is not None:
                return float(llm_score)
    except Exception as e:
        logging.debug(f"perf_claims: LLM scoring unavailable: {e}")
    text = readme.lower()

    # Strong signals: tables with metric names and numeric values
    strong_keywords = [
        "accuracy", "f1", "f1-score", "precision", "recall", "bleu", "rouge", "cer", "wer",
        "latency", "throughput", "ms", "fps", "samples/s", "glue", "squad", "mmlu", "hellaswag",
        "perplexity", "loss", "auc", "mae", "rmse", "map"
    ]
    has_table = "|" in text and "---" in text  # markdown table heuristic
    numbers = re.findall(r"\b\d{1,3}(?:\.\d+)?%?\b", text)

    # Strong hit if: (table OR list with metrics) AND keywords AND numbers
    has_structured_metrics = has_table or (any(k in text for k in strong_keywords) and len(numbers) >= 2)
    strong_hit = has_structured_metrics and any(k in text for k in strong_keywords)

    # Medium signals: words like benchmark, evaluation, results, SOTA, without enough detail
    medium_keywords = ["benchmark", "evaluation", "results", "sota", "state-of-the-art", "compare", "comparison"]
    medium_hit = any(k in text for k in medium_keywords)

    # cardData may contain evaluation results too
    try:
        card = getattr(model_info, "cardData", None)
        if isinstance(card, dict):
            if any(key in card for key in ("metrics", "evaluation", "results")):
                strong_hit = True
    except Exception:
        pass

    if strong_hit:
        return 1.0
    if medium_hit:
        return 0.5
    return 0.0
