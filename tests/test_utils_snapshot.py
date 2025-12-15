import os
import types
import json
import pytest


# Target module
import lambda_handlers.utils as utils


class DummyResponse:
    def __init__(self, status_code=403):
        self.status_code = status_code


class DummyHTTPStatusError(Exception):
    def __init__(self, response=None):
        self.response = response or DummyResponse(403)


@pytest.fixture(autouse=True)
def configure_env(monkeypatch):
    monkeypatch.setenv("ARTIFACTS_BUCKET", "test-bucket")
    # Recreate s3 client with bucket present
    monkeypatch.setattr(utils, "BUCKET_NAME", "test-bucket", raising=False)
    # Mock s3 client
    class S3Mock:
        def __init__(self):
            self.puts = []
        def put_object(self, Bucket, Key, Body, ContentType):
            # record payload
            self.puts.append({
                "Bucket": Bucket,
                "Key": Key,
                "BodyLen": len(Body) if isinstance(Body, (bytes, bytearray)) else (len(Body) if hasattr(Body, "__len__") else 0),
                "ContentType": ContentType,
            })
    s3 = S3Mock()
    monkeypatch.setattr(utils, "s3_client", s3, raising=False)
    return s3


def test_is_essential_file_filters_weights():
    assert utils.is_essential_file("config.json")
    assert utils.is_essential_file("tokenizer.json")
    assert not utils.is_essential_file("pytorch_model.bin")
    assert not utils.is_essential_file("model.safetensors")
    assert not utils.is_essential_file("weights.onnx")


def test_upload_hf_files_to_s3_gated_fast_fail(monkeypatch, configure_env):
    # Ensure placeholder is stored first
    # Mock store_simple_zip to write a small payload
    def store_zip(artifact_id, hf_url):
        utils.s3_client.put_object(
            Bucket=utils.BUCKET_NAME,
            Key=f"artifacts/{artifact_id}/data.zip",
            Body=b"placeholder",
            ContentType="application/zip",
        )
    monkeypatch.setattr(utils, "store_simple_zip", store_zip)

    # Mock snapshot_download to raise gated error quickly
    def snapshot_download(**kwargs):
        from huggingface_hub.errors import GatedRepoError
        raise GatedRepoError("gated")
    monkeypatch.setattr(utils, "snapshot_download", snapshot_download)

    key = utils.upload_hf_files_to_s3("abc123", "https://huggingface.co/org/model")

    # Returns None and should have exactly one put_object from placeholder
    assert key is None
    puts = utils.s3_client.puts
    assert len(puts) == 1
    assert puts[0]["Key"] == "artifacts/abc123/data.zip"
    assert puts[0]["Bucket"] == utils.BUCKET_NAME


def test_upload_hf_files_to_s3_success_overwrites_placeholder(monkeypatch, configure_env):
    # Placeholder first
    def store_zip(artifact_id, hf_url):
        utils.s3_client.put_object(
            Bucket=utils.BUCKET_NAME,
            Key=f"artifacts/{artifact_id}/data.zip",
            Body=b"placeholder",
            ContentType="application/zip",
        )
    monkeypatch.setattr(utils, "store_simple_zip", store_zip)

    # Create a fake local_dir structure
    tmp_root = os.getcwd()
    fake_dir = os.path.join(tmp_root, "_fake_snapshot")
    os.makedirs(fake_dir, exist_ok=True)
    # essential
    with open(os.path.join(fake_dir, "config.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"a": 1}))
    # weight should be ignored
    with open(os.path.join(fake_dir, "pytorch_model.bin"), "wb") as f:
        f.write(b"0" * 32)

    # Mock snapshot_download to return fake_dir
    def snapshot_download(**kwargs):
        return fake_dir
    monkeypatch.setattr(utils, "snapshot_download", snapshot_download)

    key = utils.upload_hf_files_to_s3("xyz789", "https://huggingface.co/org/model")

    # Should overwrite: two puts (placeholder + snapshot)
    puts = utils.s3_client.puts
    assert key == "artifacts/xyz789/data.zip"
    assert len(puts) == 2
    # Second upload should be the snapshot zip
    assert puts[-1]["Key"] == "artifacts/xyz789/data.zip"
    assert puts[-1]["Bucket"] == utils.BUCKET_NAME
    # Cleanup
    try:
        os.remove(os.path.join(fake_dir, "config.json"))
        os.remove(os.path.join(fake_dir, "pytorch_model.bin"))
        os.rmdir(fake_dir)
    except Exception:
        pass
