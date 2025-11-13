"""
Artifact storage abstraction layer.

Provides a uniform interface for accessing artifact data in both Lambda (S3) and CLI contexts.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ArtifactStore(ABC):
    """Abstract base class for artifact storage backends."""

    @abstractmethod
    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve artifact data by ID.

        Args:
            artifact_id: Unique identifier for the artifact

        Returns:
            Dictionary containing artifact data (including net_score), or None if not found
        """
        pass

    @abstractmethod
    def artifact_exists(self, artifact_id: str) -> bool:
        """
        Check if an artifact exists in storage.

        Args:
            artifact_id: Unique identifier for the artifact

        Returns:
            True if artifact exists, False otherwise
        """
        pass


class S3ArtifactStore(ArtifactStore):
    """
    S3-backed artifact storage implementation for Lambda context.
    """

    def __init__(self, bucket_name: str):
        """
        Initialize S3 artifact store.

        Args:
            bucket_name: Name of the S3 bucket containing artifacts
        """
        self.bucket_name = bucket_name
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy-load S3 client to avoid import/connection overhead."""
        if self._s3_client is None:
            import boto3

            self._s3_client = boto3.client("s3")
        return self._s3_client

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve artifact from S3.

        Args:
            artifact_id: Unique identifier for the artifact

        Returns:
            Parsed JSON artifact data, or None if not found
        """
        try:
            key = f"artifacts/{artifact_id}.json"
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except self.s3_client.exceptions.NoSuchKey:
            logger.debug(f"Artifact {artifact_id} not found in S3")
            return None
        except Exception as e:
            logger.error(f"Error fetching artifact {artifact_id} from S3: {e}")
            return None

    def artifact_exists(self, artifact_id: str) -> bool:
        """
        Check if artifact exists in S3.

        Args:
            artifact_id: Unique identifier for the artifact

        Returns:
            True if artifact exists, False otherwise
        """
        try:
            key = f"artifacts/{artifact_id}.json"
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except self.s3_client.exceptions.ClientError:
            return False
        except Exception as e:
            logger.error(f"Error checking artifact {artifact_id} existence: {e}")
            return False


class NullArtifactStore(ArtifactStore):
    """
    Null implementation for CLI context where S3 is not available.

    Always returns None/False, allowing metrics to gracefully degrade.
    """

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Always returns None (no storage available)."""
        return None

    def artifact_exists(self, artifact_id: str) -> bool:
        """Always returns False (no storage available)."""
        return False


def get_artifact_store() -> ArtifactStore:
    """
    Factory function to get appropriate artifact store for current context.

    Returns:
        S3ArtifactStore if ARTIFACTS_BUCKET env var is set (Lambda context),
        otherwise NullArtifactStore (CLI context)
    """
    bucket_name = os.environ.get("ARTIFACTS_BUCKET")
    if bucket_name:
        logger.debug(f"Using S3ArtifactStore with bucket: {bucket_name}")
        return S3ArtifactStore(bucket_name)
    else:
        logger.debug("Using NullArtifactStore (no S3 access)")
        return NullArtifactStore()
