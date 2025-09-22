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


def compute_dataset_quality_metric(model_info: Any) -> float:
    """
    Computes the quality of the documented dataset.
    - 1.0: Dataset is named, and README describes its properties.
    - 0.5: Dataset is named, but README lacks detail.
    - 0.0: No dataset is clearly documented.
    """
    # Step 1: Check if a dataset is mentioned at all
    dataset_name = None
    if (
        hasattr(model_info, "cardData")
        and model_info.cardData
        and model_info.cardData.get("datasets")
    ):
        dataset_name = model_info.cardData.get("datasets")

    if not dataset_name:
        return 0.0  # If no dataset is linked in metadata, quality is 0

    # Step 2: Analyze README for quality of documentation
    readme_content = _fetch_readme_content(model_info)
    if not readme_content:
        return 0.5  # Dataset is named, but we can't verify quality from README

    readme_lower = readme_content.lower()

    # Keywords that indicate good documentation about the dataset
    quality_keywords = ["size", "samples", "split", "features", "diversity", "source"]

    found_keywords = sum(1 for keyword in quality_keywords if keyword in readme_lower)

    # Scoring based on findings
    if found_keywords >= 2:
        # If at least two quality indicators are present, score is high
        return 1.0
    elif found_keywords == 1:
        # If only one is present, it's partial
        return 0.75
    else:
        # Named but not described well in the README
        return 0.5
