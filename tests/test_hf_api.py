from types import SimpleNamespace
from unittest.mock import patch
from src.hf_api import HuggingFaceAPI

def test_get_model_metadata_happy_path():
    fake_info = SimpleNamespace(
        downloads=123, likes=7, lastModified="2024-01-01",
        siblings=[SimpleNamespace(rfilename="weights.safetensors"), SimpleNamespace(rfilename="README.md")],
        cardData={"license": "apache-2.0"},
    )
    with patch("src.hf_api.HfApi") as Mock:
        Mock.return_value.model_info.return_value = fake_info
        api = HuggingFaceAPI(token="dummy")
        meta = api.get_model_metadata("org/model")
        assert meta["downloads"] == 123
        assert "weights.safetensors" in meta["files"]
        assert meta["license"] == "apache-2.0"

def test_get_model_metadata_none():
    with patch("src.hf_api.HfApi") as Mock:
        Mock.return_value.model_info.return_value = None
        api = HuggingFaceAPI(token="dummy")
        assert api.get_model_metadata("missing/model") is None
