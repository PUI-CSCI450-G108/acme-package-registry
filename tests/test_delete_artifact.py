"""Tests for delete_artifact Lambda handler."""

import json
import pytest
from botocore.exceptions import ClientError


# Fixtures
@pytest.fixture
def mock_s3_operations(monkeypatch):
    """Mock S3 operations with in-memory storage."""
    stored_artifacts = {}
    deleted_keys = []

    def mock_load(artifact_id):
        return stored_artifacts.get(artifact_id)

    # Mock boto3.client to return a mock S3 client
    class MockS3Client:
        def delete_object(self, Bucket, Key):
            deleted_keys.append(Key)
            # Simulate successful deletion (S3 doesn't error if key doesn't exist)
            return {}

    def mock_boto3_client(service_name):
        if service_name == "s3":
            return MockS3Client()
        raise ValueError(f"Unexpected service: {service_name}")

    monkeypatch.setattr(
        "lambda_handlers.delete_artifact.load_artifact_from_s3",
        mock_load
    )
    monkeypatch.setattr(
        "lambda_handlers.delete_artifact.boto3.client",
        mock_boto3_client
    )
    monkeypatch.setenv("ARTIFACTS_BUCKET", "test-bucket")

    return {"stored_artifacts": stored_artifacts, "deleted_keys": deleted_keys}


@pytest.fixture
def mock_s3_error(monkeypatch):
    """Mock S3 operations that raise ClientError."""
    stored_artifacts = {}

    def mock_load(artifact_id):
        return stored_artifacts.get(artifact_id)

    class MockS3Client:
        def delete_object(self, Bucket, Key):
            # Simulate S3 error
            error_response = {
                "Error": {
                    "Code": "InternalError",
                    "Message": "Internal server error"
                }
            }
            raise ClientError(error_response, "DeleteObject")

    def mock_boto3_client(service_name):
        if service_name == "s3":
            return MockS3Client()
        raise ValueError(f"Unexpected service: {service_name}")

    monkeypatch.setattr(
        "lambda_handlers.delete_artifact.load_artifact_from_s3",
        mock_load
    )
    monkeypatch.setattr(
        "lambda_handlers.delete_artifact.boto3.client",
        mock_boto3_client
    )
    monkeypatch.setenv("ARTIFACTS_BUCKET", "test-bucket")

    return stored_artifacts


# Happy Path Tests
def test_delete_model_success(mock_s3_operations):
    """Test successful model deletion."""
    # Setup existing artifact
    artifact_id = "test-model-id"
    mock_s3_operations["stored_artifacts"][artifact_id] = {
        "url": "https://huggingface.co/test/model",
        "metadata": {"name": "test-model", "id": artifact_id, "type": "model"},
        "rating": {"net_score": 0.75},
        "type": "model"
    }

    # Create delete event
    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model", "id": artifact_id}
    }

    # Execute handler
    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "deleted" in body["message"].lower()

    # Verify S3 deletion
    expected_key = f"artifacts/{artifact_id}.json"
    assert expected_key in mock_s3_operations["deleted_keys"]


def test_delete_dataset_success(mock_s3_operations):
    """Test successful dataset deletion."""
    artifact_id = "test-dataset-id"
    mock_s3_operations["stored_artifacts"][artifact_id] = {
        "url": "https://huggingface.co/datasets/test/dataset",
        "metadata": {"name": "test-dataset", "id": artifact_id, "type": "dataset"},
        "rating": None,
        "type": "dataset"
    }

    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "dataset", "id": artifact_id}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 200
    expected_key = f"artifacts/{artifact_id}.json"
    assert expected_key in mock_s3_operations["deleted_keys"]


def test_delete_code_success(mock_s3_operations):
    """Test successful code artifact deletion."""
    artifact_id = "test-code-id"
    mock_s3_operations["stored_artifacts"][artifact_id] = {
        "url": "https://github.com/test/repo",
        "metadata": {"name": "test-repo", "id": artifact_id, "type": "code"},
        "rating": None,
        "type": "code"
    }

    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "code", "id": artifact_id}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 200


# Validation Tests
def test_delete_missing_artifact_id():
    """Test delete without artifact ID returns 400."""
    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model"}  # Missing 'id'
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "missing field" in body["error"].lower()


def test_delete_invalid_artifact_type():
    """Test delete with invalid artifact type returns 400."""
    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "invalid_type", "id": "test-id"}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "artifact_type" in body["error"] or "invalid" in body["error"].lower()


def test_delete_artifact_not_found(mock_s3_operations):
    """Test delete of non-existent artifact returns 404."""
    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model", "id": "nonexistent-id"}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert "does not exist" in body["error"]


def test_delete_type_mismatch(mock_s3_operations):
    """Test delete with type mismatch returns 404."""
    artifact_id = "test-id"
    # Store as model
    mock_s3_operations["stored_artifacts"][artifact_id] = {
        "url": "https://huggingface.co/test/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {"net_score": 0.7},
        "type": "model"
    }

    # Try to delete as dataset
    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "dataset", "id": artifact_id}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert "does not exist" in body["error"]


# Edge Cases
def test_delete_options_preflight():
    """Test OPTIONS preflight request returns 200."""
    event = {
        "httpMethod": "OPTIONS",
        "pathParameters": {"artifact_type": "model", "id": "test-id"}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 200


def test_delete_s3_not_configured(mock_s3_operations, monkeypatch):
    """Test delete when S3 bucket not configured returns 500."""
    artifact_id = "test-id"
    mock_s3_operations["stored_artifacts"][artifact_id] = {
        "url": "https://huggingface.co/test/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {},
        "type": "model"
    }

    # Remove ARTIFACTS_BUCKET env var
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)

    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model", "id": artifact_id}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "S3" in body["error"] or "Internal" in body["error"]


def test_delete_s3_error(mock_s3_error):
    """Test delete when S3 operation fails returns 500."""
    artifact_id = "test-id"
    mock_s3_error[artifact_id] = {
        "url": "https://huggingface.co/test/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {},
        "type": "model"
    }

    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model", "id": artifact_id}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "Failed to delete" in body["error"] or "error" in body["error"].lower()


def test_delete_empty_artifact_type():
    """Test delete with empty artifact_type returns 400."""
    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "", "id": "test-id"}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400


def test_delete_empty_artifact_id():
    """Test delete with empty artifact_id returns 400."""
    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model", "id": ""}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 400


def test_delete_artifact_with_metadata_type_only(mock_s3_operations):
    """Test delete artifact where type is only in metadata field."""
    artifact_id = "test-id"
    # Type only in metadata, not as top-level field
    mock_s3_operations["stored_artifacts"][artifact_id] = {
        "url": "https://huggingface.co/test/model",
        "metadata": {"name": "test", "id": artifact_id, "type": "model"},
        "rating": {}
        # No top-level "type" field
    }

    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model", "id": artifact_id}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 200


def test_delete_artifact_with_top_level_type(mock_s3_operations):
    """Test delete artifact where type is in top-level field (legacy format)."""
    artifact_id = "test-id"
    # Type in top-level field (fallback scenario)
    mock_s3_operations["stored_artifacts"][artifact_id] = {
        "url": "https://huggingface.co/test/model",
        "metadata": {"name": "test", "id": artifact_id},  # No type in metadata
        "rating": {},
        "type": "model"  # Type at top level
    }

    event = {
        "httpMethod": "DELETE",
        "pathParameters": {"artifact_type": "model", "id": artifact_id}
    }

    from lambda_handlers.delete_artifact import handler
    response = handler(event, None)

    assert response["statusCode"] == 200
