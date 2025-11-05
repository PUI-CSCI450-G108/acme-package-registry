"""Manual tests for listing artifacts."""

import json
from typing import List, Optional

import requests

from api_config import API_BASE_URL


def test_list_artifacts(
    queries: List[dict],
    offset: Optional[int] = None,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None,
) -> None:
    """Test the POST /artifacts endpoint."""

    endpoint = f"{api_base_url}/artifacts"
    if offset is not None:
        endpoint += f"?offset={offset}"

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["X-Authorization"] = auth_token

    print(f"\n{'=' * 60}")
    print("Testing: POST /artifacts")
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {json.dumps(queries, indent=2)}")
    print(f"{'=' * 60}")

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=queries,
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
            print("\n✓ SUCCESS: Artifacts retrieved successfully!")
            if isinstance(response_json, list):
                print(f"  Found {len(response_json)} artifact(s)")
                for artifact in response_json:
                    print(
                        "    - "
                        f"{artifact.get('name')} (v{artifact.get('version')}) "
                        f"- Type: {artifact.get('type')}"
                    )

                if "offset" in response.headers:
                    print(f"  Next offset: {response.headers['offset']}")
        elif response.status_code == 400:
            print("\n✗ ERROR: Bad request - check your query format")
        elif response.status_code == 413:
            print("\n✗ ERROR: Too many artifacts returned")
        else:
            print(f"\n✗ ERROR: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out")
    except requests.exceptions.ConnectionError as exc:
        print("\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n✗ ERROR: {exc}")

