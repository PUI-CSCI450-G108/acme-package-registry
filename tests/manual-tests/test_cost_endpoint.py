#!/usr/bin/env python3
"""Manual test for the artifact cost endpoint."""

import json
import sys

import requests

from api_config import API_BASE_URL


def test_cost_endpoint(artifact_type: str, artifact_id: str, include_dependencies: bool = False):
    """
    Test the GET /artifact/{artifact_type}/{id}/cost endpoint.

    Args:
        artifact_type: Type of artifact (model, dataset, or code)
        artifact_id: ID of the artifact
        include_dependencies: Whether to include dependency costs
    """
    print(f"\n{'=' * 60}")
    print(f"Testing Cost Endpoint")
    print(f"Artifact Type: {artifact_type}")
    print(f"Artifact ID: {artifact_id}")
    print(f"Include Dependencies: {include_dependencies}")
    print(f"{'=' * 60}\n")

    # Build the URL
    url = f"{API_BASE_URL}/artifact/{artifact_type}/{artifact_id}/cost"
    if include_dependencies:
        url += "?dependency=true"

    print(f"GET {url}")

    try:
        response = requests.get(url)
        print(f"\nStatus Code: {response.status_code}")

        try:
            data = response.json()
            print(f"\nResponse Body:")
            print(json.dumps(data, indent=2))

            # Validate the response structure
            if response.status_code == 200:
                if artifact_id in data:
                    cost_data = data[artifact_id]
                    if "total_cost" in cost_data:
                        print(f"\n✓ SUCCESS: Cost endpoint returned valid data")
                        print(f"  Total Cost: {cost_data['total_cost']} MB")

                        if include_dependencies and "standalone_cost" in cost_data:
                            print(f"  Standalone Cost: {cost_data['standalone_cost']} MB")
                    else:
                        print(f"\n✗ ERROR: Response missing 'total_cost' field")
                else:
                    print(f"\n✗ ERROR: Response missing artifact_id '{artifact_id}' as key")
            elif response.status_code == 404:
                print(f"\n✗ Artifact not found")
            elif response.status_code == 400:
                print(f"\n✗ Bad request - check artifact_type and artifact_id")
            else:
                print(f"\n✗ Unexpected status code")
        except json.JSONDecodeError:
            print(f"\n✗ ERROR: Response is not valid JSON")
            print(f"Response Text: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"\n✗ ERROR: Failed to connect to API: {e}")
        sys.exit(1)


def main():
    """Main entrypoint for manual cost endpoint test."""
    if len(sys.argv) < 3:
        print("\nUsage:")
        print("  python test_cost_endpoint.py <artifact_type> <artifact_id> [dependencies]")
        print("\nExamples:")
        print("  python test_cost_endpoint.py model 123456789")
        print("  python test_cost_endpoint.py model 123456789 true")
        print("\nArtifact types: model, dataset, code")
        sys.exit(1)

    artifact_type = sys.argv[1]
    artifact_id = sys.argv[2]
    include_dependencies = len(sys.argv) > 3 and sys.argv[3].lower() == "true"

    if artifact_type not in ["model", "dataset", "code"]:
        print(f"\n✗ ERROR: Invalid artifact_type '{artifact_type}'")
        print("Valid types: model, dataset, code")
        sys.exit(1)

    if not API_BASE_URL or "YOUR_API_ID" in API_BASE_URL:
        print("\n⚠ WARNING: Please update API_BASE_URL in api_config.py")
        print("  Example: https://abc123xyz.execute-api.us-east-1.amazonaws.com")
        sys.exit(1)

    test_cost_endpoint(artifact_type, artifact_id, include_dependencies)

    print(f"\n{'=' * 60}")
    print("Test completed!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
