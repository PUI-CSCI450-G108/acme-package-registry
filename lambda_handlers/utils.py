"""
Shared utility functions for Lambda handlers.

Includes S3 operations, response formatting, and model evaluation helpers.
"""
import os
import json
import logging
import re
import boto3
import shutil
from io import BytesIO
import zipfile
from huggingface_hub import snapshot_download
from huggingface_hub.errors import GatedRepoError
from httpx import HTTPStatusError
import fnmatch
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional, Iterable, List, Union
from src.artifact_store import S3ArtifactStore
# Setup environment
os.environ.setdefault("GIT_LFS_SKIP_SMUDGE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

if not os.getenv("HF_TOKEN") and os.getenv("HF_API_TOKEN"):
    os.environ["HF_TOKEN"] = os.environ["HF_API_TOKEN"]

if os.getenv("HF_TOKEN") and not os.getenv("HUGGINGFACE_HUB_TOKEN"):
    os.environ["HUGGINGFACE_HUB_TOKEN"] = os.getenv("HF_TOKEN")

def _configure_logger() -> logging.Logger:
    """Initialize a dedicated Lambda logger shipping to CloudWatch."""

    level_name = os.getenv("LAMBDA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log = logging.getLogger("acme_lambda")
    log.setLevel(level)
    log.propagate = False  # avoid duplicate entries if root already streams

    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        handler.setLevel(level)
        log.addHandler(handler)
    else:
        for handler in log.handlers:
            handler.setLevel(level)

    return log


# Setup logging for CloudWatch
logger = _configure_logger()
LogLevel = Union[int, str]


def get_header(event: Dict[str, Any], name: str) -> Optional[str]:
    """Retrieve a header value from the API Gateway event, case-insensitively."""

    headers = event.get("headers") or {}
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def log_event(
    level: LogLevel,
    message: str,
    *,
    event: Optional[Dict[str, Any]] = None,
    context: Optional[Any] = None,
    model_id: Optional[str] = None,
    latency: Optional[float] = None,
    status: Optional[int] = None,
    error_code: Optional[str] = None,
    exc_info: Any = None,
    **kwargs: Any,
) -> None:
    """Log a structured event enriched with Lambda request metadata."""

    if isinstance(level, str):
        level_upper = level.upper()
        if not hasattr(logging, level_upper):
            raise ValueError(f"Invalid log level: {level!r}")
        level_value = getattr(logging, level_upper)
    else:
        level_value = level

    request_context = event.get("requestContext", {}) if isinstance(event, dict) else {}

    request_id = None
    if context is not None:
        request_id = getattr(context, "aws_request_id", None)
    if not request_id:
        request_id = request_context.get("requestId")

    user = None
    if request_context:
        identity = request_context.get("identity", {})
        authorizer = request_context.get("authorizer", {})
        http_context = request_context.get("http", {})
        user = (
            authorizer.get("principalId")
            or identity.get("userArn")
            or identity.get("user")
            or http_context.get("user")
            or request_context.get("accountId")
        )

    endpoint = None
    if request_context:
        http_context = request_context.get("http", {})
        endpoint = (
            request_context.get("resourcePath")
            or request_context.get("path")
            or http_context.get("path")
            or request_context.get("resource")
        )

    extra = {
        "request_id": request_id,
        "user": user,
        "model_id": model_id,
        "endpoint": endpoint,
        "latency": latency,
        "status": status,
        "error_code": error_code,
    }

    log_kwargs = dict(kwargs)
    if "extra" in log_kwargs:
        user_extra = log_kwargs.pop("extra")
        if not isinstance(user_extra, dict):
            raise TypeError("The 'extra' argument passed to log_event must be a dict.")
        # Merge user-provided extra with our extra; function's extra takes precedence
        merged_extra = {**user_extra, **extra}
        log_kwargs["extra"] = merged_extra
    else:
        log_kwargs["extra"] = extra
    if exc_info:
        log_kwargs["exc_info"] = exc_info

    logger.log(level_value, message, **log_kwargs)

# S3 storage for artifacts
BUCKET_NAME = os.getenv("ARTIFACTS_BUCKET")

s3_client = boto3.client("s3") if BUCKET_NAME else None

MIN_NET_SCORE_THRESHOLD = float(os.getenv("MIN_NET_SCORE", "0.5"))

# Files essential to clone/use a model locally
ESSENTIAL_PATTERNS: List[str] = [
    "*.json",
    "*.bin",
    "*.safetensors",
    "tokenizer.json",
    "config.json",
    "pytorch_model.bin",
    "model.safetensors",
    "vocab.txt",
    "merges.txt",
    "special_tokens_map.json",
]

def is_essential_file(relative_path: str) -> bool:
    """Return True if the file should be kept and uploaded to S3."""
    filename = os.path.basename(relative_path)
    for pattern in ESSENTIAL_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False

def upload_hf_files_to_s3(artifact_id: str, hf_url: str) -> Optional[str]:
    """
    Download a Hugging Face snapshot, zip it, upload to S3 as
    artifacts/{artifact_id}/data.zip, and clean up local files and buffers.

    Returns the S3 key on success, or None on failure.
    """
    if not s3_client or not BUCKET_NAME:
        log_event(
            "warning",
            "S3 not configured; cannot upload data.zip",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="s3_not_configured",
        )
        return None

    # Always create a simple placeholder zip first so downloads work even if snapshot fails
    try:
        store_simple_zip(artifact_id, hf_url)
    except Exception:
        log_event(
            "warning",
            f"Failed to store simple placeholder zip for {artifact_id}",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="simple_zip_store_failed",
            exc_info=True,
        )

    try:
        if not hf_url.startswith("https://huggingface.co/"):
            log_event(
                "warning",
                "Non-HuggingFace URL provided to upload_file_to_s3; skipping",
                event=None,
                context=None,
                model_id=artifact_id,
                error_code="invalid_hf_url",
            )
            return None

        repo_id = hf_url.replace("https://huggingface.co/", "")
        if "/tree/" in repo_id:
            repo_id = repo_id.split("/tree/")[0]

        repo_type = "dataset" if "/datasets/" in hf_url else "model"
        hf_token = os.getenv("HF_TOKEN")

        log_event(
            "info",
            f"Downloading HF snapshot {repo_type}:{repo_id} (auth={'yes' if hf_token else 'no'})",
            event=None,
            context=None,
            model_id=artifact_id,
        )

        # Constrain snapshot to essential files to reduce /tmp usage
        allow_patterns = ESSENTIAL_PATTERNS
        ignore_patterns = ["*.md", "*.txt", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg", "*.psd", "*.pptx", "*.xlsx", "*.csv", "*.parquet", "*.tar", "*.zip", "*.7z", "*.rar"]
        # Force cache under /tmp to avoid writing elsewhere
        os.environ.setdefault("HF_HOME", "/tmp/hf-home")
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", "/tmp/hf-cache")

        try:
            local_dir = snapshot_download(
                repo_id=repo_id,
                repo_type=repo_type,
                token=hf_token,
                allow_patterns=allow_patterns,
                ignore_patterns=ignore_patterns,
            )
        except GatedRepoError as e:
            log_event(
                "warning",
                f"Gated HF repo {repo_id}; aborting snapshot after first failure",
                event=None,
                context=None,
                error_code="gated_repo",
            )
            return None
        except HTTPStatusError as e:
            status = e.response.status_code
            if status == 403:
                log_event(
                    "warning",
                    f"HTTP 403 on HF repo {repo_id}; aborting snapshot",
                    event=None,
                    context=None,
                    error_code="gated_repo",
                )
                return None
            raise

        zip_key = f"artifacts/{artifact_id}/data.zip"
        buffer = BytesIO()
        try:
            with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(local_dir):
                    for fname in files:
                        file_path = os.path.join(root, fname)
                        arcname = os.path.relpath(file_path, start=local_dir)
                        if is_essential_file(arcname):
                            zf.write(file_path, arcname)
                zf.writestr("data.txt", f"artifact_id={artifact_id}\nrepo_id={repo_id}\nrepo_type={repo_type}\n")
            buffer.seek(0)

            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=zip_key,
                Body=buffer.read(),
                ContentType="application/zip",
            )
            log_event(
                "info",
                f"Uploaded snapshot data.zip to s3://{BUCKET_NAME}/{zip_key} (overwrote placeholder)",
                event=None,
                context=None,
                model_id=artifact_id,
            )
            return zip_key
        finally:
            try:
                buffer.close()
            except Exception:
                pass
            try:
                shutil.rmtree(local_dir, ignore_errors=True)
            except Exception:
                pass
    except Exception as e:
        log_event(
            "error",
            f"upload_hf_files_to_s3 failed for {artifact_id}: {e}",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="hf_snapshot_zip_upload_error",
            exc_info=True,
        )
        return None

def store_simple_zip(artifact_id: str, hf_url: str) -> None:
    """Download a Hugging Face snapshot and store it as a simple zip in S3."""
    try:
        zip_key = f"artifacts/{artifact_id}/data.zip"
        if not BUCKET_NAME:
            log_event(
                "warning",
                "ARTIFACTS_BUCKET env var not set; skipping data.zip storage",
                event=None,
                context=None,
                model_id=artifact_id,
                error_code="missing_bucket_env",
            )
        elif not s3_client:
            log_event(
                "warning",
                "S3 client not initialized; skipping data.zip storage",
                event=None,
                context=None,
                model_id=artifact_id,
                error_code="missing_s3_client",
            )
        else:
            log_event(
                "info",
                f"Preparing data.zip for {artifact_id} to store at s3://{BUCKET_NAME}/{zip_key}",
                event=None,
                context=None,
                model_id=artifact_id,
            )
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("data.txt", f"artifact_id={artifact_id}\n")
            buffer.seek(0)
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=zip_key,
                Body=buffer.read(),
                ContentType="application/zip"
            )
            log_event(
                "info",
                f"Stored data.zip at s3://{BUCKET_NAME}/{zip_key}",
                event=None,
                context=None,
                model_id=artifact_id,
            )
    except Exception as e:
        log_event(
            "warning",
            f"Failed to create/store data.zip for {artifact_id} at s3://{BUCKET_NAME}/{zip_key}: {e}",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="zip_store_failed",
        )

def save_artifact_to_s3(artifact_id: str, artifact_data: dict) -> None:
    """Save artifact data to S3 as JSON."""
    if not s3_client or not BUCKET_NAME:
        log_event(
            "warning",
            "S3 not configured, skipping save",
            event=None,
            context=None,
        )
        return

    key = f"artifacts/{artifact_id}.json"
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(artifact_data),
        ContentType="application/json"
    )
    log_event(
        "info",
        f"Saved artifact {artifact_id} to S3",
        event=None,
        context=None,
        model_id=artifact_id,
    )


