"""Manual tests for resetting the registry."""

import json
from typing import Optional

import requests

from api_config import require_api_base_url


def test_reset_registry(
    api_base_url: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> None:
    """Test the DELETE /reset endpoint."""

    if api_base_url is None:
        api_base_url = require_api_base_url()

    endpoint = f"{api_base_url}/reset"

    headers = {}
    if auth_token:
        headers["X-Authorization"] = auth_token

    print(f"\n{'=' * 60}")
    print("Testing: DELETE /reset")
    print(f"Endpoint: {endpoint}")
    print(f"{'=' * 60}")
    print("\n⚠ WARNING: This will delete ALL artifacts from the registry!")

    try:
        response = requests.delete(
            endpoint,
            headers=headers,
            timeout=30,
        )

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        try:
            response_json = response.json()
            print("\nResponse Body:")
            print(json.dumps(response_json, indent=2))
        except json.JSONDecodeError:
            response_json = None
            print("\nResponse Body (raw):")
            print(response.text)

        if response.status_code == 200:
            print("\n✓ SUCCESS: Registry reset successfully!")
            if response_json and "deleted_artifacts" in response_json:
                deleted_count = response_json["deleted_artifacts"]
                print(f"  Deleted {deleted_count} artifact(s)")
        elif response.status_code == 500:
            print("\n✗ ERROR: Failed to reset registry storage")
        else:
            print(f"\n✗ ERROR: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out")
    except requests.exceptions.ConnectionError as exc:
        print("\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n✗ ERROR: {exc}")

