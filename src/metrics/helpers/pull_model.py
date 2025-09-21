from huggingface_hub import HfApi
import validators
from enum import Enum

 
# Define enum for url types
class UrlType(Enum):
    HUGGING_FACE_MODEL = "hugging_face_model",
    HUGGING_FACE_DATASET = "hugging_face_dataset",
    HUGGING_FACE_CODEBASE = "hugging_face_codebase",
    GIT_REPO = "git_repo",
    OTHER = "other",
    INVALID = "invalid"


hf_api = HfApi()

def pull_model_info(url: str) -> dict:
    url_type = get_url_type(url)
    if url_type == UrlType.INVALID:
        raise ValueError("Invalid URL: " + url)

    if url_type == UrlType.HUGGING_FACE_DATASET:
        # Dataset: https://huggingface.co/datasets/<namespace>/<repo>
        # get string after /datasets/
        name = url.split("/datasets/")[1]
        info = hf_api.dataset_info(name, files_metadata=True)
    if url_type == UrlType.HUGGING_FACE_MODEL:
        # Model: https://huggingface.co/<namespace>/<repo>
        name = url.split("huggingface.co/")[1]
        info = hf_api.model_info(name, files_metadata=True)
    if url_type == UrlType.HUGGING_FACE_CODEBASE:
        # Code/Space: https://huggingface.co/spaces/<namespace>/<repo>
        name = url.split("/spaces/")[1]
        info = hf_api.space_info(name, files_metadata=True)
    if url_type == UrlType.GIT_REPO:
        # TODO: Implement git repo info pull
        return None
    if url_type == UrlType.OTHER:
        raise ValueError("Other URL type: " + url)

    return info




## Parses the url and returns the type of the url
def get_url_type(url: str) -> str:

    if not validators.url(url):
        return UrlType.INVALID

    # Verify the URL is hosted on Hugging Face or Github
    if url.startswith("https://github.com/"):
        return UrlType.GIT_REPO

    if not url.startswith("https://huggingface.co/"):
        return UrlType.OTHER

    # Model: https://huggingface.co/<namespace>/<repo>
    # Dataset: https://huggingface.co/datasets/<namespace>/<repo>
    # Code/Space: https://huggingface.co/spaces/<namespace>/<repo>

    if url.startswith("https://huggingface.co/datasets/"):
        return UrlType.HUGGING_FACE_DATASET

    if url.startswith("https://huggingface.co/spaces/"):
        return UrlType.HUGGING_FACE_CODEBASE

    if url.startswith("https://huggingface.co/"):
        return UrlType.HUGGING_FACE_MODEL

    return UrlType.INVALID


# Test cases

# info = pull_model_info("https://huggingface.co/google/gemma-3-270m")
# print("Model:\n\n\n\n")
# print(info)

# print("Dataset:\n\n\n\n")
# info = pull_model_info("https://huggingface.co/datasets/xlangai/AgentNet")
# print(info)

# print("Space:\n\n\n\n")
# info = pull_model_info("https://huggingface.co/spaces/gradio/hello_world")
# print(info)


