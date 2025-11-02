#!/usr/bin/env python3
"""
Simple script to test the AWS deployed ACME Package Registry API

Supported endpoints:
- POST /artifact/{artifact_type} - Create a new artifact
- GET /artifact/model/{id}/rate - Get artifact ratings
- GET /artifact/byName/{name} - Get artifact by name
- GET /health - Health check
- POST /artifacts - List/query artifacts with pagination
- DELETE /reset - Reset the registry (delete all artifacts)
"""

import requests
import json
import sys
from typing import Optional
import os

# Configuration: Set your API Gateway URL via the API_BASE_URL environment variable
API_BASE_URL = os.getenv("API_BASE_URL")
if not API_BASE_URL:
    raise RuntimeError("API_BASE_URL environment variable is not set. Please set it to your API Gateway URL.")

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
        headers["Authorization"] = auth_token

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

def test_health_endpoint(api_base_url: Optional[str] = None) -> None:
    """Test the /health endpoint"""
    if api_base_url is None:
        api_base_url = API_BASE_URL
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


def test_list_artifacts(
    queries: list,
    offset: Optional[int] = None,
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None
) -> None:
    """
    Test the POST /artifacts endpoint (list/query artifacts)

    Args:
        queries: List of query dictionaries with 'name', optional 'types', and optional 'version'
        offset: Optional pagination offset
        api_base_url: Base URL of your API Gateway
        auth_token: Optional authorization token
    """
    endpoint = f"{api_base_url}/artifacts"
    if offset is not None:
        endpoint += f"?offset={offset}"

    headers = {
        "Content-Type": "application/json"
    }

    if auth_token:
        headers["X-Authorization"] = auth_token

    print(f"\n{'='*60}")
    print(f"Testing: POST /artifacts")
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {json.dumps(queries, indent=2)}")
    print(f"{'='*60}")

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=queries,
            timeout=30
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
            print("\n✓ SUCCESS: Artifacts retrieved successfully!")
            if isinstance(response_json, list):
                print(f"  Found {len(response_json)} artifact(s)")
                for artifact in response_json:
                    print(f"    - {artifact.get('name')} (v{artifact.get('version')}) - Type: {artifact.get('type')}")

                # Check for pagination header
                if 'offset' in response.headers:
                    print(f"  Next offset: {response.headers['offset']}")
        elif response.status_code == 400:
            print("\n✗ ERROR: Bad request - check your query format")
        elif response.status_code == 413:
            print("\n✗ ERROR: Too many artifacts returned")
        else:
            print(f"\n✗ ERROR: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out")
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")


