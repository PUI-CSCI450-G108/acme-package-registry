"""
Unit tests for the /tracks endpoint handler.
"""

import json
from unittest.mock import Mock

import pytest

from lambda_handlers.tracks import PLANNED_TRACKS, handler


def test_get_tracks_returns_200():
    """Test that GET /tracks returns 200 status code."""
    event = {"httpMethod": "GET", "headers": {}}
    context = Mock()

    response = handler(event, context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "plannedTracks" in body
    assert isinstance(body["plannedTracks"], list)


def test_get_tracks_returns_access_control_track():
    """Test that GET /tracks returns the correct track."""
    event = {"httpMethod": "GET", "headers": {}}
    context = Mock()

    response = handler(event, context)
    body = json.loads(response["body"])

    assert body["plannedTracks"] == ["Access control track"]
    assert len(body["plannedTracks"]) == 1


def test_get_tracks_matches_constant():
    """Test that the response matches the PLANNED_TRACKS constant."""
    event = {"httpMethod": "GET", "headers": {}}
    context = Mock()

    response = handler(event, context)
    body = json.loads(response["body"])

    assert body["plannedTracks"] == PLANNED_TRACKS


def test_options_preflight():
    """Test that OPTIONS preflight request returns 200 with CORS headers."""
    event = {"httpMethod": "OPTIONS", "headers": {}}
    context = Mock()

    response = handler(event, context)

    assert response["statusCode"] == 200
    assert "Access-Control-Allow-Origin" in response["headers"]
    assert "Access-Control-Allow-Methods" in response["headers"]


def test_cors_headers_present():
    """Test that CORS headers are present in the response."""
    event = {"httpMethod": "GET", "headers": {}}
    context = Mock()

    response = handler(event, context)

    assert "Access-Control-Allow-Origin" in response["headers"]
    assert response["headers"]["Content-Type"] == "application/json"
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_response_body_is_valid_json():
    """Test that the response body is valid JSON."""
    event = {"httpMethod": "GET", "headers": {}}
    context = Mock()

    response = handler(event, context)

    # Should not raise an exception
    body = json.loads(response["body"])
    assert isinstance(body, dict)
