from enum import Enum

import validators
from huggingface_hub import HfApi


# Define enum for url types
# Define enum for url types
class UrlType(Enum):
    HUGGING_FACE_MODEL = "hugging_face_model"
    HUGGING_FACE_DATASET = "hugging_face_dataset"
    HUGGING_FACE_CODEBASE = "hugging_face_codebase"
    GIT_REPO = "git_repo"
    OTHER = "other"
    INVALID = "invalid"


def pull_model_info(url: str) -> dict:
    # This is the fix: instantiate HfApi inside the function
    hf_api = HfApi()

    url_type = get_url_type(url)
    if url_type == UrlType.INVALID:
        raise ValueError("Invalid URL: " + url)

    if url_type == UrlType.HUGGING_FACE_DATASET:
        name = url.split("/datasets/")[1]
        info = hf_api.dataset_info(name, files_metadata=True)
    elif url_type == UrlType.HUGGING_FACE_MODEL:
        name = url.split("huggingface.co/")[1]
        info = hf_api.model_info(name, files_metadata=True)
    elif url_type == UrlType.HUGGING_FACE_CODEBASE:
        name = url.split("/spaces/")[1]
        info = hf_api.space_info(name, files_metadata=True)
    elif url_type == UrlType.GIT_REPO:
        return None
    elif url_type == UrlType.OTHER:
        raise ValueError("Other URL type: " + url)
    else:
        # Should be unreachable, but good practice
        raise ValueError(f"Unhandled URL type: {url_type.name}")

    return info


# Parses the url and returns the type of the url
def get_url_type(url: str) -> str:
    if not validators.url(url):
        return UrlType.INVALID

    if url.startswith("https://github.com/"):
        return UrlType.GIT_REPO

    if not url.startswith("https://huggingface.co/"):
        return UrlType.OTHER

    if "/datasets/" in url:
        return UrlType.HUGGING_FACE_DATASET

    if "/spaces/" in url:
        return UrlType.HUGGING_FACE_CODEBASE

    # Default to model if it's on huggingface.co and not a dataset/space
    return UrlType.HUGGING_FACE_MODEL