def test_reset_registry(
    api_base_url: str = API_BASE_URL,
    auth_token: Optional[str] = None
) -> None:
    """
    Test the DELETE /reset endpoint

    Args:
        api_base_url: Base URL of your API Gateway
        auth_token: Optional authorization token
    """
    endpoint = f"{api_base_url}/reset"

    headers = {}
    if auth_token:
        headers["X-Authorization"] = auth_token

    print(f"\n{'='*60}")
    print(f"Testing: DELETE /reset")
    print(f"Endpoint: {endpoint}")
    print(f"{'='*60}")
    print("\n⚠ WARNING: This will delete ALL artifacts from the registry!")

    # Ask for confirmation in interactive mode
    if sys.stdout.isatty():
        confirm = input("Are you sure you want to continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("\n✗ CANCELLED: Reset operation aborted")
            return

    try:
        response = requests.delete(
            endpoint,
            headers=headers,
            timeout=30
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
            print("\n✓ SUCCESS: Registry reset successfully!")
            if "deleted_artifacts" in response_json:
                deleted_count = response_json["deleted_artifacts"]
                print(f"  Deleted {deleted_count} artifact(s)")
        elif response.status_code == 500:
            print("\n✗ ERROR: Failed to reset registry storage")
        else:
            print(f"\n✗ ERROR: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n✗ ERROR: Request timed out")
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ ERROR: Connection failed - check your API URL")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")


def main():
    """Main test runner"""
    print("=" * 60)
    print("ACME Package Registry API Test Script")
    print("=" * 60)

    # Check if API URL is configured
    if API_BASE_URL and "YOUR_API_ID" in API_BASE_URL:
        print("\n⚠ WARNING: Please update API_BASE_URL in this script with your actual API Gateway URL")
        print("  Example: https://abc123xyz.execute-api.us-east-1.amazonaws.com/dev")
        print("\nYou can find your API URL by running:")
        print("  aws cloudformation describe-stacks --stack-name acme-package-registry \\")
        print("    --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' --output text")
        sys.exit(1)

    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]

        # Test health endpoint
        if command == "health":
            test_health_endpoint()

        # Test list artifacts endpoint
        elif command == "list":
            # Example queries
            queries = [{"name": "*"}]
            if len(sys.argv) > 2:
                # Allow custom query from command line
                try:
                    queries = json.loads(sys.argv[2])
                except json.JSONDecodeError:
                    print("\n✗ ERROR: Invalid JSON for queries")
                    print("  Example: '[{\"name\": \"*\"}]'")
                    sys.exit(1)

            offset = None
            if len(sys.argv) > 3:
                try:
                    offset = int(sys.argv[3])
                except ValueError:
                    print("\n✗ ERROR: Offset must be an integer")
                    sys.exit(1)

            test_list_artifacts(queries, offset)

        # Test reset registry endpoint
        elif command == "reset":
            test_reset_registry()

        # Test create and rate workflow
        elif command in ["model", "dataset", "code"]:
            artifact_type = command
            url = sys.argv[2] if len(sys.argv) > 2 else TEST_URLS.get(artifact_type)

            if not url:
                print(f"\n✗ ERROR: No URL provided for artifact type '{artifact_type}'")
                print(f"  Usage: python test_api.py {artifact_type} <url>")
                sys.exit(1)

            # Test health endpoint first
            test_health_endpoint()

            # Test creating the artifact and then getting its rating
            test_create_and_rate(artifact_type, url)

        # Run comprehensive test suite
        elif command == "all":
            print("\nRunning comprehensive test suite...")

            # 1. Health check
            test_health_endpoint()

            # 2. Create a model artifact
            print("\n" + "=" * 60)
            print("TEST 1: Create Model Artifact")
            print("=" * 60)
            test_create_and_rate("model", TEST_URLS["model"])

            # 3. List all artifacts
            print("\n" + "=" * 60)
            print("TEST 2: List All Artifacts")
            print("=" * 60)
            test_list_artifacts([{"name": "*"}])

            # 4. List specific artifact
            print("\n" + "=" * 60)
            print("TEST 3: Query Specific Artifact")
            print("=" * 60)
            test_list_artifacts([{"name": "gpt2", "types": ["model"]}])

        # Show usage
        else:
            print("\nUsage:")
            print("  python test_api.py health                           # Test health endpoint")
            print("  python test_api.py list [queries] [offset]          # Test list artifacts endpoint")
            print("  python test_api.py reset                            # Test reset registry endpoint")
            print("  python test_api.py <type> <url>                     # Test create artifact and rate")
            print("  python test_api.py all                              # Run comprehensive test suite")
            print("\nExamples:")
            print('  python test_api.py list \'[{"name": "*"}]\'')
            print('  python test_api.py list \'[{"name": "gpt2", "types": ["model"]}]\'')
            print("  python test_api.py model https://huggingface.co/gpt2")
            print("\nArtifact types: model, dataset, code")
            sys.exit(1)
    else:
        # Default: run comprehensive test suite
        print("\nNo command specified. Running comprehensive test suite...")
        print("Use 'python test_api.py health|list|reset|model|dataset|code|all' for specific tests\n")

        # Test health endpoint
        test_health_endpoint()

        # Test creating a model artifact and getting its rating
        test_create_and_rate("model", TEST_URLS["model"])

        # Test listing artifacts
        print("\n" + "=" * 60)
        print("Testing List Artifacts Endpoint")
        print("=" * 60)
        test_list_artifacts([{"name": "*"}])

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
