"""Tests for POST /artifact/model/{id}/license-check - License Compatibility Check endpoint."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from lambda_handlers.license_check import handler


@pytest.fixture
def mock_model_artifact():
    """Mock model artifact with license info."""
    return {
        "metadata": {
            "name": "bert-base",
            "id": "test-model-123",
            "type": "model"
        },
        "url": "https://huggingface.co/google-bert/bert-base-uncased",
        "license_info": "apache-2.0",
        "net_score": 0.75
    }


def test_license_check_compatible():
    """Test successful license compatibility check (compatible licenses)."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": json.dumps({
            "github_url": "https://github.com/google-research/bert"
        })
    }
    context = MagicMock()

    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"},
        "url": "https://huggingface.co/google-bert/bert-base-uncased",
        "license_info": "apache-2.0"
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.license_check.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.license_check.fetch_github_license") as mock_github:
                with patch("lambda_handlers.license_check.check_license_compatibility") as mock_check:
                    mock_load.return_value = mock_artifact
                    mock_github.return_value = "mit"
                    mock_check.return_value = (True, "Both licenses are permissive and compatible")

                    response = handler(event, context)

                    assert response["statusCode"] == 200
                    body = json.loads(response["body"])
                    assert body is True  # Should return boolean true


def test_license_check_incompatible():
    """Test license compatibility check with incompatible licenses."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": json.dumps({
            "github_url": "https://github.com/some-org/gpl-project"
        })
    }
    context = MagicMock()

    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"},
        "url": "https://huggingface.co/google-bert/bert-base-uncased",
        "license_info": "apache-2.0"
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.license_check.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.license_check.fetch_github_license") as mock_github:
                with patch("lambda_handlers.license_check.check_license_compatibility") as mock_check:
                    mock_load.return_value = mock_artifact
                    mock_github.return_value = "gpl-3.0"
                    mock_check.return_value = (False, "GitHub license gpl-3.0 is incompatible (copyleft)")

                    response = handler(event, context)

                    assert response["statusCode"] == 200
                    body = json.loads(response["body"])
                    assert body is False  # Should return boolean false


def test_license_check_artifact_not_found():
    """Test license check for non-existent artifact."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "nonexistent-id"
        },
        "body": json.dumps({
            "github_url": "https://github.com/google-research/bert"
        })
    }
    context = MagicMock()

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.license_check.load_artifact_from_s3") as mock_load:
            mock_load.return_value = None

            response = handler(event, context)

            assert response["statusCode"] == 404
            body = json.loads(response["body"])
            assert "error" in body
            assert "not be found" in body["error"]


def test_license_check_missing_github_url():
    """Test license check without GitHub URL."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": json.dumps({})  # Missing github_url
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
    assert "malformed" in body["error"]


def test_license_check_invalid_github_url():
    """Test license check with invalid GitHub URL."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": json.dumps({
            "github_url": "https://gitlab.com/some/project"  # Not a GitHub URL
        })
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body


def test_license_check_invalid_json():
    """Test license check with invalid JSON."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": "invalid json{"
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body


def test_license_check_github_fetch_failure():
    """Test when GitHub license cannot be fetched."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": json.dumps({
            "github_url": "https://github.com/private/repo"
        })
    }
    context = MagicMock()

    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"},
        "license_info": "apache-2.0"
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.license_check.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.license_check.fetch_github_license") as mock_github:
                mock_load.return_value = mock_artifact
                mock_github.return_value = None  # Failed to fetch

                response = handler(event, context)

                assert response["statusCode"] == 502
                body = json.loads(response["body"])
                assert "error" in body
                assert "could not be retrieved" in body["error"]


