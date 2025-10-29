#!/usr/bin/env python3
"""
Simple script to test the AWS deployed ACME Package Registry API
Tests the /artifact/{artifact_type} endpoint
"""

import requests
import json
import sys
from typing import Optional

# Configuration - UPDATE THIS with your actual API Gateway URL
API_BASE_URL = "https://s9fj0wjsih.execute-api.us-east-1.amazonaws.com/dev"

# Example URLs to test with
TEST_URLS = {
    "model": "https://huggingface.co/gpt2",
    "dataset": "https://huggingface.co/datasets/wikitext",
    "code": "https://github.com/huggingface/transformers"
}


def test_artifact_endpoint(
    artifact_type: str,
    url: str,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None
) -> None:
    """
    Test the POST /artifact/{artifact_type} endpoint

    Args:
        artifact_type: One of "model", "dataset", or "code"
        url: URL of the artifact to register
        api_base_url: Base URL of your API Gateway
        auth_token: Optional authorization token
    """
    endpoint = f"{api_base_url}/artifact/{artifact_type}"

    headers = {
        "Content-Type": "application/json"
    }

    if auth_token:
        headers["X-Authorization"] = auth_token

    payload = {
        "url": url
    }

    print(f"\n{'='*60}")
    print(f"Testing: POST /artifact/{artifact_type}")
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'='*60}")

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=300  # 5 minutes timeout for model evaluation
        )

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        try:
            response_json = response.json()
            print(f"\nResponse Body:")
            print(json.dumps(response_json, indent=2))
        except json.JSONDecodeError:
            print(f"\nResponse Body (raw):")
            print(response.text)

        # Check status
        if response.status_code == 201:
            print("\n✓ SUCCESS: Artifact registered successfully!")
            if "metadata" in response_json:
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
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")


def test_rate_endpoint(
    artifact_id: str,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None
) -> None:
    """
    Test the GET /artifact/model/{id}/rate endpoint

    Args:
        artifact_id: The ID of the artifact to rate
        api_base_url: Base URL of your API Gateway
        auth_token: Optional authorization token
    """
    endpoint = f"{api_base_url}/artifact/model/{artifact_id}/rate"

    headers = {}
    if auth_token:
        headers["X-Authorization"] = auth_token

    print(f"\n{'='*60}")
    print(f"Testing: GET /artifact/model/{artifact_id}/rate")
    print(f"Endpoint: {endpoint}")
    print(f"{'='*60}")

    try:
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=300  # 5 minutes timeout for model evaluation
        )

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        try:
            response_json = response.json()
            print(f"\nResponse Body:")
            print(json.dumps(response_json, indent=2))
        except json.JSONDecodeError:
            print(f"\nResponse Body (raw):")
            print(response.text)

        # Check status
        if response.status_code == 200:
            print("\n✓ SUCCESS: Rating retrieved successfully!")
            if "data" in response_json:
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
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")


