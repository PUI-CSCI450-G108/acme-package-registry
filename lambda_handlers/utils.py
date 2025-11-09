"""
Shared utility functions for Lambda handlers.

Includes S3 operations, response formatting, and model evaluation helpers.
"""

import os
import json
import logging
import uuid
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional, Iterable, List, Union

# Setup environment
os.environ.setdefault("GIT_LFS_SKIP_SMUDGE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

if not os.getenv("HF_TOKEN") and os.getenv("HF_API_TOKEN"):
    os.environ["HF_TOKEN"] = os.environ["HF_API_TOKEN"]

if os.getenv("HF_TOKEN") and not os.getenv("HUGGINGFACE_HUB_TOKEN"):
    os.environ["HUGGINGFACE_HUB_TOKEN"] = os.getenv("HF_TOKEN")

# Setup logging
logger = logging.getLogger()


LogLevel = Union[int, str]


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
        level_value = getattr(logging, level.upper(), logging.INFO)
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
    log_kwargs["extra"] = extra
    if exc_info:
        log_kwargs["exc_info"] = exc_info

    logger.log(level_value, message, **log_kwargs)

# Import evaluation logic
from src.metrics.helpers.pull_model import pull_model_info, canonicalize_hf_url
from src.orchestrator import calculate_all_metrics

# S3 storage for artifacts
BUCKET_NAME = os.getenv("ARTIFACTS_BUCKET")
s3_client = boto3.client("s3") if BUCKET_NAME else None

MIN_NET_SCORE_THRESHOLD = float(os.getenv("MIN_NET_SCORE", "0.5"))


# --- S3 Storage Helpers ---

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

    # Convert latencies from milliseconds to seconds
    for key in list(result.keys()):
        if key.endswith("_latency"):
            ms_value = result[key]
            result[key] = ms_value / 1000.0 if ms_value > 0 else 0.001

    return result


def evaluate_model(
    url: str,
    *,
    event: Optional[Dict[str, Any]] = None,
    context: Optional[Any] = None,
) -> dict:
    """Evaluate a model and return rating dict."""
    log_event("info", f"Evaluating model: {url}", event=event, context=context)

    url = canonicalize_hf_url(url) if url.startswith("https://huggingface.co/") else url

    # Fetch and evaluate
    model_info = pull_model_info(url)
    if not model_info:
        raise ValueError("Could not retrieve model information")

    ndjson_output = calculate_all_metrics(model_info, url)
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

    return convert_to_model_rating(result)


def generate_artifact_id(artifact_type: str, url: str) -> str:
    """Generate a deterministic, low-collision artifact ID.

    Rationale:
    - Previously used MD5 truncated to 12 chars, which increases collision risk.
    - Use UUIDv5 (namespace-based) for deterministic IDs from (type, canonical URL).
    - Hyphenated UUID string is allowed by our ID validator and avoids truncation risks.

    Note: We canonicalize Hugging Face URLs to avoid duplicate IDs for equivalent URLs.
    """
    normalized_url = (
        canonicalize_hf_url(url) if isinstance(url, str) and url.startswith("https://huggingface.co/") else url
    )
    name = f"{artifact_type}:{normalized_url}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))
