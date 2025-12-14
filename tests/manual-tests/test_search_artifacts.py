import json
from typing import Optional

import requests

from api_config import API_BASE_URL


def test_search_endpoint(
    regex: str,
    *,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None,
) -> None:
    """Test the POST /artifact/byRegEx endpoint."""

    endpoint = f"{api_base_url}/artifact/byRegEx"

    headers = {"Content-Type": "application/json"}
    # Use whichever header your gateway expects; keeping both patterns you've used
    if auth_token:
        headers["Authorization"] = auth_token
        headers["X-Authorization"] = auth_token

    payload = {
        "regex": regex,
    }

    print(f"\n{'=' * 60}")
    print("Testing: POST /artifact/byRegEx")
    print(f"Endpoint: {endpoint}")
    print("Payload:")
    print(json.dumps(payload, indent=2))
    print(f"{'=' * 60}")

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=60,
        )

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        # Try to parse JSON
        try:
            response_json = response.json()
            print("\nResponse Body:")
            print(json.dumps(response_json, indent=2))
        except json.JSONDecodeError:
            response_json = None
            print("\nResponse Body (raw):")
            print(response.text)

        # Status handling similar to your style
        if response.status_code == 200:
            print("\n✓ SUCCESS: Search returned results!")
            if isinstance(response_json, list):
                print(f"  Matches: {len(response_json)}")
                # Print a few key fields if present
                for i, item in enumerate(response_json[:10], start=1):
                    mid = (item.get("id") if isinstance(item, dict) else None)
                    mname = (item.get("name") if isinstance(item, dict) else None)
                    mtype = (item.get("type") if isinstance(item, dict) else None)
                    print(f"   {i:>2}. id={mid} | name={mname} | type={mtype}")
                if len(response_json) > 10:
                    print(f"  ...and {len(response_json) - 10} more")
        elif response.status_code == 404:
            print("\n✗ INFO: No artifact found under this regex")
        elif response.status_code == 400:
            print("\n✗ ERROR: Bad request - check your regex pattern")
            print("  Note: Catastrophic backtracking patterns like (a|aa)*$ will timeout")
        else:
            print(f"\n✗ ERROR: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out")
    except requests.exceptions.ConnectionError as exc:
        print("\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n✗ ERROR: {exc}")
