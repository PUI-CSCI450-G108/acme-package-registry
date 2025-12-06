"""Tests for update_artifact Lambda handler."""

import json
import pytest
from types import SimpleNamespace

from src.auth.exceptions import AuthError, InvalidTokenError


# Mock classes for testing
class MockUser:
    """Mock user object for testing."""
    def __init__(self, username, can_upload=True, can_search=True, can_download=True, is_admin=False):
        self.username = username
        self.can_upload = can_upload
        self.can_search = can_search
        self.can_download = can_download
        self.is_admin = is_admin


class MockPayload:
    """Mock JWT payload for testing."""
    def __init__(self, sub, jti):
        self.sub = sub
        self.jti = jti


class MockAuthService:
    """Mock authentication service for testing."""
    def authenticate_token(self, token):
        # Strip "bearer " prefix if present
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:]

        if token == "valid-admin-token":
            user = MockUser(username="admin", can_upload=True, is_admin=True)
            payload = MockPayload(sub="admin", jti="token-123")
            return payload, user
        elif token == "valid-readonly-token":
            user = MockUser(username="readonly", can_upload=False)
            payload = MockPayload(sub="readonly", jti="token-456")
            return payload, user
        elif token == "expired-token":
            raise InvalidTokenError("Token expired")
        else:
            raise InvalidTokenError("Invalid token")


# Fixtures
@pytest.fixture
def mock_auth_service(monkeypatch):
    """Mock authentication service."""
    service = MockAuthService()
    monkeypatch.setattr(
        "lambda_handlers.update_artifact.get_default_auth_service",
        lambda: service
    )
    return service


@pytest.fixture
def mock_s3_operations(monkeypatch):
    """Mock S3 operations with in-memory storage."""
    stored_artifacts = {}

    def mock_load(artifact_id):
        return stored_artifacts.get(artifact_id)

    def mock_save(artifact_id, data):
        stored_artifacts[artifact_id] = data

    monkeypatch.setattr(
        "lambda_handlers.update_artifact.load_artifact_from_s3",
        mock_load
    )
    monkeypatch.setattr(
        "lambda_handlers.update_artifact.save_artifact_to_s3",
        mock_save
    )

    return stored_artifacts


@pytest.fixture
def mock_evaluate_model(monkeypatch):
    """Mock model evaluation that returns passing score."""
    def mock_eval(url, artifact_store=None):
        return {
            "net_score": 0.75,
            "name": "test-model",
            "ramp_up_time": 0.5,
            "ramp_up_time_latency": 1.2,
            "bus_factor": 0.8,
            "bus_factor_latency": 0.5,
            "performance_claims": 0.7,
            "performance_claims_latency": 0.3,
            "license": 1.0,
            "license_latency": 0.1,
            "dataset_and_code_score": 0.6,
            "dataset_and_code_score_latency": 0.4,
            "dataset_quality": 0.7,
            "dataset_quality_latency": 0.2,
            "code_quality": 0.6,
            "code_quality_latency": 0.3,
            "reproducibility": 0.5,
            "reproducibility_latency": 0.4,
            "reviewedness": 0.6,
            "reviewedness_latency": 0.5,
            "tree_score": 0.8,
            "tree_score_latency": 0.2,
            "size_score": {
                "raspberry_pi": 0.3,
                "jetson_nano": 0.5,
                "desktop_pc": 0.8,
                "aws_server": 1.0
            },
            "size_score_latency": 0.1,
            "net_score_latency": 0.05,
        }
    monkeypatch.setattr(
        "lambda_handlers.update_artifact.evaluate_model",
        mock_eval
    )


@pytest.fixture
def mock_evaluate_model_low_score(monkeypatch):
    """Mock model evaluation that returns failing score."""
    def mock_eval(url, artifact_store=None):
        return {
            "net_score": 0.3,  # Below 0.5 threshold
            "name": "low-quality-model",
            "ramp_up_time": 0.2,
            "ramp_up_time_latency": 1.0,
            "bus_factor": 0.1,
            "bus_factor_latency": 0.5,
            "performance_claims": 0.3,
            "performance_claims_latency": 0.3,
            "license": 1.0,
            "license_latency": 0.1,
            "dataset_and_code_score": 0.2,
            "dataset_and_code_score_latency": 0.4,
            "dataset_quality": 0.3,
            "dataset_quality_latency": 0.2,
            "code_quality": 0.2,
            "code_quality_latency": 0.3,
            "reproducibility": 0.2,
            "reproducibility_latency": 0.4,
            "reviewedness": 0.3,
            "reviewedness_latency": 0.5,
            "tree_score": 0.4,
            "tree_score_latency": 0.2,
            "size_score": {
                "raspberry_pi": 0.1,
                "jetson_nano": 0.2,
                "desktop_pc": 0.4,
                "aws_server": 0.6
            },
            "size_score_latency": 0.1,
            "net_score_latency": 0.05,
        }
    monkeypatch.setattr(
        "lambda_handlers.update_artifact.evaluate_model",
        mock_eval
    )


