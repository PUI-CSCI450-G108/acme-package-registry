import types
from unittest.mock import patch

import pytest

from src.metrics.size import (
    _bytes_from_safetensors_params,
    _bytes_from_repo_files,
    _bytes_from_dataset,
    _bytes_from_space,
    compute_size_metric,
    logistic_scale,
)


def test_bytes_from_safetensors_params_basic():
    safetensors = types.SimpleNamespace(parameters={"F16": 3, "I8": 10})
    model_info = types.SimpleNamespace(safetensors=safetensors)
    assert _bytes_from_safetensors_params(model_info) == (3 * 2 + 10 * 1)


def test_bytes_from_safetensors_params_none_return():
    # No safetensors attribute
    model_info = types.SimpleNamespace()
    assert _bytes_from_safetensors_params(model_info) is None


def test_bytes_from_safetensors_no_parameters_return():
    # parameters missing/empty -> None
    safetensors = types.SimpleNamespace(parameters={})
    model_info = types.SimpleNamespace(safetensors=safetensors)
    assert _bytes_from_safetensors_params(model_info) is None


@patch("src.metrics.size.os.path.getsize", return_value=1500)
@patch("src.metrics.size.hf_hub_download", return_value="/tmp/dl.bin")
def test_bytes_from_repo_files_with_download_fallback(mock_dl, mock_getsize):
    # One file with size present, one requiring download
    sib1 = types.SimpleNamespace(rfilename="weights.bin", size=500)
    sib2 = types.SimpleNamespace(rfilename="model.safetensors", size=None)
    sib3 = types.SimpleNamespace(rfilename="README.md", size=999)  # skipped
    model_info = types.SimpleNamespace(id="repo", sha="main", siblings=[sib1, sib2, sib3])
    total = _bytes_from_repo_files(model_info)
    assert total == 500 + 1500
    mock_dl.assert_called_once()
    mock_getsize.assert_called_once()


@patch("src.metrics.size.hf_hub_download", side_effect=Exception("network"))
def test_bytes_from_repo_files_download_exception_is_ignored(mock_dl):
    sib = types.SimpleNamespace(rfilename="weights.bin", size=None)
    model_info = types.SimpleNamespace(id="repo", sha="main", siblings=[sib])
    assert _bytes_from_repo_files(model_info) is None


def test_bytes_from_repo_files_no_weight_files_returns_none():
    sib1 = types.SimpleNamespace(rfilename=None, size=100)
    sib2 = types.SimpleNamespace(rfilename="notes.txt", size=200)
    model_info = types.SimpleNamespace(id="repo", sha="main", siblings=[sib1, sib2])
    assert _bytes_from_repo_files(model_info) is None


def test_bytes_from_dataset_prefers_files_metadata():
    info = types.SimpleNamespace(files=[{"size": 100}, {"size": 250}], siblings=[])
    assert _bytes_from_dataset(info) == 350


def test_bytes_from_dataset_files_metadata_bad_size_ignored():
    info = types.SimpleNamespace(files=[{"size": "abc"}, {"size": 10}], siblings=[])
    assert _bytes_from_dataset(info) == 10


def test_bytes_from_dataset_fallback_to_siblings_and_lfs():
    lfs_obj = types.SimpleNamespace(size=50)
    sib1 = types.SimpleNamespace(rfilename="data.parquet", size=100, lfs=None)
    sib2 = types.SimpleNamespace(rfilename="more.json", size=None, lfs=lfs_obj)
    sib3 = types.SimpleNamespace(rfilename="README.md", size=999, lfs=None)  # skipped
    info = types.SimpleNamespace(files=None, siblings=[sib1, sib2, sib3])
    assert _bytes_from_dataset(info) == 150


def test_bytes_from_dataset_fallback_skips_nonstring_and_nondata_ext():
    sib1 = types.SimpleNamespace(rfilename=None, size=100, lfs=None)
    sib2 = types.SimpleNamespace(rfilename="notes.txt", size=200, lfs=None)
    info = types.SimpleNamespace(files=None, siblings=[sib1, sib2])
    assert _bytes_from_dataset(info) is None


def test_bytes_from_space_from_runtime_storage():
    runtime = types.SimpleNamespace(storage={"current": 12345})
    info = types.SimpleNamespace(runtime=runtime, siblings=None)
    assert _bytes_from_space(info) == 12345


def test_bytes_from_space_fallback_sums_siblings_and_lfs():
    runtime = types.SimpleNamespace(storage={})
    sib1 = types.SimpleNamespace(size=100)
    sib2 = types.SimpleNamespace(size=None, lfs=types.SimpleNamespace(size=50))
    info = types.SimpleNamespace(runtime=runtime, siblings=[sib1, sib2])
    assert _bytes_from_space(info) == 150


def test_bytes_from_space_fallback_no_siblings_returns_none():
    runtime = types.SimpleNamespace(storage={})
    info = types.SimpleNamespace(runtime=runtime, siblings=[])
    assert _bytes_from_space(info) is None


def test_compute_size_metric_returns_zeros_when_unknown():
    scores = compute_size_metric(types.SimpleNamespace())
    assert set(scores.keys()) == {"raspberry_pi", "jetson_nano", "desktop_pc", "aws_server"}
    assert all(v == 0.0 for v in scores.values())


def test_compute_size_metric_for_dataset_files_metadata_uses_logistic_scale():
    # Construct ~4 GiB total to get non-trivial scores
    total_bytes = 4 * (1024 ** 3)
    info = types.SimpleNamespace(files=[{"size": total_bytes}], siblings=None)
    scores = compute_size_metric(info)

    device_capacity_gb = {
        "raspberry_pi": 8.0,
        "jetson_nano": 12.0,
        "desktop_pc": 50.0,
        "aws_server": 100.0,
    }
    total_gb = total_bytes / (1024 ** 3)

    expected = {
        device: round(logistic_scale(total_gb / capacity), 4)
        for device, capacity in device_capacity_gb.items()
    }
    assert scores == expected


def test_compute_size_metric_for_space_uses_fallback_sum():
    runtime = types.SimpleNamespace(storage={})
    sib1 = types.SimpleNamespace(size=1024 * 1024)
    info = types.SimpleNamespace(runtime=runtime, siblings=[sib1])
    scores = compute_size_metric(info)
    assert all(v >= 0.0 for v in scores.values())


def test_compute_size_metric_for_model_prefers_parameters():
    safetensors = types.SimpleNamespace(parameters={"F16": 2})  # 4 bytes total
    info = types.SimpleNamespace(safetensors=safetensors, siblings=[])
    scores = compute_size_metric(info)
    assert all(v >= 0.0 for v in scores.values())


@patch("src.metrics.size.os.path.getsize", return_value=2048)
@patch("src.metrics.size.hf_hub_download", return_value="/tmp/file")
def test_compute_size_metric_model_fallback_to_repo_files(mock_dl, mock_getsize):
    safetensors = types.SimpleNamespace(parameters={})  # forces fallback
    sib = types.SimpleNamespace(rfilename="model.bin", size=None)
    info = types.SimpleNamespace(id="repo", sha="main", safetensors=safetensors, siblings=[sib])
    scores = compute_size_metric(info)
    assert all(v >= 0.0 for v in scores.values())


