"""
Manual integration test for the GET /tracks endpoint.

This test validates the /tracks endpoint against a live API deployment.
"""

import json
from typing import Optional

import requests

from api_config import API_BASE_URL


def test_tracks_endpoint(api_base_url: Optional[str] = None) -> None:
    """
    Test the GET /tracks endpoint.

    Args:
        api_base_url: Optional API base URL. If None, uses API_BASE_URL from config.
    """
    if api_base_url is None:
        api_base_url = API_BASE_URL

    endpoint = f"{api_base_url}/tracks"

    print(f"\n{'=' * 60}")
    print("Testing: GET /tracks")
    print(f"Endpoint: {endpoint}")
    print(f"{'=' * 60}")

    try:
        response = requests.get(endpoint, timeout=10)
        print(f"\nStatus Code: {response.status_code}")

        # Print headers
        print("\nResponse Headers:")
        for header, value in response.headers.items():
            print(f"  {header}: {value}")

        # Parse and print response body
        response_json = response.json()
        print("\nResponse Body:")
        print(json.dumps(response_json, indent=2))

        # Validate response
        if response.status_code == 200:
            if "plannedTracks" in response_json:
                tracks = response_json["plannedTracks"]
                if tracks == ["Access control track"]:
                    print("\n✓ SUCCESS: Correct track returned!")
                    print(f"  Expected: ['Access control track']")
                    print(f"  Received: {tracks}")
                else:
                    print(f"\n✗ ERROR: Unexpected tracks returned")
                    print(f"  Expected: ['Access control track']")
                    print(f"  Received: {tracks}")
            else:
                print("\n✗ ERROR: Missing 'plannedTracks' key in response")
        else:
            print(f"\n✗ ERROR: Expected status code 200, got {response.status_code}")

        # Validate CORS headers
        print("\nCORS Validation:")
        if "access-control-allow-origin" in response.headers:
            print("  ✓ Access-Control-Allow-Origin header present")
        else:
            print("  ✗ Access-Control-Allow-Origin header missing")

    except requests.exceptions.RequestException as exc:
        print(f"\n✗ REQUEST ERROR: {exc}")
    except json.JSONDecodeError as exc:
        print(f"\n✗ JSON DECODE ERROR: {exc}")
        print(f"Response text: {response.text}")
    except Exception as exc:
        print(f"\n✗ UNEXPECTED ERROR: {exc}")


if __name__ == "__main__":
    test_tracks_endpoint()