def load_artifact_from_s3(artifact_id: str) -> Optional[dict]:
    """Load artifact data from S3."""
    if not s3_client or not BUCKET_NAME:
        log_event(
            "warning",
            "S3 not configured, cannot load",
            event=None,
            context=None,
        )
        return None

    key = f"artifacts/{artifact_id}.json"
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return data
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return None
        log_event(
            "error",
            f"Error loading artifact {artifact_id} from S3: {e}",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="s3_load_failed",
        )
        return None
    except Exception as e:
        log_event(
            "error",
            f"Error loading artifact {artifact_id} from S3: {e}",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="s3_load_failed",
        )
        return None


def artifact_exists_in_s3(artifact_id: str) -> bool:
    """Check if artifact exists in S3."""
    if not s3_client or not BUCKET_NAME:
        return False

    key = f"artifacts/{artifact_id}.json"
    try:
        s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] in ['404', 'NoSuchKey']:
            return False
        log_event(
            "error",
            f"Error checking artifact {artifact_id} existence in S3: {e}",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="s3_head_failed",
        )
        return False
    except Exception as e:
        log_event(
            "error",
            f"Unexpected error checking artifact {artifact_id} in S3: {e}",
            event=None,
            context=None,
            model_id=artifact_id,
            error_code="s3_head_failed",
        )
        return False