@pytest.fixture
def mock_is_valid_url(monkeypatch):
    """Mock URL validation (default: all valid)."""
    monkeypatch.setattr(
        "lambda_handlers.update_artifact.is_valid_artifact_url",
        lambda url, artifact_type: True
    )


# Happy Path Tests
def test_update_model_success(mock_auth_service, mock_s3_operations, mock_evaluate_model, mock_is_valid_url):
    """Test successful model update with re-evaluation."""
    # Setup existing artifact
    artifact_id = "test-model-id"
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/old/model",
        "metadata": {"name": "old-model", "id": artifact_id, "type": "model"},
        "rating": {"net_score": 0.6},
        "type": "model"
    }

    # Create update event
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://huggingface.co/new/model"})
    }

    # Execute handler
    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["url"] == "https://huggingface.co/new/model"
    assert body["metadata"]["name"] == "old-model"  # Name preserved
    assert body["metadata"]["id"] == artifact_id
    assert body["metadata"]["type"] == "model"

    # Verify S3 update
    updated = mock_s3_operations[artifact_id]
    assert updated["url"] == "https://huggingface.co/new/model"
    assert updated["rating"]["net_score"] == 0.75  # Re-evaluated
    assert updated["metadata"]["name"] == "old-model"


def test_update_dataset_success(mock_auth_service, mock_s3_operations, mock_is_valid_url):
    """Test successful dataset update without re-evaluation."""
    # Setup existing dataset
    artifact_id = "test-dataset-id"
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/datasets/old/dataset",
        "metadata": {"name": "old-dataset", "id": artifact_id, "type": "dataset"},
        "rating": None,
        "type": "dataset"
    }

    # Create update event
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "dataset", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://huggingface.co/datasets/new/dataset"})
    }

    # Execute handler
    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["url"] == "https://huggingface.co/datasets/new/dataset"
    assert body["metadata"]["name"] == "old-dataset"  # Name preserved

    # Verify S3 update (no rating change)
    updated = mock_s3_operations[artifact_id]
    assert updated["url"] == "https://huggingface.co/datasets/new/dataset"
    assert updated["rating"] is None


def test_update_code_success(mock_auth_service, mock_s3_operations, mock_is_valid_url):
    """Test successful code artifact update."""
    # Setup existing code artifact
    artifact_id = "test-code-id"
    mock_s3_operations[artifact_id] = {
        "url": "https://github.com/old/repo",
        "metadata": {"name": "old-repo", "id": artifact_id, "type": "code"},
        "rating": None,
        "type": "code"
    }

    # Create update event
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "code", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://github.com/new/repo"})
    }

    # Execute handler
    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["url"] == "https://github.com/new/repo"
    assert body["metadata"]["name"] == "old-repo"


