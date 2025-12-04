import logging
import math
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


def compute_ramp_up_metric(model_info: Any) -> float:
    """
    Computes the ramp-up time score based on the README word count.
    The score is based on a Gaussian function centered around an ideal word count,
    penalizing READMEs that are too short or too long.
    """
    readme_content = _fetch_readme_content(model_info)
    if not readme_content:
        return 0.5

    word_count = len(readme_content.split())

    # Parameters for the "ideal" word count, as discussed in the plan.
    mu = 1000  # Ideal word count
    sigma = 500  # Standard deviation

    # Gaussian function to score based on deviation from the ideal
    score = math.exp(-((word_count - mu) ** 2) / (2 * sigma**2))

    return round(score, 4)