def list_all_artifacts_from_s3() -> Dict[str, dict]:
    """List all artifacts from S3 (for byName search)."""
    if not s3_client or not BUCKET_NAME:
        log_event(
            "warning",
            "S3 not configured, returning empty list",
            event=None,
            context=None,
        )
        return {}

    artifacts = {}
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix="artifacts/"):
            if "Contents" not in page:
                continue

            for obj in page["Contents"]:
                key = obj["Key"]
                if key.endswith(".json"):
                    artifact_id = key.replace("artifacts/", "").replace(".json", "")
                    try:
                        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
                        artifact_data = json.loads(response["Body"].read().decode("utf-8"))
                        artifacts[artifact_id] = artifact_data
                    except ClientError as e:
                        if e.response['Error']['Code'] == 'NoSuchKey':
                            continue
                        log_event(
                            "error",
                            f"Error loading artifact {artifact_id} from S3: {e}",
                            event=None,
                            context=None,
                            model_id=artifact_id,
                            error_code="s3_load_failed",
                        )
                    except Exception as e:
                        log_event(
                            "error",
                            f"Error loading artifact {artifact_id} from S3: {e}",
                            event=None,
                            context=None,
                            model_id=artifact_id,
                            error_code="s3_load_failed",
                        )

        return artifacts
    except Exception as e:
        log_event(
            "error",
            f"Error listing artifacts from S3: {e}",
            event=None,
            context=None,
            error_code="s3_list_failed",
        )
        return {}


