"""
AWS Lambda handlers for the ACME Package Registry API.

These handlers process API Gateway events directly without FastAPI/Mangum.
"""

import os
import json
import logging
import hashlib
import uuid
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

# In-memory storage (in production, use DynamoDB or S3)
# Note: Lambda containers are reused, so this persists across invocations
ARTIFACTS_DB: Dict[str, dict] = {}

MIN_NET_SCORE_THRESHOLD = float(os.getenv("MIN_NET_SCORE", "0.5"))


# --- Helper Functions ---

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


# --- Lambda Handlers ---

def create_artifact(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for POST /artifact/{artifact_type}

    Registers a new artifact and evaluates it.

    API Gateway Event Structure:
    - event['pathParameters']['artifact_type'] - model/dataset/code
    - event['body'] - JSON string with {"url": "..."}
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    try:
        logger.info(f"create_artifact invoked: {json.dumps(event)}")

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_response(200, {})

        # Parse path parameter
        artifact_type = event.get('pathParameters', {}).get('artifact_type')
        if not artifact_type or artifact_type not in ['model', 'dataset', 'code']:
            return create_response(400, {
                "error": "Invalid artifact_type. Must be model, dataset, or code."
            })

        # Parse request body
        body_str = event.get('body', '{}')
        try:
            body = json.loads(body_str) if isinstance(body_str, str) else body_str
        except json.JSONDecodeError:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
            })

        url = body.get('url', '').strip()
        if not url:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
            })

        # Generate artifact ID (deterministic UUID based on type+URL)
        artifact_id = generate_artifact_id(artifact_type, url)

        # Check if already exists
        if artifact_id in ARTIFACTS_DB:
            return create_response(409, {"error": "Artifact exists already."})

        # Evaluate the artifact (only models supported for now)
        if artifact_type == 'model':
            try:
                rating = evaluate_model(url)

                # Check if rating is acceptable
                if rating.get("net_score", 0) < MIN_NET_SCORE_THRESHOLD:
                    return create_response(424, {
                        "error": f"Artifact is not registered due to the disqualified rating (net_score={rating.get('net_score', 0):.2f} < {MIN_NET_SCORE_THRESHOLD})."
                    })

                name = rating.get("name", "unknown")
            except Exception as e:
                logger.error(f"Error evaluating artifact: {e}", exc_info=True)
                return create_response(500, {
                    "error": f"Error evaluating artifact: {str(e)}"
                })
        else:
            # For dataset/code, just extract name from URL
            name = url.split("/")[-1] if "/" in url else "unknown"
            rating = None

        # Create artifact metadata
        metadata = {
            "name": name,
            "version": "1.0.0",
            "id": artifact_id,
            "type": artifact_type
        }

        # Store artifact
        ARTIFACTS_DB[artifact_id] = {
            "url": url,
            "metadata": metadata,
            "rating": rating,
            "type": artifact_type
        }

        logger.info(f"Registered artifact {artifact_id}: {name}")

        # Return artifact envelope
        return create_response(201, {
            "metadata": metadata,
            "data": {"url": url}
        })

    except Exception as e:
        logger.error(f"Unexpected error in create_artifact: {e}", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(e)}"})


def rate_artifact(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /artifact/model/{id}/rate

    Returns the rating for a registered model artifact.

    API Gateway Event Structure:
    - event['pathParameters']['id'] - Artifact ID
    - event['headers']['X-Authorization'] - Auth token (optional)
    """
    try:
        logger.info(f"rate_artifact invoked: {json.dumps(event)}")

        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_response(200, {})

        # Parse path parameter
        artifact_id = event.get('pathParameters', {}).get('id')
        if not artifact_id:
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Validate ID format
        if not artifact_id.replace("-", "").replace("_", "").isalnum():
            return create_response(400, {
                "error": "There is missing field(s) in the artifact_id or it is formed improperly, or is invalid."
            })

        # Check if artifact exists
        if artifact_id not in ARTIFACTS_DB:
            return create_response(404, {"error": "Artifact does not exist."})

        artifact = ARTIFACTS_DB[artifact_id]

        # Verify it's a model
        if artifact.get("type") != "model":
            return create_response(400, {
                "error": f"Artifact {artifact_id} is not a model"
            })

        # Get cached rating or re-evaluate
        rating = artifact.get("rating")
        if not rating:
            url = artifact.get("url")
            try:
                rating = evaluate_model(url)
                ARTIFACTS_DB[artifact_id]["rating"] = rating
            except Exception as e:
                logger.error(f"Error evaluating artifact {artifact_id}: {e}", exc_info=True)
                return create_response(500, {
                    "error": "The artifact rating system encountered an error while computing at least one metric."
                })

        logger.info(f"Returning rating for artifact {artifact_id}")
        return create_response(200, rating)

    except Exception as e:
        logger.error(f"Unexpected error in rate_artifact: {e}", exc_info=True)
        return create_response(500, {"error": f"Internal server error: {str(e)}"})


def health_check(event: Dict[str, Any], context: Any) -> Dict:
    """
    Lambda handler for GET /health

    Simple health check endpoint.
    """
    return create_response(200, {
        "status": "healthy",
        "service": "acme-package-registry",
        "artifacts_count": len(ARTIFACTS_DB)
    })


# --- For local testing ---
if __name__ == "__main__":
    # Test create_artifact
    test_create_event = {
        "httpMethod": "POST",
        "pathParameters": {"artifact_type": "model"},
        "body": json.dumps({"url": "https://huggingface.co/gpt2"}),
        "headers": {}
    }

    print("Testing create_artifact...")
    response = create_artifact(test_create_event, None)
    print(json.dumps(response, indent=2))

    if response['statusCode'] == 201:
        result = json.loads(response['body'])
        artifact_id = result['metadata']['id']

        # Test rate_artifact
        test_rate_event = {
            "httpMethod": "GET",
            "pathParameters": {"id": artifact_id},
            "headers": {}
        }

        print("\nTesting rate_artifact...")
        response = rate_artifact(test_rate_event, None)
        print(json.dumps(response, indent=2))
