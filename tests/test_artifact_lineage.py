"""Tests for artifact lineage endpoint."""

import json
from unittest.mock import MagicMock, patch

from lambda_handlers.artifact_lineage import handler


def test_lineage_missing_auth_token():
    """Test lineage endpoint returns 403 when auth token is missing."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": "test-artifact-123"},
        "headers": {},
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 403
    body = json.loads(response["body"])
    assert "Authentication failed" in body["error"]


def test_lineage_invalid_auth_token():
    """Test lineage endpoint returns 403 when auth token is invalid."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": "test-artifact-123"},
        "headers": {"X-Authorization": "invalid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.InvalidTokenError", Exception):
        mock_auth.return_value.verify_token.side_effect = Exception("Invalid token")

        response = handler(event, context)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert "Authentication failed" in body["error"]


def test_lineage_missing_artifact_id():
    """Test lineage endpoint returns 400 when artifact_id is missing."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth:
        mock_auth.return_value.verify_token.return_value = "test-user"

        response = handler(event, context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "missing field" in body["error"].lower()


def test_lineage_artifact_not_found():
    """Test lineage endpoint returns 404 when artifact doesn't exist."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": "nonexistent-artifact"},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.list_all_artifacts_from_s3") as mock_list:

        mock_auth.return_value.verify_token.return_value = "test-user"
        mock_list.return_value = {}

        response = handler(event, context)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "does not exist" in body["error"]


def test_lineage_non_model_artifact():
    """Test lineage endpoint returns 400 for non-model artifacts."""
    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": "dataset-123"},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.list_all_artifacts_from_s3") as mock_list:

        mock_auth.return_value.verify_token.return_value = "test-user"
        mock_list.return_value = {
            "dataset-123": {
                "url": "https://huggingface.co/datasets/test",
                "metadata": {"type": "dataset", "name": "test-dataset"},
                "type": "dataset"
            }
        }

        response = handler(event, context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "cannot be computed" in body["error"]


def test_lineage_single_model_no_dependencies():
    """Test lineage for a model with no dependencies."""
    artifact_id = "model-123"
    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": artifact_id},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.list_all_artifacts_from_s3") as mock_list:

        mock_auth.return_value.verify_token.return_value = "test-user"
        mock_list.return_value = {
            artifact_id: {
                "url": "https://huggingface.co/test/model",
                "metadata": {"type": "model", "name": "test-model", "id": artifact_id},
                "type": "model",
                "rating": {}
            }
        }

        response = handler(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])

        # Should have one node (the model itself) and no edges
        assert "nodes" in body
        assert "edges" in body
        assert len(body["nodes"]) == 1
        assert len(body["edges"]) == 0
        assert body["nodes"][0]["artifact_id"] == artifact_id
        assert body["nodes"][0]["name"] == "test-model"


def test_lineage_model_with_base_model():
    """Test lineage for a model with a base model dependency."""
    child_id = "model-child"
    parent_id = "model-parent"

    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": child_id},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.list_all_artifacts_from_s3") as mock_list:

        mock_auth.return_value.verify_token.return_value = "test-user"
        mock_list.return_value = {
            child_id: {
                "url": "https://huggingface.co/test/child-model",
                "metadata": {"type": "model", "name": "child-model", "id": child_id},
                "type": "model",
                "base_model": "https://huggingface.co/test/parent-model"
            },
            parent_id: {
                "url": "https://huggingface.co/test/parent-model",
                "metadata": {"type": "model", "name": "parent-model", "id": parent_id},
                "type": "model"
            }
        }

        response = handler(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])

        # Should have two nodes and one edge
        assert len(body["nodes"]) == 2
        assert len(body["edges"]) == 1

        # Check edge relationship
        edge = body["edges"][0]
        assert edge["from_node_artifact_id"] == parent_id
        assert edge["to_node_artifact_id"] == child_id
        assert edge["relationship"] == "base_model"