def test_license_check_no_stored_license_refetch_success():
    """Test when license is not stored but can be re-fetched."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": json.dumps({
            "github_url": "https://github.com/google-research/bert"
        })
    }
    context = MagicMock()

    # Artifact without license_info
    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"},
        "url": "https://huggingface.co/google-bert/bert-base-uncased"
    }

    mock_model_info = MagicMock()
    mock_model_info.cardData = {"license": "apache-2.0"}

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.license_check.load_artifact_from_s3") as mock_load:
            with patch("lambda_handlers.license_check.fetch_github_license") as mock_github:
                with patch("lambda_handlers.license_check.check_license_compatibility") as mock_check:
                    with patch("src.metrics.helpers.pull_model.pull_model_info") as mock_pull:
                        mock_load.return_value = mock_artifact
                        mock_pull.return_value = mock_model_info
                        mock_github.return_value = "mit"
                        mock_check.return_value = (True, "Compatible")

                        response = handler(event, context)

                        assert response["statusCode"] == 200
                        body = json.loads(response["body"])
                        assert body is True


def test_license_check_no_license_available():
    """Test when license cannot be determined from artifact."""
    event = {
        "httpMethod": "POST",
        "pathParameters": {
            "id": "test-model-123"
        },
        "body": json.dumps({
            "github_url": "https://github.com/google-research/bert"
        })
    }
    context = MagicMock()

    # Artifact without license_info and no URL
    mock_artifact = {
        "metadata": {"name": "bert-base", "id": "test-model-123", "type": "model"}
    }

    with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-bucket"}):
        with patch("lambda_handlers.license_check.load_artifact_from_s3") as mock_load:
            mock_load.return_value = mock_artifact

            response = handler(event, context)

            assert response["statusCode"] == 404
            body = json.loads(response["body"])
            assert "error" in body


def test_license_check_options_request():
    """Test CORS preflight OPTIONS request."""
    event = {
        "httpMethod": "OPTIONS",
        "pathParameters": {
            "id": "test-model-123"
        }
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 200


# Tests for GitHub license integration module

def test_parse_github_url_valid():
    """Test parsing valid GitHub URLs."""
    from src.github_license import parse_github_url

    assert parse_github_url("https://github.com/google-research/bert") == ("google-research", "bert")
    assert parse_github_url("https://github.com/openai/whisper/") == ("openai", "whisper")
    assert parse_github_url("https://github.com/huggingface/transformers.git") == ("huggingface", "transformers")


def test_parse_github_url_invalid():
    """Test parsing invalid GitHub URLs."""
    from src.github_license import parse_github_url

    assert parse_github_url("https://gitlab.com/some/project") is None
    assert parse_github_url("https://github.com/invalid") is None
    assert parse_github_url("not a url") is None


def test_normalize_license_identifier():
    """Test license identifier normalization."""
    from src.github_license import normalize_license_identifier

    assert normalize_license_identifier("Apache-2.0") == "apache-2.0"
    assert normalize_license_identifier("MIT License") == "mit"
    assert normalize_license_identifier("BSD 3-Clause") == "bsd-3-clause"
    assert normalize_license_identifier("GPL-3.0") == "gpl-3.0"
    assert normalize_license_identifier("lgpl-2.1") == "lgpl-2.1"


def test_check_license_compatibility_both_permissive():
    """Test compatibility check with both permissive licenses."""
    from src.github_license import check_license_compatibility

    compatible, reason = check_license_compatibility("apache-2.0", "mit")
    assert compatible is True
    assert "permissive" in reason.lower()


def test_check_license_compatibility_model_copyleft():
    """Test compatibility check with model having copyleft license."""
    from src.github_license import check_license_compatibility

    compatible, reason = check_license_compatibility("gpl-3.0", "mit")
    assert compatible is False
    assert "gpl-3.0" in reason.lower()


def test_check_license_compatibility_github_copyleft():
    """Test compatibility check with GitHub having copyleft license."""
    from src.github_license import check_license_compatibility

    compatible, reason = check_license_compatibility("apache-2.0", "gpl-3.0")
    assert compatible is False
    assert "gpl-3.0" in reason.lower()


def test_check_license_compatibility_unknown():
    """Test compatibility check with unknown licenses."""
    from src.github_license import check_license_compatibility

    compatible, reason = check_license_compatibility("", "mit")
    assert compatible is False
    assert "could not be determined" in reason.lower()


@patch("src.github_license.requests.get")
def test_fetch_github_license_success(mock_get):
    """Test successful GitHub license fetch."""
    from src.github_license import fetch_github_license

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "license": {"spdx_id": "Apache-2.0"}
    }
    mock_get.return_value = mock_response

    license_id = fetch_github_license("https://github.com/google-research/bert")
    assert license_id == "apache-2.0"


@patch("src.github_license.requests.get")
def test_fetch_github_license_not_found(mock_get):
    """Test GitHub license fetch for non-existent repo."""
    from src.github_license import fetch_github_license

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    license_id = fetch_github_license("https://github.com/nonexistent/repo")
    assert license_id is None


@patch("src.github_license.requests.get")
def test_fetch_github_license_rate_limited(mock_get):
    """Test GitHub license fetch when rate limited."""
    from src.github_license import fetch_github_license

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_get.return_value = mock_response

    license_id = fetch_github_license("https://github.com/some/repo")
    assert license_id is None