def _chunked_keys(keys: Iterable[Dict[str, str]], size: int = 1000) -> Iterable[List[Dict[str, str]]]:
    """Yield chunks of S3 object identifiers."""

    chunk: List[Dict[str, str]] = []
    for key in keys:
        chunk.append(key)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def delete_all_artifacts_from_s3() -> int:
    """Delete every stored artifact object from S3.

    Returns the number of deleted artifacts. If S3 is not configured the function
    is a no-op and returns 0.
    """

    if not s3_client or not BUCKET_NAME:
        log_event(
            "warning",
            "S3 not configured, reset skipped",
            event=None,
            context=None,
        )
        return 0

    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        objects_to_delete: List[Dict[str, str]] = []
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix="artifacts/"):
            for obj in page.get("Contents", []):
                objects_to_delete.append({"Key": obj["Key"]})

        delete_count = len(objects_to_delete)
        if not objects_to_delete:
            return 0

        for chunk in _chunked_keys(objects_to_delete, size=1000):
            s3_client.delete_objects(
                Bucket=BUCKET_NAME,
                Delete={"Objects": chunk, "Quiet": True}
            )

        log_event(
            "info",
            f"Deleted {delete_count} artifact object(s) from S3",
            event=None,
            context=None,
        )
        return delete_count
    except ClientError as e:
        log_event(
            "error",
            f"Error resetting artifacts in S3: {e}",
            event=None,
            context=None,
            error_code="s3_reset_failed",
        )
        raise
    except Exception as e:
        log_event(
            "error",
            f"Unexpected error during S3 reset: {e}",
            event=None,
            context=None,
            error_code="s3_reset_failed",
        )
        raise


# --- Response Helpers ---

def create_response(status_code: int, body: Any, headers: Optional[Dict] = None) -> Dict:
    """Create an API Gateway response."""
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
    }

    if headers:
        default_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body) if not isinstance(body, str) else body
    }


def handle_cors_preflight(event: Dict[str, Any]) -> Optional[Dict]:
    """Handle OPTIONS preflight requests for CORS.

    Returns a response dict if this is a preflight request, None otherwise.
    """
    if event.get("httpMethod") == "OPTIONS" or event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return create_response(200, "")
    return None
# --- Model Evaluation Helpers ---

def convert_to_model_rating(ndjson_result: dict) -> dict:
    """Convert orchestrator output to ModelRating format (ms->seconds)."""
    result = ndjson_result.copy()

    # Remove net_score_version field (not part of ModelRating schema per spec)
    result.pop("net_score_version", None)

    # Convert latencies from milliseconds to seconds
    for key in list(result.keys()):
        if key.endswith("_latency"):
            ms_value = result[key]
            result[key] = ms_value / 1000.0 if ms_value > 0 else 0.001

    return result