# Authentication/Authorization Tests
def test_update_missing_token(mock_s3_operations):
    """Test update without authorization token returns 403."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": "test-id"},
        "headers": {},  # No X-Authorization header
        "body": json.dumps({"url": "https://huggingface.co/test/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 403
    body = json.loads(response["body"])
    assert "Authentication failed" in body["error"]


def test_update_invalid_token(mock_auth_service, mock_s3_operations):
    """Test update with invalid token returns 403."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": "test-id"},
        "headers": {"X-Authorization": "invalid-token"},
        "body": json.dumps({"url": "https://huggingface.co/test/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 403
    body = json.loads(response["body"])
    assert "Authentication failed" in body["error"]


def test_update_insufficient_permissions(mock_auth_service, mock_s3_operations):
    """Test update with can_upload=False returns 403."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": "test-id"},
        "headers": {"X-Authorization": "valid-readonly-token"},
        "body": json.dumps({"url": "https://huggingface.co/test/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 403
    body = json.loads(response["body"])
    assert "Authentication failed" in body["error"]


def test_update_expired_token(mock_auth_service, mock_s3_operations):
    """Test update with expired token returns 403."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": "test-id"},
        "headers": {"X-Authorization": "expired-token"},
        "body": json.dumps({"url": "https://huggingface.co/test/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 403


# Validation Tests
def test_update_missing_artifact_id(mock_auth_service):
    """Test update without artifact ID returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model"},  # Missing 'id'
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://huggingface.co/test/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "missing field" in body["error"].lower()


def test_update_invalid_artifact_type(mock_auth_service):
    """Test update with invalid artifact type returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "invalid_type", "id": "test-id"},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://huggingface.co/test/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "artifact_type" in body["error"]


def test_update_missing_url(mock_auth_service, mock_s3_operations):
    """Test update without URL in body returns 400."""
    artifact_id = "test-id"
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/old/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {},
        "type": "model"
    }

    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({})  # Missing URL
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400


def test_update_invalid_url_format(mock_auth_service, mock_s3_operations, monkeypatch):
    """Test update with invalid URL format returns 400."""
    artifact_id = "test-id"
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/old/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {},
        "type": "model"
    }

    # Mock URL validation to return False
    monkeypatch.setattr(
        "lambda_handlers.update_artifact.is_valid_artifact_url",
        lambda url, artifact_type: False
    )

    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "invalid-url"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Invalid URL" in body["error"]


def test_update_artifact_not_found(mock_auth_service, mock_s3_operations, mock_is_valid_url):
    """Test update of non-existent artifact returns 404."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": "nonexistent-id"},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://huggingface.co/test/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert "does not exist" in body["error"]


def test_update_type_mismatch(mock_auth_service, mock_s3_operations, mock_is_valid_url):
    """Test attempting to change artifact type returns 400."""
    artifact_id = "test-id"
    # Store as model
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/old/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {"net_score": 0.7},
        "type": "model"
    }

    # Try to update as dataset
    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "dataset", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://huggingface.co/datasets/test/dataset"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400


# Rating Threshold Tests
def test_update_model_below_threshold(
    mock_auth_service, mock_s3_operations, mock_evaluate_model_low_score, mock_is_valid_url
):
    """Test model update with score below threshold returns 424."""
    artifact_id = "test-model-id"
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/old/model",
        "metadata": {"name": "test-model", "id": artifact_id, "type": "model"},
        "rating": {"net_score": 0.6},
        "type": "model"
    }

    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({"url": "https://huggingface.co/low-quality/model"})
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 424
    body = json.loads(response["body"])
    assert "disqualified rating" in body["error"]
    assert "0.3" in body["error"]  # Low score mentioned


# Edge Cases
def test_update_preserves_name(mock_auth_service, mock_s3_operations, mock_evaluate_model, mock_is_valid_url):
    """Test that update preserves the original artifact name."""
    artifact_id = "test-id"
    original_name = "original-artifact-name"
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/old/model",
        "metadata": {"name": original_name, "id": artifact_id, "type": "model"},
        "rating": {"net_score": 0.6},
        "type": "model"
    }

    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": json.dumps({
            "url": "https://huggingface.co/new/model",
            "name": "attempted-new-name"  # Should be ignored
        })
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    # Name should remain the original, not the one in request
    assert body["metadata"]["name"] == original_name

    updated = mock_s3_operations[artifact_id]
    assert updated["metadata"]["name"] == original_name


def test_update_options_preflight():
    """Test OPTIONS preflight request returns 200."""
    event = {
        "httpMethod": "OPTIONS",
        "pathParameters": {"artifact_type": "model", "id": "test-id"}
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 200


def test_update_malformed_json(mock_auth_service, mock_s3_operations):
    """Test update with malformed JSON body returns 400."""
    artifact_id = "test-id"
    mock_s3_operations[artifact_id] = {
        "url": "https://huggingface.co/old/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {},
        "type": "model"
    }

    event = {
        "httpMethod": "PUT",
        "pathParameters": {"artifact_type": "model", "id": artifact_id},
        "headers": {"X-Authorization": "valid-admin-token"},
        "body": "{ invalid json }"
    }

    from lambda_handlers.update_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400
