from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict



from huggingface_hub import hf_hub_download

from src.metrics.helpers.pull_model import UrlType, pull_model_info

# Configure logger for size metric
logger = logging.getLogger(__name__)


def _bytes_from_safetensors_params(model_info: Any) -> int | None:
    logger.debug("Attempting to get size from safetensors parameters")
    safetensors_info = getattr(model_info, "safetensors", None)
    if not safetensors_info:
        logger.debug("No safetensors info found")
        return None

    parameters = getattr(safetensors_info, "parameters", None)
    if not parameters:
        logger.debug("Safetensors found but no parameters attribute")
        return None

    logger.debug(f"Found safetensors parameters: {parameters}")
    bytes_per_dtype: Dict[str, int] = {
        "F32": 4,
        "F16": 2,
        "BF16": 2,
        "I8": 1,
        "U8": 1,
    }
    total_bytes = 0
    for dtype, count in parameters.items():
        dtype_bytes = bytes_per_dtype.get(dtype, 0)
        total_bytes += int(count) * dtype_bytes
        logger.debug(f"  {dtype}: {count} params × {dtype_bytes} bytes = {int(count) * dtype_bytes} bytes")

    logger.debug(f"Total bytes from safetensors params: {total_bytes}")
    return total_bytes if total_bytes > 0 else None


