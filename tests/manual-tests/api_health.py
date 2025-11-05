"""Manual tests for the /health endpoint."""

import json
from typing import Optional

import requests

from api_config import API_BASE_URL


def test_health_endpoint(api_base_url: Optional[str] = None) -> None:
    """Test the GET /health endpoint."""

    if api_base_url is None:
        api_base_url = API_BASE_URL

    endpoint = f"{api_base_url}/health"

    print(f"\n{'=' * 60}")
    print("Testing: GET /health")
    print(f"Endpoint: {endpoint}")
    print(f"{'=' * 60}")

    try:
        response = requests.get(endpoint, timeout=10)
        print(f"\nStatus Code: {response.status_code}")

        try:
            response_json = response.json()
            print("\nResponse Body:")
            print(json.dumps(response_json, indent=2))

            if response.status_code == 200:
                print("\n✓ SUCCESS: API is healthy!")
        except json.JSONDecodeError:
            print("\nResponse Body (raw):")
            print(response.text)

    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n✗ ERROR: {exc}")

