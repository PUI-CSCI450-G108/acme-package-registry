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
    # 1. Check the structured cardData
    dataset_mentioned = False
    if (
        hasattr(model_info, "cardData")
        and model_info.cardData
        and model_info.cardData.get("datasets")
    ):
        dataset_mentioned = True
    # 2. Check README for more specific dataset references
    elif any(keyword in readme_lower for keyword in [
        "trained on", "training data", "dataset:", "datasets:",
        "training set", "data source", "corpus"
    ]):
        dataset_mentioned = True

    if dataset_mentioned:
        score += 0.5

    # Check for Code/Example Availability (+0.5)
    # 1. Check for common script files in the repo
    code_available = False
    if hasattr(model_info, "siblings") and any(
        s.rfilename.endswith((".py", ".ipynb")) for s in model_info.siblings
    ):
        code_available = True
    # 2. Check README for keywords
    elif any(
        keyword in readme_lower
        for keyword in ["example", "inference", "fine-tuning", "how to use", "notebook"]
    ):
        code_available = True

    if code_available:
        score += 0.5

    return score