def test_create_and_rate(
    artifact_type: str,
    url: str,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None
) -> None:
    """
    Test creating an artifact and then retrieving its rating

    Args:
        artifact_type: One of "model", "dataset", or "code"
        url: URL of the artifact to register
        api_base_url: Base URL of your API Gateway
        auth_token: Optional authorization token
    """
    # Step 1: Create the artifact
    create_endpoint = f"{api_base_url}/artifact/{artifact_type}"

    headers = {
        "Content-Type": "application/json"
    }

    if auth_token:
        headers["X-Authorization"] = auth_token

    payload = {
        "url": url
    }

    print(f"\n{'='*60}")
    print(f"STEP 1: Create Artifact")
    print(f"Testing: POST /artifact/{artifact_type}")
    print(f"Endpoint: {create_endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'='*60}")

    artifact_id = None

    try:
        response = requests.post(
            create_endpoint,
            headers=headers,
            json=payload,
            timeout=300  # 5 minutes timeout for model evaluation
        )

        print(f"\nStatus Code: {response.status_code}")

        try:
            response_json = response.json()
            print(f"\nResponse Body:")
            print(json.dumps(response_json, indent=2))

            # Extract artifact ID from response
            if response.status_code == 201:
                print("\n✓ SUCCESS: Artifact created successfully!")
                if "metadata" in response_json:
                    artifact_id = response_json["metadata"].get("id")
                    print(f"  Artifact ID: {artifact_id}")
                    print(f"  Name: {response_json['metadata'].get('name')}")
                    print(f"  Type: {response_json['metadata'].get('type')}")
            elif response.status_code == 409:
                print("\n⚠ WARNING: Artifact already exists")
                # Try to extract ID from existing artifact response
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
            print(f"\nResponse Body (raw):")
            print(response.text)
            print("\n✗ ERROR: Failed to parse response")
            return

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out")
        return
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {e}")
        return
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return

    # Step 2: If we don't have artifact_id from create, try byName endpoint
    artifact_name = None
    if not artifact_id:
        # Try to get artifact name from the response or extract from URL
        if "metadata" in response_json:
            artifact_name = response_json["metadata"].get("name")

        if not artifact_name:
            # Extract name from URL as fallback
            artifact_name = url.split("/")[-1] if "/" in url else None

        if artifact_name:
            print(f"\n{'='*60}")
            print(f"STEP 2: Get Artifact ID by Name")
            print(f"{'='*60}")

            byname_endpoint = f"{api_base_url}/artifact/byName/{artifact_name}"

            byname_headers = {}
            if auth_token:
                byname_headers["X-Authorization"] = auth_token

            try:
                byname_response = requests.get(
                    byname_endpoint,
                    headers=byname_headers,
                    timeout=10
                )

                print(f"\nStatus Code: {byname_response.status_code}")

                if byname_response.status_code == 200:
                    byname_json = byname_response.json()
                    print(f"\nResponse Body:")
                    print(json.dumps(byname_json, indent=2))

                    # Get the first artifact's ID
                    if byname_json and len(byname_json) > 0:
                        artifact_id = byname_json[0].get("id")
                        print(f"\n✓ SUCCESS: Retrieved artifact ID: {artifact_id}")
                else:
                    print(f"\n✗ ERROR: Could not retrieve artifact by name")

            except Exception as e:
                print(f"\n✗ ERROR: {e}")

    # Step 3: Test the rate endpoint if we have an artifact ID
    if artifact_id:
        print(f"\n{'='*60}")
        print(f"STEP 3: Get Artifact Rating")
        print(f"{'='*60}")
        test_rate_endpoint(artifact_id, api_base_url, auth_token)
    else:
        print("\n✗ ERROR: Could not retrieve artifact ID, skipping rate test")


def test_health_endpoint(api_base_url: str = API_BASE_URL) -> None:
    """Test the /health endpoint"""
    endpoint = f"{api_base_url}/health"

    print(f"\n{'='*60}")
    print(f"Testing: GET /health")
    print(f"Endpoint: {endpoint}")
    print(f"{'='*60}")

    try:
        response = requests.get(endpoint, timeout=10)
        print(f"\nStatus Code: {response.status_code}")

        try:
            response_json = response.json()
            print(f"\nResponse Body:")
            print(json.dumps(response_json, indent=2))

            if response.status_code == 200:
                print("\n✓ SUCCESS: API is healthy!")
        except json.JSONDecodeError:
            print(f"\nResponse Body (raw):")
            print(response.text)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")


def main():
    """Main test runner"""
    print("=" * 60)
    print("ACME Package Registry API Test Script")
    print("=" * 60)

    # Check if API URL is configured
    if "YOUR_API_ID" in API_BASE_URL:
        print("\n⚠ WARNING: Please update API_BASE_URL in this script with your actual API Gateway URL")
        print("  Example: https://abc123xyz.execute-api.us-east-1.amazonaws.com/dev")
        print("\nYou can find your API URL by running:")
        print("  aws cloudformation describe-stacks --stack-name acme-package-registry \\")
        print("    --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' --output text")
        sys.exit(1)

    # Test health endpoint first
    test_health_endpoint()

    # Get artifact type from command line or use default
    artifact_type = sys.argv[1] if len(sys.argv) > 1 else "model"
    url = sys.argv[2] if len(sys.argv) > 2 else TEST_URLS.get(artifact_type)

    if artifact_type not in ["model", "dataset", "code"]:
        print(f"\n✗ ERROR: Invalid artifact type '{artifact_type}'")
        print("  Valid types: model, dataset, code")
        sys.exit(1)

    if not url:
        print(f"\n✗ ERROR: No URL provided for artifact type '{artifact_type}'")
        sys.exit(1)

    # Test creating the artifact and then getting its rating
    test_create_and_rate(artifact_type, url)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
