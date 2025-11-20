"""Tests for PUT /artifacts/{artifact_type}/{id} - Update Artifact endpoint."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from lambda_handlers.update_artifact import handler


@pytest.fixture
def mock_s3_artifact():
    """Mock artifact data as stored in S3."""
    return {
        "metadata": {
            "name": "test-model",
            "id": "test-artifact-123",
            "type": "model"
        },
        "url": "https://huggingface.co/google-bert/bert-base-uncased",
        "net_score": 0.75,
        "license": 0.8,
        "license_info": "apache-2.0"
    }


@pytest.fixture
def mock_evaluation_result():
    """Mock evaluation result for a model."""
    return {
        "name": "test-model",
        "category": "MODEL",
        "net_score": 0.82,
        "license": 0.9,
        "license_info": "mit",
        "ramp_up_time": 0.7,
        "bus_factor": 0.6,
        "performance_claims": 0.8,
        "dataset_and_code_score": 0.75,
        "dataset_quality": 0.7,
        "code_quality": 0.8,
        "reproducibility": 0.65,
        "reviewedness": 0.7,
        "tree_score": 0.85,
        "size_score": {"raspberry_pi": 0.3, "jetson_nano": 0.5, "desktop_pc": 0.8, "aws_server": 0.9},
        "net_score_latency": 1.5,
        "ramp_up_time_latency": 0.5,
        "bus_factor_latency": 0.3,
        "performance_claims_latency": 0.4,
        "license_latency": 0.2,
        "dataset_and_code_score_latency": 0.6,
        "dataset_quality_latency": 0.5,
        "code_quality_latency": 0.7,
        "reproducibility_latency": 0.4,
        "reviewedness_latency": 0.3,
        "tree_score_latency": 0.8,
        "size_score_latency": 0.5,
    }


def test_update_artifact_success(mock_s3_artifact, mock_evaluation_result):
    """Test successful artifact update."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-artifact-123"
        },
        "body": json.dumps({
            "metadata": {
                "name": "test-model",
                "id": "test-artifact-123",
                "type": "model"
            },
            "data": {
                "url": "https://huggingface.co/meta-llama/Llama-2-7b"
            }
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.update_artifact.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.update_artifact.save_artifact_to_s3") as mock_save:
                with patch("lambda_handlers.update_artifact.evaluate_model") as mock_eval:
                    with patch("lambda_handlers.update_artifact.get_artifact_store"):
                        mock_load.return_value = mock_s3_artifact
                        mock_eval.return_value = mock_evaluation_result

                        response = handler(event, context)

                        assert response["statusCode"] == 200
                        body = json.loads(response["body"])
                        assert "message" in body
                        assert body["message"] == "Artifact is updated."

                        # Verify save was called
                        mock_save.assert_called_once()
                        saved_data = mock_save.call_args[0][1]
                        assert saved_data["url"] == "https://huggingface.co/meta-llama/Llama-2-7b"
                        assert saved_data["net_score"] == 0.82


def test_update_artifact_not_found():
    """Test updating non-existent artifact returns 404."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "model",
            "id": "nonexistent-id"
        },
        "body": json.dumps({
            "metadata": {
                "name": "test-model",
                "id": "nonexistent-id",
                "type": "model"
            },
            "data": {
                "url": "https://huggingface.co/meta-llama/Llama-2-7b"
            }
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.update_artifact.load_artifact_from_s3") as mock_load:
            mock_load.return_value = None

            response = handler(event, context)

            assert response["statusCode"] == 404
            body = json.loads(response["body"])
            assert "error" in body
            assert "does not exist" in body["error"]


def test_update_artifact_name_mismatch(mock_s3_artifact):
    """Test that name mismatch returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-artifact-123"
        },
        "body": json.dumps({
            "metadata": {
                "name": "wrong-name",  # Different from stored name
                "id": "test-artifact-123",
                "type": "model"
            },
            "data": {
                "url": "https://huggingface.co/meta-llama/Llama-2-7b"
            }
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.update_artifact.load_artifact_from_s3") as mock_load:
            mock_load.return_value = mock_s3_artifact

            response = handler(event, context)

            assert response["statusCode"] == 400
            body = json.loads(response["body"])
            assert "error" in body


def test_update_artifact_id_mismatch(mock_s3_artifact):
    """Test that ID mismatch returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-artifact-123"
        },
        "body": json.dumps({
            "metadata": {
                "name": "test-model",
                "id": "different-id",  # Different from path parameter
                "type": "model"
            },
            "data": {
                "url": "https://huggingface.co/meta-llama/Llama-2-7b"
            }
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.update_artifact.load_artifact_from_s3") as mock_load:
            mock_load.return_value = mock_s3_artifact

            response = handler(event, context)

            assert response["statusCode"] == 400
            body = json.loads(response["body"])
            assert "error" in body


def test_update_artifact_type_mismatch(mock_s3_artifact):
    """Test that type mismatch returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "dataset",  # Different from stored type
            "id": "test-artifact-123"
        },
        "body": json.dumps({
            "metadata": {
                "name": "test-model",
                "id": "test-artifact-123",
                "type": "dataset"
            },
            "data": {
                "url": "https://huggingface.co/datasets/bookcorpus"
            }
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.update_artifact.load_artifact_from_s3") as mock_load:
            mock_load.return_value = mock_s3_artifact

            response = handler(event, context)

            assert response["statusCode"] == 400
            body = json.loads(response["body"])
            assert "error" in body


def test_update_artifact_missing_url(mock_s3_artifact):
    """Test that missing URL returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-artifact-123"
        },
        "body": json.dumps({
            "metadata": {
                "name": "test-model",
                "id": "test-artifact-123",
                "type": "model"
            },
            "data": {}  # Missing URL
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.update_artifact.load_artifact_from_s3") as mock_load:
            mock_load.return_value = mock_s3_artifact

            response = handler(event, context)

            assert response["statusCode"] == 400
            body = json.loads(response["body"])
            assert "error" in body


def test_update_artifact_invalid_json():
    """Test that invalid JSON returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-artifact-123"
        },
        "body": "invalid json{"
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        response = handler(event, context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "error" in body


def test_update_artifact_evaluation_failure(mock_s3_artifact):
    """Test that evaluation failure returns 400."""
    event = {
        "httpMethod": "PUT",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-artifact-123"
        },
        "body": json.dumps({
            "metadata": {
                "name": "test-model",
                "id": "test-artifact-123",
                "type": "model"
            },
            "data": {
                "url": "https://huggingface.co/invalid-model"
            }
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.update_artifact.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.update_artifact.evaluate_model") as mock_eval:
                with patch("lambda_handlers.update_artifact.get_artifact_store"):
                    mock_load.return_value = mock_s3_artifact
                    mock_eval.side_effect = Exception("Model not found")

                    response = handler(event, context)

                    assert response["statusCode"] == 400
                    body = json.loads(response["body"])
                    assert "error" in body


def test_update_artifact_options_request():
    """Test CORS preflight OPTIONS request."""
    event = {
        "httpMethod": "OPTIONS",
        "pathParameters": {
            "artifact_type": "model",
            "id": "test-artifact-123"
        }
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 200