def extract_base_model_from_model_info(model_info: Any) -> Optional[Any]:
    """
    Extract base_model field from HuggingFace model cardData.

    Returns the base_model value (string, list, or None) for storage in artifact metadata.
    This information is used by the lineage endpoint to build dependency graphs.

    Args:
        model_info: HuggingFace ModelInfo object

    Returns:
        base_model value (str, list, or None)
    """
    try:
        card_data = getattr(model_info, "cardData", None) or {}
        base_model = card_data.get("base_model")

        # Return None for empty strings or empty lists
        if base_model is None:
            return None
        elif isinstance(base_model, str) and not base_model.strip():
            return None
        elif isinstance(base_model, list) and len(base_model) == 0:
            return None
        else:
            return base_model
    except Exception as e:
        logging.debug(f"Failed to extract base_model: {e}")
        return None


def evaluate_model(

    url: str,
    *,
    artifact_store: Optional[S3ArtifactStore] = None,
    event: Optional[Dict[str, Any]] = None,
    context: Optional[Any] = None,
) -> dict:
    """Evaluate a model and return rating dict with base_model metadata."""
    # Lazy import evaluation logic to reduce cold start time for handlers that don't evaluate
    from src.metrics.helpers.pull_model import pull_model_info, canonicalize_hf_url
    from src.orchestrator import calculate_all_metrics

    log_event("info", f"Evaluating model: {url}", event=event, context=context)

    url = canonicalize_hf_url(url) if url.startswith("https://huggingface.co/") else url

    # Fetch and evaluate
    model_info = pull_model_info(url)
    if not model_info:
        raise ValueError("Could not retrieve model information")

    ndjson_output = calculate_all_metrics(model_info, url, artifact_store)
    result = json.loads(ndjson_output)

    # Post-process name
    if result.get("category") == "MODEL":
        name = result.get("name", "")
        if isinstance(name, str) and "/" in name:
            result["name"] = name.split("/")[-1]

    # Ensure latencies > 0
    for k, v in list(result.items()):
        if k.endswith("_latency") and isinstance(v, int) and v <= 0:
            result[k] = 1

    # Extract base_model for lineage tracking (stored separately from rating)
    base_model = extract_base_model_from_model_info(model_info)
    if base_model is not None:
        result["base_model"] = base_model

    return convert_to_model_rating(result)


# --- URL Validation Helpers ---

def is_valid_artifact_url(url: str, artifact_type: str = "model") -> bool:
    """
    Validate that a URL is valid for the artifact type.

    Supported URL patterns:
    - model: https://huggingface.co/<org>/<model_name>[/tree/<branch>]
    - dataset: https://huggingface.co/datasets/<org>/<dataset_name>[/tree/<branch>]
    - code: https://github.com/<owner>/<repo>[/tree/<branch>]

    Args:
        url: The URL to validate
        artifact_type: Type of artifact - "model", "dataset", or "code"

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(url, str):
        return False

    url = url.strip()

    if artifact_type == "model":
        # Model pattern: https://huggingface.co/<org>/<name>[/tree/<branch>]
        if not url.startswith("https://huggingface.co/"):
            return False
        remainder = url.replace("https://huggingface.co/", "")
        # Must not start with "datasets/" and must have org/name format
        if remainder.startswith("datasets/"):
            return False
        pattern = r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.\-]+(/tree/[a-zA-Z0-9_.\-]+)?/?$"
        return bool(re.match(pattern, remainder))

    elif artifact_type == "dataset":
        # Dataset pattern: https://huggingface.co/datasets/<org>/<name>[/tree/<branch>]
        if not url.startswith("https://huggingface.co/datasets/"):
            return False
        remainder = url.replace("https://huggingface.co/datasets/", "")
        pattern = r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.\-]+(/tree/[a-zA-Z0-9_.\-]+)?/?$"
        return bool(re.match(pattern, remainder))

    elif artifact_type == "code":
        # Code pattern: https://github.com/<owner>/<repo>[/tree/<branch>]
        if not url.startswith("https://github.com/"):
            return False
        remainder = url.replace("https://github.com/", "")
        pattern = r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.\-]+(/tree/[a-zA-Z0-9_.\-]+)?/?$"
        return bool(re.match(pattern, remainder))

    return False


