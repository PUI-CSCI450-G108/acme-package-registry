"""Tests for GET /artifact/{artifact_type}/{id}/cost - Get Artifact Cost endpoint."""

import json
import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from lambda_handlers.get_artifact_cost import handler


@pytest.fixture
def mock_model_artifact():
    """Mock model artifact data."""
    return {
        "metadata": {
            "name": "bert-base",
            "id": "test-model-123",
            "type": "model"
        },
        "url": "https://huggingface.co/google-bert/bert-base-uncased",
        "net_score": 0.75,
        "base_model": None  # No dependencies
    }


@pytest.fixture
def mock_model_with_deps():
    """Mock model artifact with dependencies."""
    return {
        "metadata": {
            "name": "fine-tuned-model",
            "id": "test-model-456",
            "type": "model"
        },
        "url": "https://huggingface.co/user/fine-tuned-bert",
        "net_score": 0.80,
        "base_model": "google-bert/bert-base-uncased"  # Has dependency
    }


@pytest.fixture
def mock_model_info():
    """Mock HuggingFace model info object."""
    mock = Mock()
    mock.safetensors = Mock()
    mock.safetensors.parameters = {"F32": 110000000}  # 110M parameters in F32 = 440MB
    return mock


def test_get_artifact_cost_success():
    """Test successful cost retrieval without dependencies."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-model-123"
        },
        "queryStringParameters": None
    }
    context = MagicMock()

    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"},
        "url": "https://huggingface.co/google-bert/bert-base-uncased"
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.get_artifact_cost.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.get_artifact_cost._get_artifact_size_mb") as mock_size:
                mock_load.return_value = mock_artifact
                mock_size.return_value = 440.5  # 440.5 MB

                response = handler(event, context)

                assert response["statusCode"] == 200
                body = json.loads(response["body"])
                assert "test-model-123" in body
                assert body["test-model-123"]["total_cost"] == 440.5
                assert "standalone_cost" not in body["test-model-123"]  # Not included without dependency=true


def test_get_artifact_cost_with_dependencies():
    """Test cost retrieval with dependencies."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-model-456"
        },
        "queryStringParameters": {
            "dependency": "true"
        }
    }
    context = MagicMock()

    main_artifact = {
        "metadata": {"name": "fine-tuned-model", "id": "test-model-456", "type": "model"},
        "url": "https://huggingface.co/user/fine-tuned-bert",
        "base_model": ["google-bert/bert-base-uncased"]
    }

    dependency_artifact = {
        "metadata": {"name": "bert-base", "id": "dep-123", "type": "model"},
        "url": "https://huggingface.co/google-bert/bert-base-uncased"
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.get_artifact_cost.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.get_artifact_cost._get_artifact_size_mb") as mock_size:
                with patch("src.artifact_utils.generate_artifact_id") as mock_id:
                    # First call returns main artifact, second returns dependency
                    mock_load.side_effect = [main_artifact, dependency_artifact]
                    mock_id.return_value = "dep-123"

                    # First call for main (200MB), second for dependency (440MB)
                    mock_size.side_effect = [200.0, 440.0]

                    response = handler(event, context)

                    assert response["statusCode"] == 200
                    body = json.loads(response["body"])

                    # Main artifact should have standalone + total
                    assert "test-model-456" in body
                    assert body["test-model-456"]["standalone_cost"] == 200.0
                    assert body["test-model-456"]["total_cost"] == 640.0  # 200 + 440

                    # Dependency should be listed
                    assert "dep-123" in body
                    assert body["dep-123"]["standalone_cost"] == 440.0
                    assert body["dep-123"]["total_cost"] == 440.0


def test_get_artifact_cost_not_found():
    """Test cost retrieval for non-existent artifact."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {
            "artifact_type": "model",
            "id": "nonexistent-id"
        },
        "queryStringParameters": None
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.get_artifact_cost.load_artifact_from_s3") as mock_load:
            mock_load.return_value = None

            response = handler(event, context)

            assert response["statusCode"] == 404
            body = json.loads(response["body"])
            assert "error" in body
            assert "does not exist" in body["error"]


def test_get_artifact_cost_type_mismatch():
    """Test cost retrieval with mismatched artifact type."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {
            "artifact_type": "dataset",  # Requesting as dataset
            "id": "test-model-123"
        },
        "queryStringParameters": None
    }
    context = MagicMock()

    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"},  # Actually a model
        "url": "https://huggingface.co/google-bert/bert-base-uncased"
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.get_artifact_cost.load_artifact_from_s3") as mock_load:
            mock_load.return_value = mock_artifact

            response = handler(event, context)

            assert response["statusCode"] == 404
            body = json.loads(response["body"])
            assert "error" in body


