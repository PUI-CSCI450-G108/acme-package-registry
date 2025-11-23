"""
Reproducibility metric.

Measures whether the model can be reproduced using information provided
in the model card, repository, and associated documentation.

Scoring:
- 1.0: All reproducibility elements present (code, configs, dataset, instructions)
- 0.7: Most elements present
- 0.5: Some elements present (partial reproducibility)
- 0.3: Minimal information
- 0.0: No reproducibility information
"""

import logging
from typing import Any

try:
    from huggingface_hub import HfFileSystem, hf_hub_download
except ImportError:
    HfFileSystem = None
    hf_hub_download = None

logger = logging.getLogger(__name__)


def _fetch_readme_content(model_info: Any) -> str:
    """
    Fetch README.md content from HuggingFace model repository.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        README content as string, or empty string if not available
    """
    if not HfFileSystem or not hf_hub_download:
        return ""

    try:
        fs = HfFileSystem()
        paths = fs.ls(model_info.id, detail=False)
        if not any(p.endswith("README.md") for p in paths):
            return ""

        readme_file = hf_hub_download(
            repo_id=model_info.id, filename="README.md", repo_type="model"
        )
        with open(readme_file, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.debug(f"Could not fetch README for {model_info.id}: {e}")
        return ""


def _check_training_code(model_info: Any) -> float:
    """
    Check for presence of training scripts.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    try:
        siblings = getattr(model_info, "siblings", [])
        files = [s.rfilename for s in siblings]

        # Look for training scripts
        training_indicators = ["train", "training", "fine_tune", "finetune"]
        py_files = [f for f in files if f.endswith(".py")]

        has_training_code = any(
            any(indicator in f.lower() for indicator in training_indicators)
            for f in py_files
        )

        return 1.0 if has_training_code else 0.0
    except Exception as e:
        logger.debug(f"Error checking training code: {e}")
        return 0.0


def _check_config_files(model_info: Any) -> float:
    """
    Check for presence of configuration files.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    try:
        siblings = getattr(model_info, "siblings", [])
        files = [s.rfilename for s in siblings]

        # Look for config files
        config_files = [
            "config.json",
            "training_args.json",
            "trainer_config.json",
            "hyperparameters.json",
        ]
        yaml_configs = [f for f in files if f.endswith((".yaml", ".yml"))]

        has_json_config = any(cf in files for cf in config_files)
        has_yaml_config = len(yaml_configs) > 0

        if has_json_config and has_yaml_config:
            return 1.0
        elif has_json_config or has_yaml_config:
            return 0.7
        else:
            return 0.0
    except Exception as e:
        logger.debug(f"Error checking config files: {e}")
        return 0.0


def _check_dataset_documentation(model_info: Any) -> float:
    """
    Check for dataset documentation in cardData.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    try:
        card_data = getattr(model_info, "cardData", None) or {}
        datasets = card_data.get("datasets", [])

        if not datasets:
            return 0.0

        # Check if datasets are documented (not empty)
        documented_datasets = [d for d in datasets if d and isinstance(d, str)]
        if len(documented_datasets) > 0:
            return 1.0
        else:
            return 0.0
    except Exception as e:
        logger.debug(f"Error checking dataset documentation: {e}")
        return 0.0


def _check_environment_files(model_info: Any) -> float:
    """
    Check for environment specification files.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Score between 0.0 and 1.0
    """
    try:
        siblings = getattr(model_info, "siblings", [])
        files = [s.rfilename for s in siblings]

        # Look for dependency/environment files
        env_files = [
            "requirements.txt",
            "environment.yml",
            "environment.yaml",
            "Pipfile",
            "pyproject.toml",
            "setup.py",
            "Dockerfile",
        ]

        has_env_file = any(ef in files for ef in env_files)
        return 1.0 if has_env_file else 0.0
    except Exception as e:
        logger.debug(f"Error checking environment files: {e}")
        return 0.0


def _check_readme_reproduction_info(readme_content: str) -> float:
    """
    Check README for reproduction-related information.

    Args:
        readme_content: Content of README.md

    Returns:
        Score between 0.0 and 1.0
    """
    if not readme_content:
        return 0.0

    readme_lower = readme_content.lower()

    # Look for reproduction-related sections and keywords
    reproduction_keywords = [
        "reproduc",  # matches reproduce, reproduction, reproducibility
        "training",
        "fine-tun",  # matches fine-tune, fine-tuning
        "hyperparameter",
        "random seed",
        "seed",
        "how to train",
        "training procedure",
        "training details",
    ]

    matches = sum(1 for kw in reproduction_keywords if kw in readme_lower)

    # Score based on number of matches
    if matches >= 5:
        return 1.0
    elif matches >= 3:
        return 0.7
    elif matches >= 1:
        return 0.4
    else:
        return 0.0


def compute_reproducibility_metric(model_info: Any) -> float:
    """
    Compute reproducibility score based on presence of training code, configs,
    dataset documentation, environment specs, and README information.

    Scoring rubric:
    - Training code: 25%
    - Config files: 25%
    - Dataset documentation: 20%
    - Environment files: 15%
    - README reproduction info: 15%

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        Reproducibility score between 0.0 and 1.0
    """
    try:
        # Fetch README content
        readme_content = _fetch_readme_content(model_info)

        # Component scores
        training_code_score = _check_training_code(model_info)
        config_score = _check_config_files(model_info)
        dataset_score = _check_dataset_documentation(model_info)
        environment_score = _check_environment_files(model_info)
        readme_score = _check_readme_reproduction_info(readme_content)

        # Weighted combination
        final_score = (
            training_code_score * 0.25
            + config_score * 0.25
            + dataset_score * 0.20
            + environment_score * 0.15
            + readme_score * 0.15
        )

        # Ensure score is within bounds
        final_score = max(0.0, min(1.0, final_score))

        logger.debug(
            f"Reproducibility scores - code: {training_code_score:.2f}, "
            f"config: {config_score:.2f}, dataset: {dataset_score:.2f}, "
            f"env: {environment_score:.2f}, readme: {readme_score:.2f}, "
            f"final: {final_score:.2f}"
        )

        return round(final_score, 4)

    except Exception as e:
        logger.error(f"Error computing reproducibility metric: {e}")
        return 0.0
