import os
from typing import Any, Dict, List, Optional

from huggingface_hub import DatasetInfo, HfApi, ModelInfo


class HuggingFaceAPI:
    def __init__(self, token: Optional[str] = None):
        if token is None:
            token = (
                os.environ.get("HF_API_TOKEN")
                or os.environ.get("HUGGINGFACE_HUB_TOKEN")
                or os.environ.get("HF_TOKEN")
            )
        self.api = HfApi(token=token)

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        return self.api.model_info(model_id)

    def get_dataset_info(self, dataset_id: str) -> Optional[DatasetInfo]:
        return self.api.dataset_info(dataset_id)

    def get_model_metadata(self, model_id: str) -> Optional[Dict[str, Any]]:
        info = self.get_model_info(model_id)
        if info:
            return {
                "downloads": info.downloads,
                "likes": info.likes,
                "last_modified": info.lastModified,
                "files": [f.rfilename for f in info.siblings],
                "license": info.cardData.get("license") if info.cardData else None,
            }
        return None
    def list_repo_commits(self, repo_id: str, repo_type: str = "model", limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.api.list_repo_commits(repo_id=repo_id, repo_type=repo_type)


def test_connection():
    api = HuggingFaceAPI()
    model_id = "bert-base-uncased"
    metadata = api.get_model_metadata(model_id)

    if metadata:
        print("✅ API connection successful!")
        print("Model metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")
    else:
        print(
            "Failed to fetch model metadata. Check your token or internet connection."
        )


if __name__ == "__main__":
    test_connection()