def test_lineage_external_dependency():
    """Test lineage when base model is not in registry (external)."""
    artifact_id = "model-123"
    external_base = "bert-base-uncased"

    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": artifact_id},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.list_all_artifacts_from_s3") as mock_list:

        mock_auth.return_value.verify_token.return_value = "test-user"
        mock_list.return_value = {
            artifact_id: {
                "url": "https://huggingface.co/test/my-model",
                "metadata": {"type": "model", "name": "my-model", "id": artifact_id},
                "type": "model",
                "base_model": external_base
            }
        }

        response = handler(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])

        # Should have two nodes (current model + external dependency)
        assert len(body["nodes"]) == 2
        assert len(body["edges"]) == 1

        # Find the external node
        external_node = next((n for n in body["nodes"] if n["artifact_id"] == external_base), None)
        assert external_node is not None
        assert external_node["source"] == "external"

        # Check edge
        edge = body["edges"][0]
        assert edge["from_node_artifact_id"] == external_base
        assert edge["to_node_artifact_id"] == artifact_id


def test_lineage_multiple_base_models():
    """Test lineage for merged model with multiple base models."""
    merged_id = "model-merged"
    parent1_id = "model-parent1"
    parent2_id = "model-parent2"

    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": merged_id},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.list_all_artifacts_from_s3") as mock_list:

        mock_auth.return_value.verify_token.return_value = "test-user"
        mock_list.return_value = {
            merged_id: {
                "url": "https://huggingface.co/test/merged",
                "metadata": {"type": "model", "name": "merged-model", "id": merged_id},
                "type": "model",
                "base_model": [
                    "https://huggingface.co/test/parent1",
                    "https://huggingface.co/test/parent2"
                ]
            },
            parent1_id: {
                "url": "https://huggingface.co/test/parent1",
                "metadata": {"type": "model", "name": "parent1", "id": parent1_id},
                "type": "model"
            },
            parent2_id: {
                "url": "https://huggingface.co/test/parent2",
                "metadata": {"type": "model", "name": "parent2", "id": parent2_id},
                "type": "model"
            }
        }

        response = handler(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])

        # Should have three nodes and two edges
        assert len(body["nodes"]) == 3
        assert len(body["edges"]) == 2

        # Both parents should point to the merged model
        for edge in body["edges"]:
            assert edge["to_node_artifact_id"] == merged_id
            assert edge["from_node_artifact_id"] in [parent1_id, parent2_id]


def test_lineage_recursive_dependencies():
    """Test lineage with multi-level dependencies."""
    child_id = "model-child"
    parent_id = "model-parent"
    grandparent_id = "model-grandparent"

    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": child_id},
        "headers": {"X-Authorization": "valid-token"},
    }
    context = MagicMock()

    with patch("lambda_handlers.artifact_lineage.get_default_auth_service") as mock_auth, \
         patch("lambda_handlers.artifact_lineage.list_all_artifacts_from_s3") as mock_list:

        mock_auth.return_value.verify_token.return_value = "test-user"
        mock_list.return_value = {
            child_id: {
                "url": "https://huggingface.co/test/child",
                "metadata": {"type": "model", "name": "child", "id": child_id},
                "type": "model",
                "base_model": "https://huggingface.co/test/parent"
            },
            parent_id: {
                "url": "https://huggingface.co/test/parent",
                "metadata": {"type": "model", "name": "parent", "id": parent_id},
                "type": "model",
                "base_model": "https://huggingface.co/test/grandparent"
            },
            grandparent_id: {
                "url": "https://huggingface.co/test/grandparent",
                "metadata": {"type": "model", "name": "grandparent", "id": grandparent_id},
                "type": "model"
            }
        }

        response = handler(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])

        # Should have three nodes in the lineage chain
        assert len(body["nodes"]) == 3
        assert len(body["edges"]) == 2

        # Verify the chain: grandparent -> parent -> child
        node_ids = {node["artifact_id"] for node in body["nodes"]}
        assert child_id in node_ids
        assert parent_id in node_ids
        assert grandparent_id in node_ids


def test_lineage_options_request():
    """Test OPTIONS preflight request."""
    event = {
        "httpMethod": "OPTIONS",
    }
    context = MagicMock()

    response = handler(event, context)

    assert response["statusCode"] == 200