def _download_file_with_retry(model_id: str, filename: str, revision: str, max_retries: int = 3) -> tuple[str, int, bool]:
    """
    Download a single file with retry logic and exponential backoff.

    Args:
        model_id: HuggingFace model ID
        filename: File to download
        revision: Model revision/commit hash
        max_retries: Maximum number of retry attempts

    Returns:
        Tuple of (filename, size_bytes, success_flag)
    """
    for attempt in range(max_retries):
        try:
            local_path = hf_hub_download(model_id, filename, revision=revision)
            file_size = os.path.getsize(local_path)
            if attempt > 0:
                logger.info(f"  ✓ {filename}: {file_size} bytes (succeeded on retry {attempt})")
            else:
                logger.debug(f"  ✓ {filename}: {file_size} bytes")
            return (filename, file_size, True)
        except Exception as e:
            logger.exception(f"Exception occurred while downloading {filename} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s, 4s
                wait_time = 2 ** attempt
                logger.warning(f"  Retry {attempt + 1}/{max_retries} for {filename} after error: {type(e).__name__}: {e}")
                logger.debug(f"    Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                logger.error(f"  ✗ {filename}: All {max_retries} attempts failed - {type(e).__name__}: {e}")
                return (filename, 0, False)

    return (filename, 0, False)


def _download_files_concurrently(model_id: str, filenames: list[str], revision: str) -> dict[str, int]:
    """
    Download multiple files concurrently with retry logic.

    Args:
        model_id: HuggingFace model ID
        filenames: List of files to download
        revision: Model revision/commit hash

    Returns:
        Dictionary mapping successfully downloaded filenames to their sizes
    """
    if not filenames:
        return {}

    # Dynamic worker count: min(file_count, 6) to adapt to workload
    max_workers = min(len(filenames), 6)
    logger.info(f"Downloading {len(filenames)} files concurrently with {max_workers} workers...")

    successful_downloads = {}
    failed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_filename = {
            executor.submit(_download_file_with_retry, model_id, filename, revision): filename
            for filename in filenames
        }

        # Collect results as they complete
        for future in as_completed(future_to_filename):
            filename, size_bytes, success = future.result()
            if success:
                successful_downloads[filename] = size_bytes
            else:
                failed_count += 1

    success_count = len(successful_downloads)
    total_count = len(filenames)

    if success_count == total_count:
        logger.info(f"✓ Successfully downloaded all {total_count} files")
    elif success_count > 0:
        logger.warning(f"⚠ Partial success: downloaded {success_count}/{total_count} files ({failed_count} failures)")
    else:
        logger.error(f"✗ Failed to download all {total_count} files")

    return successful_downloads


def _bytes_from_repo_files(model_info: Any) -> int | None:
    logger.debug("Attempting to get size from repo files (model weights)")
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
    logger.debug(f"Found {len(siblings) if siblings else 0} siblings in repo")

    # Separate files into two groups: WITH size metadata and WITHOUT
    files_with_size = []  # (filename, size) tuples
    files_without_size = []  # filenames only
    any_weight_files = False

    for sibling in siblings or []:
        rfilename = getattr(sibling, "rfilename", "")
        if not isinstance(rfilename, str):
            continue
        if not rfilename.endswith(weight_exts):
            continue

        any_weight_files = True
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            files_with_size.append((rfilename, size))
            logger.debug(f"  {rfilename}: {size} bytes (from metadata)")
        else:
            files_without_size.append(rfilename)

    if not any_weight_files:
        logger.debug("No weight files found in repo")
        return None

    # Sum files with known sizes
    total_bytes = sum(size for _, size in files_with_size)
    logger.debug(f"Files with metadata: {len(files_with_size)} files = {total_bytes} bytes")

    # Download files without size metadata concurrently
    if files_without_size:
        logger.debug(f"Files without metadata: {len(files_without_size)} files need download")
        downloaded_sizes = _download_files_concurrently(
            model_info.id,
            files_without_size,
            model_info.sha
        )

        # Add successful downloads to total (partial results supported)
        download_bytes = sum(downloaded_sizes.values())
        total_bytes += download_bytes
        logger.debug(f"Downloaded files contributed: {download_bytes} bytes")

    total_files = len(files_with_size) + len(files_without_size)
    logger.info(f"Repo files total: {total_files} weight files = {total_bytes} bytes")

    return total_bytes if total_bytes > 0 else None


def _bytes_from_dataset(info: Any) -> int | None:
    logger.debug("Attempting to get size from dataset files")
    # Prefer explicit files metadata if present (added by helper)
    files_meta = getattr(info, "files", None)
    if isinstance(files_meta, list) and files_meta:
        logger.debug(f"Found explicit files metadata with {len(files_meta)} entries")
        total = 0
        for entry in files_meta:
            try:
                size_val = int(entry.get("size", 0)) if isinstance(entry, dict) else 0
            except Exception:
                size_val = 0
            total += size_val
        if total > 0:
            logger.debug(f"Total bytes from files metadata: {total}")
            return total
        logger.debug("Files metadata present but total size is 0")

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

    siblings = getattr(info, "siblings", [])
    logger.debug(f"Checking {len(siblings) if siblings else 0} siblings for dataset files")
    total_bytes = 0
    any_found = False
    data_files_found = []

    for sibling in siblings or []:
        rfilename = getattr(sibling, "rfilename", "")
        if not isinstance(rfilename, str) or not rfilename:
            continue
        # Skip trivial metadata files
        if rfilename in {".gitattributes", "README.md", "LICENSE"}:
            continue
        if not rfilename.lower().endswith(data_exts):
            continue
        any_found = True
        data_files_found.append(rfilename)
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total_bytes += size
            logger.debug(f"  {rfilename}: {size} bytes")
            continue
        lfs = getattr(sibling, "lfs", None)
        lfs_size = getattr(lfs, "size", None) if lfs is not None else None
        if isinstance(lfs_size, int):
            total_bytes += lfs_size
            logger.debug(f"  {rfilename}: {lfs_size} bytes (from LFS)")
        else:
            logger.debug(f"  {rfilename}: no size info available")

    if not any_found:
        logger.debug("No dataset files found in repo")
        return None
    logger.debug(f"Found {len(data_files_found)} data files, total: {total_bytes} bytes")
    return total_bytes if total_bytes > 0 else None


def _bytes_from_space(info: Any) -> int | None:
    logger.debug("Attempting to get size from space (runtime storage)")
    # Prefer runtime storage metrics if present
    runtime = getattr(info, "runtime", None)
    storage = getattr(runtime, "storage", None) if runtime is not None else None
    if isinstance(storage, dict):
        current = storage.get("current")
        requested = storage.get("requested")
        logger.debug(f"Runtime storage: current={current}, requested={requested}")
        if isinstance(current, (int, float)) and current:
            logger.debug(f"Using current storage: {int(current)} bytes")
            return int(current)
        if isinstance(requested, (int, float)) and requested:
            logger.debug(f"Using requested storage: {int(requested)} bytes")
            return int(requested)
    else:
        logger.debug("No runtime storage info found")

    # Fallback: sum sizes from siblings, including LFS pointers
    siblings = getattr(info, "siblings", [])
    logger.debug(f"Fallback: checking {len(siblings) if siblings else 0} siblings")
    total_bytes = 0
    any_found = False
    for sibling in siblings or []:
        any_found = True
        rfilename = getattr(sibling, "rfilename", "")
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total_bytes += size
            logger.debug(f"  {rfilename}: {size} bytes")
            continue
        lfs = getattr(sibling, "lfs", None)
        lfs_size = getattr(lfs, "size", None) if lfs is not None else None
        if isinstance(lfs_size, int):
            total_bytes += lfs_size
            logger.debug(f"  {rfilename}: {lfs_size} bytes (from LFS)")

    if not any_found:
        logger.debug("No files found in space")
        return None
    logger.debug(f"Total bytes from space files: {total_bytes}")
    return total_bytes if total_bytes > 0 else None


def compute_size_metric(model_info: Any) -> dict:
    model_id = getattr(model_info, "id", "unknown")
    logger.info(f"========== Computing size metric for {model_id} ==========")

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
        logger.info("Detected as a Space (has runtime attribute)")
        total_bytes = _bytes_from_space(model_info)
        if total_bytes:
            logger.info(f"✓ Space detection successful: {total_bytes} bytes")
        else:
            logger.warning("✗ Space detection failed to get size")

    # Models: try safetensors parameters first, then repo files, then dataset
    if total_bytes is None:
        # Try safetensors parameter-based estimate if available
        if getattr(model_info, "safetensors", None) is not None:
            logger.info("Detected safetensors metadata, trying parameter-based size")
            total_bytes = _bytes_from_safetensors_params(model_info)
            if total_bytes:
                logger.info(f"✓ Safetensors params successful: {total_bytes} bytes")
            else:
                logger.warning("✗ Safetensors params failed")

        # Always try repo files if we haven't found a size yet
        if total_bytes is None:
            logger.info("Trying to get size from repository files")
            total_bytes = _bytes_from_repo_files(model_info)
            if total_bytes:
                logger.info(f"✓ Repo files successful: {total_bytes} bytes")
            else:
                logger.warning("✗ Repo files failed")

        # Fallback to dataset detection
        if total_bytes is None:
            logger.info("Trying dataset detection as final fallback")
            total_bytes = _bytes_from_dataset(model_info)
            if total_bytes:
                logger.info(f"✓ Dataset detection successful: {total_bytes} bytes")
            else:
                logger.warning("✗ Dataset detection failed")

    # If we still cannot determine size, return zeros
    if total_bytes is None or total_bytes <= 0:
        import sys
        logger.error(f"FAILED to determine size for {model_id} - returning all zeros")
        logger.error("This likely means:")
        logger.error("  - No recognized file types were found in the repo")
        logger.error("  - File size metadata was missing or zero")
        logger.error("  - The artifact type wasn't properly detected")

        # Also print to stderr for visibility during testing
        print(f"[SIZE METRIC] WARNING: Zero size returned for {model_id}", file=sys.stderr)
        return {device: 0.0 for device in device_capacity_gb}

    total_gb = total_bytes / (1024**3)
    logger.info(f"Final size: {total_bytes:,} bytes = {total_gb:.4f} GB")

    # Score = max(0, 1 - (size / capacity)) per device
    scores: Dict[str, float] = {}
    for device, capacity_gb in device_capacity_gb.items():
        raw_score = 1.0 - (total_gb / capacity_gb)
        scores[device] = round(max(0.0, raw_score), 4)
        logger.debug(f"  {device}: {scores[device]} (capacity: {capacity_gb} GB)")

    logger.info(f"Scores: {scores}")
    logger.info(f"========== End size metric for {model_id} ==========\n")
    return scores


# test cases
if __name__ == "__main__":
    # Configure logging for local testing
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)s [%(name)s] %(message)s'
    )

    print("\n" + "="*80)
    print("Testing size metric computation")
    print("="*80 + "\n")

    # Test with a model
    info = pull_model_info("https://huggingface.co/google/gemma-3-270m")
    result = compute_size_metric(info)
    print(f"\n>>> google/gemma-3-270m: {result}\n")

    # Test with a dataset
    info = pull_model_info("https://huggingface.co/datasets/xlangai/AgentNet")
    result = compute_size_metric(info)
    print(f"\n>>> datasets/xlangai/AgentNet: {result}\n")

    # Test with a space
    info = pull_model_info("https://huggingface.co/spaces/gradio/hello_world")
    result = compute_size_metric(info)
    print(f"\n>>> spaces/gradio/hello_world: {result}\n")
