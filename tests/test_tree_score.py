"""
Tests for tree_score metric.
"""

from unittest.mock import MagicMock, patch
from src.metrics.tree_score import compute_tree_score_metric, clear_cache
from src.artifact_store import ArtifactStore


class MockArtifactStore(ArtifactStore):
    """Mock artifact store for testing."""

    def __init__(self):
        self.artifacts = {}

    def get_artifact(self, artifact_id):
        return self.artifacts.get(artifact_id)

    def artifact_exists(self, artifact_id):
        return artifact_id in self.artifacts

    def add_artifact(self, artifact_id, data):
        """Helper method to populate test data."""
        self.artifacts[artifact_id] = data


class MockModelInfo:
    def __init__(self, repo_id, base_model=None):
        self.id = repo_id
        self.cardData = {}
        if base_model is not None:
            self.cardData["base_model"] = base_model


def test_tree_score_no_base_model():
    """Test tree score with no base model (trained from scratch)."""
    clear_cache()
    model_info = MockModelInfo("test/model")
    store = MockArtifactStore()

    score = compute_tree_score_metric(model_info, store)

    # No dependencies = perfect score
    assert score == 1.0


def test_tree_score_no_artifact_store():
    """Test tree score without artifact store (CLI context)."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model="parent/model")

    score = compute_tree_score_metric(model_info, None)

    # No store = default score
    assert score == 0.5


def test_tree_score_parent_not_in_registry():
    """Test tree score when parent is not in registry."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model="parent/model")
    store = MockArtifactStore()

    score = compute_tree_score_metric(model_info, store)

    # Parent declared but not found = low score
    assert score == 0.25


def test_tree_score_single_parent():
    """Test tree score with single parent in registry."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model="parent/model")
    store = MockArtifactStore()

    # Add parent to registry with high score
    # Note: artifact_id would be generated from generate_artifact_id("model", "parent/model")
    # For testing, we'll use a mock ID
    with patch("src.metrics.tree_score.generate_artifact_id") as mock_gen:
        mock_gen.return_value = "parent-id"
        store.add_artifact("parent-id", {"net_score": 0.9, "base_model": []})

        score = compute_tree_score_metric(model_info, store)

    # Should return parent's score
    assert score == 0.9


def test_tree_score_multiple_parents():
    """Test tree score with multiple parents (merged model)."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model=["parent1/model", "parent2/model"])
    store = MockArtifactStore()

    with patch("src.metrics.tree_score.generate_artifact_id") as mock_gen:
        def gen_id(type, url):
            if "parent1" in url:
                return "parent1-id"
            elif "parent2" in url:
                return "parent2-id"
            return "unknown"

        mock_gen.side_effect = gen_id

        store.add_artifact("parent1-id", {"net_score": 0.8, "base_model": []})
        store.add_artifact("parent2-id", {"net_score": 0.6, "base_model": []})

        score = compute_tree_score_metric(model_info, store)

    # Should return average of parents: (0.8 + 0.6) / 2 = 0.7
    assert score == 0.7


def test_tree_score_recursive_lineage():
    """Test tree score with multi-level lineage."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model="parent/model")
    store = MockArtifactStore()

    with patch("src.metrics.tree_score.generate_artifact_id") as mock_gen:
        def gen_id(type, url):
            if "grandparent" in url:
                return "grandparent-id"
            elif "parent" in url:
                return "parent-id"
            return "unknown"

        mock_gen.side_effect = gen_id

        # Parent has grandparent
        store.add_artifact("parent-id", {"net_score": 0.8, "base_model": "grandparent/model"})
        store.add_artifact("grandparent-id", {"net_score": 0.9, "base_model": []})

        score = compute_tree_score_metric(model_info, store)

    # Should average parent and grandparent scores
    # Parent score: (0.8 + 0.9) / 2 = 0.85
    # Final score: 0.85
    assert 0.8 <= score <= 0.9


def test_tree_score_depth_limit():
    """Test that tree score respects depth limit."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model="parent/model")
    store = MockArtifactStore()

    with patch("src.metrics.tree_score.generate_artifact_id") as mock_gen:
        # Create a deep chain
        def gen_id(type, url):
            return url.replace("/", "-")

        mock_gen.side_effect = gen_id

        # Create chain: model -> parent -> gp1 -> gp2 -> gp3 -> gp4
        store.add_artifact("parent-model", {"net_score": 0.8, "base_model": "gp1-model"})
        store.add_artifact("gp1-model", {"net_score": 0.8, "base_model": "gp2-model"})
        store.add_artifact("gp2-model", {"net_score": 0.8, "base_model": "gp3-model"})
        store.add_artifact("gp3-model", {"net_score": 0.8, "base_model": "gp4-model"})
        store.add_artifact("gp4-model", {"net_score": 0.8, "base_model": []})

        score = compute_tree_score_metric(model_info, store)

    # Should stop at max_depth=3
    assert 0.7 <= score <= 0.9


def test_tree_score_circular_dependency():
    """Test that tree score handles circular dependencies."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model="parent/model")
    store = MockArtifactStore()

    with patch("src.metrics.tree_score.generate_artifact_id") as mock_gen:
        def gen_id(type, url):
            return url.replace("/", "-")

        mock_gen.side_effect = gen_id

        # Create circular reference: model -> parent -> model
        store.add_artifact("parent-model", {"net_score": 0.8, "base_model": "test/model"})
        store.add_artifact("test-model", {"net_score": 0.7, "base_model": "parent/model"})

        score = compute_tree_score_metric(model_info, store)

    # Should handle cycle gracefully (returns parent's score without recursing)
    assert 0.6 <= score <= 0.9


def test_tree_score_missing_net_score_field():
    """Test tree score when parent artifact lacks net_score."""
    clear_cache()
    model_info = MockModelInfo("test/model", base_model="parent/model")
    store = MockArtifactStore()

    with patch("src.metrics.tree_score.generate_artifact_id") as mock_gen:
        mock_gen.return_value = "parent-id"
        # Parent exists but has no net_score field
        store.add_artifact("parent-id", {"name": "parent", "type": "model"})

        score = compute_tree_score_metric(model_info, store)

    # Parent found but invalid = same as not found
    assert score == 0.25


def test_tree_score_error_handling():
    """Test error handling returns default score."""
    clear_cache()
    # Create invalid model_info
    model_info = MagicMock()
    model_info.cardData = None

    store = MockArtifactStore()

    score = compute_tree_score_metric(model_info, store)

    # Should handle gracefully
    assert 0.0 <= score <= 1.0


def test_tree_score_bounds():
    """Test that score is always within [0, 1]."""
    clear_cache()
    model_info = MockModelInfo("test/model")
    store = MockArtifactStore()

    score = compute_tree_score_metric(model_info, store)

    assert 0.0 <= score <= 1.0