def test_get_artifact_cost_invalid_artifact_type():
    """Test cost retrieval with invalid artifact type."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {
            "artifact_type": "invalid",
            "id": "test-model-123"
        },
        "queryStringParameters": None
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body


def test_get_artifact_cost_missing_id():
    """Test cost retrieval without artifact ID."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {
            "artifact_type": "model",
            "id": None
        },
        "queryStringParameters": None
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body


def test_get_artifact_cost_size_calculation_failure():
    """Test when size calculation fails."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-model-123"
        },
        "queryStringParameters": None
    }
    context = MagicMock()

    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"},
        "url": "https://huggingface.co/google-bert/bert-base-uncased"
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.get_artifact_cost.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.get_artifact_cost._get_artifact_size_mb") as mock_size:
                mock_load.return_value = mock_artifact
                mock_size.return_value = None  # Size calculation failed

                response = handler(event, context)

                assert response["statusCode"] == 500
                body = json.loads(response["body"])
                assert "error" in body
                assert "cost calculator" in body["error"]


def test_get_artifact_cost_options_request():
    """Test CORS preflight OPTIONS request."""
    event = {
        "httpMethod": "OPTIONS",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-model-123"
        }
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 200


def test_get_artifact_size_mb_from_safetensors():
    """Test size calculation from safetensors parameters."""
    from lambda_handlers.get_artifact_cost import _get_artifact_size_mb

    mock_info = Mock()
    mock_info.safetensors = Mock()
    mock_info.safetensors.parameters = {"F32": 110000000}  # 110M params * 4 bytes = 440MB
    mock_info.runtime = None

    artifact_data = {
        "url": "https://huggingface.co/google-bert/bert-base-uncased"
    }

    with patch("lambda_handlers.get_artifact_cost.pull_model_info") as mock_pull:
        mock_pull.return_value = mock_info

        size_mb = _get_artifact_size_mb(artifact_data)

        assert size_mb is not None
        assert size_mb == pytest.approx(419.62, rel=0.1)  # 440000000 bytes / (1024*1024)


def test_get_artifact_size_mb_from_files():
    """Test size calculation from file siblings."""
    from lambda_handlers.get_artifact_cost import _get_artifact_size_mb

    mock_sibling = Mock()
    mock_sibling.rfilename = "model.safetensors"
    mock_sibling.size = 440000000  # 440MB

    mock_info = Mock()
    mock_info.safetensors = Mock()
    mock_info.safetensors.parameters = None
    mock_info.siblings = [mock_sibling]
    mock_info.runtime = None

    artifact_data = {
        "url": "https://huggingface.co/google-bert/bert-base-uncased"
    }

    with patch("lambda_handlers.get_artifact_cost.pull_model_info") as mock_pull:
        mock_pull.return_value = mock_info

        size_mb = _get_artifact_size_mb(artifact_data)

        assert size_mb is not None
        assert size_mb == pytest.approx(419.62, rel=0.1)


def test_get_artifact_size_mb_no_url():
    """Test size calculation when URL is missing."""
    from lambda_handlers.get_artifact_cost import _get_artifact_size_mb

    artifact_data = {}

    size_mb = _get_artifact_size_mb(artifact_data)

    assert size_mb is None
