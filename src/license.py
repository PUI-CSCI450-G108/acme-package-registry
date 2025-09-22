import logging
import re
from typing import Any
from huggingface_hub import hf_hub_download, HfFileSystem


def _fetch_readme_content(model_info: Any) -> str:
    """Fetches the README content for a given model."""
    try:
        # Check if README.md exists in the sibling files list
        fs = HfFileSystem()
        paths = fs.ls(model_info.id, detail=False)
        readme_path = next(
            (p for p in paths if p.endswith("README.md")), None
        )

        if not readme_path:
            logging.warning(f"No README.md file found for model {model_info.id}")
            return ""

        readme_file = hf_hub_download(
            repo_id=model_info.id,
            filename="README.md",
            repo_type="model",
        )
        with open(readme_file, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"Could not download or read README for {model_info.id}: {e}")
        return ""


def compute_license_metric(model_info: Any) -> float:
    """
    Computes the license score based on compatibility with LGPLv2.1.
    - 1.0: Clearly compatible
    - 0.5: Unclear or not specified
    - 0.0: Clearly incompatible
    """
    # List of common licenses compatible with LGPLv2.1
    compatible_licenses = [
        "mit",
        "apache-2.0",
        "bsd-3-clause",
        "bsd-2-clause",
        "lgpl-2.1",
        "epl-2.0",
        "mpl-2.0",
    ]

    # List of common licenses incompatible with LGPLv2.1
    incompatible_licenses = ["gpl-3.0", "agpl-3.0", "cc-by-nc"]

    license_str = ""
    # Prefer the structured license field in cardData
    if hasattr(model_info, "cardData") and model_info.cardData and "license" in model_info.cardData:
        license_str = model_info.cardData["license"]

    if not license_str:
        # Fallback to searching the README
        readme_content = _fetch_readme_content(model_info)
        if not readme_content:
            return 0.5  # Unclear if there's no README

        # Search for a "License" section
        match = re.search(r"##?\s*License\s*\n(.+?)(?=\n##|$)", readme_content, re.IGNORECASE | re.DOTALL)
        if match:
            license_str = match.group(1).strip().lower()
        else:
            return 0.5 # Unclear if no license section

    if not license_str:
        return 0.5 # Unclear

    # Check for compatibility
    license_str_lower = license_str.lower()
    for lic in incompatible_licenses:
        if lic in license_str_lower:
            return 0.0

    for lic in compatible_licenses:
        if lic in license_str_lower:
            return 1.0

    return 0.5 # Unclear if it doesn't match known lists