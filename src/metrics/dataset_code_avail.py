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


def compute_dataset_code_avail_metric(model_info: Any) -> float:
    """
    Computes the score for dataset and code availability.
    - +0.5 if a training dataset is clearly mentioned.
    - +0.5 if example code/scripts are available.
    """
    score = 0.0
    readme_content = _fetch_readme_content(model_info)
    readme_lower = readme_content.lower()

    # Check for Dataset Availability (+0.5)
    # 1. Check the structured cardData - must be a non-empty list/value
    dataset_mentioned = False
    if (
        hasattr(model_info, "cardData")
        and model_info.cardData
        and model_info.cardData.get("datasets")
    ):
        datasets = model_info.cardData.get("datasets")
        # Only count if it's a meaningful value (not empty list/string)
        if (isinstance(datasets, list) and len(datasets) > 0) or (isinstance(datasets, str) and len(datasets) > 0):
            dataset_mentioned = True
    # 2. Check README for specific dataset mention patterns (not just the word "dataset")
    if not dataset_mentioned:
        # Look for "trained on X" pattern where X is likely a dataset name
        if "trained on" in readme_lower and any(word in readme_lower for word in ["dataset", "data", "corpus"]):
            dataset_mentioned = True

    if dataset_mentioned:
        score += 0.5

    # Check for Code/Example Availability (+0.5)
    # 1. Check for common script files in the repo
    code_available = False
    if hasattr(model_info, "siblings"):
        # Check for .py or .ipynb files
        code_files = [s for s in model_info.siblings if hasattr(s, "rfilename") and s.rfilename.endswith((".py", ".ipynb"))]
        if len(code_files) > 0:
            code_available = True
    # 2. Check README for keywords - must have code blocks or specific usage sections
    if not code_available and ("```python" in readme_content or ("```" in readme_content and "import" in readme_lower)):
        code_available = True

    if code_available:
        score += 0.5

    return score
