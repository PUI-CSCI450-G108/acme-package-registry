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
from typing import Dict, Any, Optional

# Setup environment
os.environ.setdefault("GIT_LFS_SKIP_SMUDGE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

if not os.getenv("HF_TOKEN") and os.getenv("HF_API_TOKEN"):
    os.environ["HF_TOKEN"] = os.environ["HF_API_TOKEN"]

if os.getenv("HF_TOKEN") and not os.getenv("HUGGINGFACE_HUB_TOKEN"):
    os.environ["HUGGINGFACE_HUB_TOKEN"] = os.getenv("HF_TOKEN")

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
        logger.warning("S3 not configured, skipping save")
        return

    key = f"artifacts/{artifact_id}.json"
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(artifact_data),
        ContentType="application/json"
    )
    logger.info(f"Saved artifact {artifact_id} to S3")


def load_artifact_from_s3(artifact_id: str) -> Optional[dict]:
    """Load artifact data from S3."""
    if not s3_client or not BUCKET_NAME:
        logger.warning("S3 not configured, cannot load")
        return None

    key = f"artifacts/{artifact_id}.json"
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return data
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return None
        logger.error(f"Error loading artifact {artifact_id} from S3: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading artifact {artifact_id} from S3: {e}")
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
        logger.error(f"Error checking artifact {artifact_id} existence in S3: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking artifact {artifact_id} in S3: {e}")
        return False


def list_all_artifacts_from_s3() -> Dict[str, dict]:
    """List all artifacts from S3 (for byName search)."""
    if not s3_client or not BUCKET_NAME:
        logger.warning("S3 not configured, returning empty list")
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
                        logger.error(f"Error loading artifact {artifact_id} from S3: {e}")
                    except Exception as e:
                        logger.error(f"Error loading artifact {artifact_id} from S3: {e}")

        return artifacts
    except Exception as e:
        logger.error(f"Error listing artifacts from S3: {e}")
        return {}


# --- Response Helpers ---

def create_response(status_code: int, body: Any, headers: Optional[Dict] = None) -> Dict:
    """Create an API Gateway response."""
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
    }

    if headers:
        default_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body) if not isinstance(body, str) else body
    }


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


def evaluate_model(url: str) -> dict:
    """Evaluate a model and return rating dict."""
    logger.info(f"Evaluating model: {url}")

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
