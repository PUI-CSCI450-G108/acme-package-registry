"""Helpers for manual artifact-related API tests."""

import json
from typing import Optional

import requests

from api_config import API_BASE_URL


def test_artifact_endpoint(
    artifact_type: str,
    url: str,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None,
) -> None:
    """Test the POST /artifact/{artifact_type} endpoint."""

    endpoint = f"{api_base_url}/artifact/{artifact_type}"

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = auth_token

    payload = {"url": url}

    print(f"\n{'=' * 60}")
    print(f"Testing: POST /artifact/{artifact_type}")
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'=' * 60}")

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=300,
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

        if response.status_code == 201:
            print("\n✓ SUCCESS: Artifact registered successfully!")
            if response_json and "metadata" in response_json:
                artifact_id = response_json["metadata"].get("id")
                print(f"  Artifact ID: {artifact_id}")
                print(f"  Name: {response_json['metadata'].get('name')}")
                print(f"  Type: {response_json['metadata'].get('type')}")
        elif response.status_code == 409:
            print("\n⚠ WARNING: Artifact already exists")
        elif response.status_code == 424:
            print("\n✗ FAILED: Artifact rating too low (below minimum threshold)")
        elif response.status_code == 400:
            print("\n✗ ERROR: Bad request - check your input")
        else:
            print(f"\n✗ ERROR: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out (this is normal for large models)")
    except requests.exceptions.ConnectionError as exc:
        print("\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n✗ ERROR: {exc}")


def test_rate_endpoint(
    artifact_id: str,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None,
) -> None:
    """Test the GET /artifact/model/{id}/rate endpoint."""

    endpoint = f"{api_base_url}/artifact/model/{artifact_id}/rate"

    headers = {}
    if auth_token:
        headers["X-Authorization"] = auth_token

    print(f"\n{'=' * 60}")
    print(f"Testing: GET /artifact/model/{artifact_id}/rate")
    print(f"Endpoint: {endpoint}")
    print(f"{'=' * 60}")

    try:
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=300,
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
            print("\n✓ SUCCESS: Rating retrieved successfully!")
            if response_json and "data" in response_json:
                rating = response_json["data"]
                print(f"  Net Score: {rating.get('net_score')}")
                print(f"  Bus Factor: {rating.get('bus_factor')}")
                print(f"  Code Quality: {rating.get('code_quality')}")
                print(f"  Ramp Up: {rating.get('ramp_up')}")
                print(f"  License: {rating.get('license')}")
        elif response.status_code == 404:
            print("\n✗ ERROR: Artifact not found")
        elif response.status_code == 400:
            print("\n✗ ERROR: Bad request - check your input")
        else:
            print(f"\n✗ ERROR: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out (this is normal for large models)")
    except requests.exceptions.ConnectionError as exc:
        print("\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n✗ ERROR: {exc}")


def test_create_and_rate(
    artifact_type: str,
    url: str,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None,
) -> None:
    """Create an artifact and then retrieve its rating."""

    create_endpoint = f"{api_base_url}/artifact/{artifact_type}"

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["X-Authorization"] = auth_token

    payload = {"url": url}

    print(f"\n{'=' * 60}")
    print("STEP 1: Create Artifact")
    print(f"Testing: POST /artifact/{artifact_type}")
    print(f"Endpoint: {create_endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'=' * 60}")

    artifact_id: Optional[str] = None
    response_json: Optional[dict] = None

    try:
        response = requests.post(
            create_endpoint,
            headers=headers,
            json=payload,
            timeout=300,
        )

        print(f"\nStatus Code: {response.status_code}")

        try:
            response_json = response.json()
            print("\nResponse Body:")
            print(json.dumps(response_json, indent=2))

            if response.status_code == 201:
                print("\n✓ SUCCESS: Artifact created successfully!")
                if "metadata" in response_json:
                    artifact_id = response_json["metadata"].get("id")
                    print(f"  Artifact ID: {artifact_id}")
                    print(f"  Name: {response_json['metadata'].get('name')}")
                    print(f"  Type: {response_json['metadata'].get('type')}")
            elif response.status_code == 409:
                print("\n⚠ WARNING: Artifact already exists")
                if "metadata" in response_json:
                    artifact_id = response_json["metadata"].get("id")
                    print(f"  Artifact ID: {artifact_id}")
            elif response.status_code == 424:
                print("\n✗ FAILED: Artifact rating too low (below minimum threshold)")
                print("  Cannot proceed with rate test - artifact was not registered")
                return
            else:
                print(f"\n✗ ERROR: Unexpected status code {response.status_code}")
                print("  Cannot proceed with rate test")
                return

        except json.JSONDecodeError:
            print("\nResponse Body (raw):")
            print(response.text)
            print("\n✗ ERROR: Failed to parse response")
            return

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out")
        return
    except requests.exceptions.ConnectionError as exc:
        print("\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {exc}")
        return
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n✗ ERROR: {exc}")
        return

    artifact_name: Optional[str] = None
    if response_json and "metadata" in response_json:
        artifact_name = response_json["metadata"].get("name")

    if not artifact_id:
        artifact_name = artifact_name or (url.split("/")[-1] if "/" in url else None)

        if artifact_name:
            print(f"\n{'=' * 60}")
            print("STEP 2: Get Artifact ID by Name")
            print(f"{'=' * 60}")

            byname_endpoint = f"{api_base_url}/artifact/byName/{artifact_name}"

            byname_headers = {}
            if auth_token:
                byname_headers["X-Authorization"] = auth_token

            try:
                byname_response = requests.get(
                    byname_endpoint,
                    headers=byname_headers,
                    timeout=10,
                )

                print(f"\nStatus Code: {byname_response.status_code}")

                if byname_response.status_code == 200:
                    byname_json = byname_response.json()
                    print("\nResponse Body:")
                    print(json.dumps(byname_json, indent=2))

                    if byname_json and len(byname_json) > 0:
                        artifact_id = byname_json[0].get("id")
                        print(f"\n✓ SUCCESS: Retrieved artifact ID: {artifact_id}")
                else:
                    print("\n✗ ERROR: Could not retrieve artifact by name")

            except Exception as exc:  # pylint: disable=broad-except
                print(f"\n✗ ERROR: {exc}")

    if artifact_id:
        print(f"\n{'=' * 60}")
        print("STEP 3: Get Artifact Rating")
        print(f"{'=' * 60}")
        test_rate_endpoint(artifact_id, api_base_url, auth_token)
    else:
        print("\n✗ ERROR: Could not retrieve artifact ID, skipping rate test")

