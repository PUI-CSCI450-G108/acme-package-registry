import math
import os
from typing import Any, Dict

from src.metrics.helpers.pull_model import pull_model_info, UrlType
from huggingface_hub import hf_hub_download


def logistic_scale(x: float) -> float:

    k = 12
    n = 0.35
    return 1.0 - (1.0 / (1.0 + math.exp(-k * (x - n))))


def _bytes_from_safetensors_params(model_info: Any) -> int | None:
    safetensors_info = getattr(model_info, "safetensors", None)
    if not safetensors_info:
        return None

    parameters = getattr(safetensors_info, "parameters", None)
    if not parameters:
        return None

    bytes_per_dtype: Dict[str, int] = {
        "F32": 4,
        "F16": 2,
        "BF16": 2,
        "I8": 1,
        "U8": 1,
    }
    total_bytes = 0
    for dtype, count in parameters.items():
        total_bytes += int(count) * bytes_per_dtype.get(dtype, 0)
    return total_bytes if total_bytes > 0 else None


def _bytes_from_repo_files(model_info: Any) -> int | None:
    # Sum known weight file sizes. If sizes are missing, download to measure.
    weight_exts = (
        ".safetensors",
        ".bin",
        ".onnx",
        ".h5",
        ".msgpack",
        ".ot",
        ".gguf",
    )

    siblings = getattr(model_info, "siblings", [])
    total_bytes = 0
    any_found = False

    for sibling in siblings:
        rfilename = getattr(sibling, "rfilename", "")
        if not isinstance(rfilename, str):
            continue
        if not rfilename.endswith(weight_exts):
            continue
        any_found = True
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total_bytes += size
        else:
            # Fallback: get accurate size by downloading the file
            try:
                local_path = hf_hub_download(
                    model_info.id, rfilename, revision=model_info.sha
                )
                total_bytes += os.path.getsize(local_path)
            except Exception:
                # Ignore individual file failures; continue with what we have
                continue

    if not any_found:
        return None
    return total_bytes if total_bytes > 0 else None


def _bytes_from_dataset(info: Any) -> int | None:
    # Prefer explicit files metadata if present (added by helper)
    files_meta = getattr(info, "files", None)
    if isinstance(files_meta, list) and files_meta:
        total = 0
        for entry in files_meta:
            try:
                size_val = int(entry.get("size", 0)) if isinstance(entry, dict) else 0
            except Exception:
                size_val = 0
            total += size_val
        if total > 0:
            return total

    # Fallback: sum sizes from siblings, including LFS pointers
    data_exts = (
        ".parquet",
        ".csv",
        ".jsonl",
        ".json",
        ".tsv",
        ".gz",
        ".zip",
        ".z01",
        ".z02",
        ".z03",
        ".z04",
        ".z05",
        ".z06",
        ".z07",
        ".z08",
        ".z09",
        ".z10",
        ".z11",
        ".z12",
        ".z13",
        ".z14",
        ".z15",
        ".z16",
        ".z17",
        ".z18",
        ".z19",
        ".z20",
        ".z21",
        ".z22",
        ".z23",
        ".z24",
    )

    total_bytes = 0
    any_found = False
    for sibling in getattr(info, "siblings", []) or []:
        rfilename = getattr(sibling, "rfilename", "")
        if not isinstance(rfilename, str) or not rfilename:
            continue
        # Skip trivial metadata files
        if rfilename in {".gitattributes", "README.md", "LICENSE"}:
            continue
        if not rfilename.lower().endswith(data_exts):
            continue
        any_found = True
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total_bytes += size
            continue
        lfs = getattr(sibling, "lfs", None)
        lfs_size = getattr(lfs, "size", None) if lfs is not None else None
        if isinstance(lfs_size, int):
            total_bytes += lfs_size

    if not any_found:
        return None
    return total_bytes if total_bytes > 0 else None


def _bytes_from_space(info: Any) -> int | None:
    # Prefer runtime storage metrics if present
    runtime = getattr(info, "runtime", None)
    storage = getattr(runtime, "storage", None) if runtime is not None else None
    if isinstance(storage, dict):
        current = storage.get("current")
        requested = storage.get("requested")
        if isinstance(current, (int, float)) and current:
            return int(current)
        if isinstance(requested, (int, float)) and requested:
            return int(requested)

    # Fallback: sum sizes from siblings, including LFS pointers
    total_bytes = 0
    any_found = False
    for sibling in getattr(info, "siblings", []) or []:
        any_found = True
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total_bytes += size
            continue
        lfs = getattr(sibling, "lfs", None)
        lfs_size = getattr(lfs, "size", None) if lfs is not None else None
        if isinstance(lfs_size, int):
            total_bytes += lfs_size

    if not any_found:
        return None
    return total_bytes if total_bytes > 0 else None


def compute_size_metric(model_info: Any) -> dict:
    # values are in GB, using conservative capacities per device
    device_capacity_gb = {
        "raspberry_pi": 8.0,
        "jetson_nano": 12.0,
        "desktop_pc": 50.0,
        "aws_server": 100.0,
    }

    total_bytes = None

    # Spaces first (detected by runtime attribute)
    if getattr(model_info, "runtime", None) is not None:
        total_bytes = _bytes_from_space(model_info)

    # Models: prefer parameter-based estimate; fallback to files
    if total_bytes is None and getattr(model_info, "safetensors", None) is not None:
        total_bytes = _bytes_from_safetensors_params(model_info)
        if total_bytes is None:
            total_bytes = _bytes_from_repo_files(model_info)

    # Datasets: prefer files metadata; fallback to siblings
    if total_bytes is None:
        total_bytes = _bytes_from_dataset(model_info)

    # If we still cannot determine size, return zeros
    if total_bytes is None or total_bytes <= 0:
        return {device: 0.0 for device in device_capacity_gb}

    total_gb = total_bytes / (1024**3)

    # Score = max(0, 1 - (size / capacity)) per device
    scores: Dict[str, float] = {}
    for device, capacity_gb in device_capacity_gb.items():
        raw_score = logistic_scale(total_gb / capacity_gb)
        scores[device] = round(raw_score if raw_score > 0 else 0.0, 4)

    return scores


# test cases
# if __name__ == "__main__":
#     info = pull_model.pull_model_info("https://huggingface.co/google/gemma-3-270m")
#     print("google/gemma-3-270m:" + str(compute_size_metric(info)))

#     info = pull_model.pull_model_info("https://huggingface.co/datasets/xlangai/AgentNet")
#     print("datasets/xlangai/AgentNet:" + str(compute_size_metric(info)))

#     info = pull_model.pull_model_info("https://huggingface.co/spaces/gradio/hello_world")
#     print("spaces/gradio/hello_world:" + str(compute_size_metric(info) ))
