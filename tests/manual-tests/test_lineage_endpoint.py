#!/usr/bin/env python3
"""
Manual test script for the lineage endpoint.

This script demonstrates how to use the lineage endpoint with example data.
"""

import json
from lambda_handlers.artifact_lineage import (
    _extract_base_models,
    _build_lineage_graph,
    _resolve_base_model_to_id
)


def test_extract_base_models():
    """Test extracting base models from artifact data."""
    print("\n=== Test: Extract Base Models ===")

    # Test 1: Single base model
    artifact1 = {
        "base_model": "bert-base-uncased"
    }
    result1 = _extract_base_models(artifact1)
    print(f"Single base model: {result1}")
    assert result1 == ["bert-base-uncased"], f"Expected ['bert-base-uncased'], got {result1}"

    # Test 2: Multiple base models
    artifact2 = {
        "base_model": ["model-a", "model-b"]
    }
    result2 = _extract_base_models(artifact2)
    print(f"Multiple base models: {result2}")
    assert result2 == ["model-a", "model-b"], f"Expected ['model-a', 'model-b'], got {result2}"

    # Test 3: No base model
    artifact3 = {}
    result3 = _extract_base_models(artifact3)
    print(f"No base model: {result3}")
    assert result3 == [], f"Expected [], got {result3}"

    # Test 4: Base model in rating
    artifact4 = {
        "rating": {
            "base_model": "gpt2"
        }
    }
    result4 = _extract_base_models(artifact4)
    print(f"Base model in rating: {result4}")
    assert result4 == ["gpt2"], f"Expected ['gpt2'], got {result4}"

    print("✓ All extraction tests passed")


def test_resolve_base_model():
    """Test resolving base model references to artifact IDs."""
    print("\n=== Test: Resolve Base Model ===")

    all_artifacts = {
        "artifact-123": {
            "url": "https://huggingface.co/bert-base-uncased",
            "metadata": {"name": "BERT Base"}
        },
        "artifact-456": {
            "url": "https://huggingface.co/gpt2",
            "metadata": {"name": "GPT-2"}
        }
    }

    # Test 1: Direct ID match
    result1 = _resolve_base_model_to_id("artifact-123", all_artifacts)
    print(f"Direct match: {result1}")
    assert result1 == "artifact-123", f"Expected 'artifact-123', got {result1}"

    # Test 2: URL contains base model
    result2 = _resolve_base_model_to_id("bert-base-uncased", all_artifacts)
    print(f"URL contains: {result2}")
    assert result2 == "artifact-123", f"Expected 'artifact-123', got {result2}"

    # Test 3: Full URL match
    result3 = _resolve_base_model_to_id("https://huggingface.co/gpt2", all_artifacts)
    print(f"Full URL: {result3}")
    assert result3 == "artifact-456", f"Expected 'artifact-456', got {result3}"

    # Test 4: Not found
    result4 = _resolve_base_model_to_id("nonexistent-model", all_artifacts)
    print(f"Not found: {result4}")
    assert result4 is None, f"Expected None, got {result4}"

    print("✓ All resolution tests passed")


def test_build_lineage_graph():
    """Test building a lineage graph."""
    print("\n=== Test: Build Lineage Graph ===")

    # Create test data: child -> parent -> grandparent
    all_artifacts = {
        "child-id": {
            "url": "https://huggingface.co/test/child",
            "metadata": {"name": "Child Model", "type": "model"},
            "base_model": "https://huggingface.co/test/parent"
        },
        "parent-id": {
            "url": "https://huggingface.co/test/parent",
            "metadata": {"name": "Parent Model", "type": "model"},
            "base_model": "https://huggingface.co/test/grandparent"
        },
        "grandparent-id": {
            "url": "https://huggingface.co/test/grandparent",
            "metadata": {"name": "Grandparent Model", "type": "model"}
        }
    }

    graph = _build_lineage_graph("child-id", all_artifacts)

    print(f"Nodes: {len(graph['nodes'])}")
    print(f"Edges: {len(graph['edges'])}")

    for node in graph['nodes']:
        print(f"  - {node['artifact_id']}: {node['name']} ({node['source']})")

    for edge in graph['edges']:
        print(f"  - {edge['from_node_artifact_id']} -> {edge['to_node_artifact_id']} [{edge['relationship']}]")

    assert len(graph['nodes']) == 3, f"Expected 3 nodes, got {len(graph['nodes'])}"
    assert len(graph['edges']) == 2, f"Expected 2 edges, got {len(graph['edges'])}"

    print("✓ Lineage graph test passed")


def test_external_dependency():
    """Test graph with external (not in registry) dependency."""
    print("\n=== Test: External Dependency ===")

    all_artifacts = {
        "my-model": {
            "url": "https://huggingface.co/test/my-model",
            "metadata": {"name": "My Model", "type": "model"},
            "base_model": "bert-base-uncased"  # External - not in registry
        }
    }

    graph = _build_lineage_graph("my-model", all_artifacts)

    print(f"Nodes: {len(graph['nodes'])}")
    for node in graph['nodes']:
        print(f"  - {node['artifact_id']}: {node['name']} ({node['source']})")

    assert len(graph['nodes']) == 2, f"Expected 2 nodes, got {len(graph['nodes'])}"
    assert len(graph['edges']) == 1, f"Expected 1 edge, got {len(graph['edges'])}"

    # Check that external dependency is marked as such
    external_nodes = [n for n in graph['nodes'] if n['source'] == 'external']
    assert len(external_nodes) == 1, f"Expected 1 external node, got {len(external_nodes)}"
    assert external_nodes[0]['artifact_id'] == "bert-base-uncased"

    print("✓ External dependency test passed")


def test_merged_model():
    """Test graph for merged model with multiple base models."""
    print("\n=== Test: Merged Model ===")

    all_artifacts = {
        "merged-model": {
            "url": "https://huggingface.co/test/merged",
            "metadata": {"name": "Merged Model", "type": "model"},
            "base_model": [
                "https://huggingface.co/test/model-a",
                "https://huggingface.co/test/model-b"
            ]
        },
        "model-a": {
            "url": "https://huggingface.co/test/model-a",
            "metadata": {"name": "Model A", "type": "model"}
        },
        "model-b": {
            "url": "https://huggingface.co/test/model-b",
            "metadata": {"name": "Model B", "type": "model"}
        }
    }

    graph = _build_lineage_graph("merged-model", all_artifacts)

    print(f"Nodes: {len(graph['nodes'])}")
    print(f"Edges: {len(graph['edges'])}")

    for edge in graph['edges']:
        print(f"  - {edge['from_node_artifact_id']} -> {edge['to_node_artifact_id']}")

    assert len(graph['nodes']) == 3, f"Expected 3 nodes, got {len(graph['nodes'])}"
    assert len(graph['edges']) == 2, f"Expected 2 edges, got {len(graph['edges'])}"

    # Both parents should point to merged model
    for edge in graph['edges']:
        assert edge['to_node_artifact_id'] == "merged-model"

    print("✓ Merged model test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Lineage Endpoint Logic")
    print("=" * 60)

    try:
        test_extract_base_models()
        test_resolve_base_model()
        test_build_lineage_graph()
        test_external_dependency()
        test_merged_model()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
