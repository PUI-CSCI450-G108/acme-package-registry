#!/usr/bin/env python3
"""Command line helpers for manually exercising the ACME API."""

import json
import sys

from api_artifacts import test_create_and_rate
from api_config import API_BASE_URL, TEST_URLS
from api_health import test_health_endpoint
from api_list import test_list_artifacts
from api_reset import test_reset_registry


def _print_usage() -> None:
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


def _run_comprehensive_suite() -> None:
    print("\nRunning comprehensive test suite...")

    test_health_endpoint()

    print("\n" + "=" * 60)
    print("TEST 1: Create Model Artifact")
    print("=" * 60)
    test_create_and_rate("model", TEST_URLS["model"])

    print("\n" + "=" * 60)
    print("TEST 2: List All Artifacts")
    print("=" * 60)
    test_list_artifacts([{"name": "*"}])

    print("\n" + "=" * 60)
    print("TEST 3: Query Specific Artifact")
    print("=" * 60)
    test_list_artifacts([{"name": "gpt2", "types": ["model"]}])


def main() -> None:
    """Main entrypoint for manual API tests."""

    print("=" * 60)
    print("ACME Package Registry API Test Script")
    print("=" * 60)

    if API_BASE_URL and "YOUR_API_ID" in API_BASE_URL:
        print("\n⚠ WARNING: Please update API_BASE_URL with your actual API Gateway URL")
        print("  Example: https://abc123xyz.execute-api.us-east-1.amazonaws.com/dev")
        sys.exit(1)

    if len(sys.argv) <= 1:
        print("\nNo command specified. Running comprehensive test suite...")
        print("Use 'python test_api.py health|list|reset|model|dataset|code|all' for specific tests\n")
        _run_comprehensive_suite()
        print("\n" + "=" * 60)
        print("Test completed!")
        print("=" * 60)
        return

    command = sys.argv[1]

    if command == "health":
        test_health_endpoint()
    elif command == "list":
        queries = [{"name": "*"}]
        if len(sys.argv) > 2:
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
    elif command == "reset":
        test_reset_registry()
    elif command in ["model", "dataset", "code"]:
        artifact_type = command
        url = sys.argv[2] if len(sys.argv) > 2 else TEST_URLS.get(artifact_type)

        if not url:
            print(f"\n✗ ERROR: No URL provided for artifact type '{artifact_type}'")
            print(f"  Usage: python test_api.py {artifact_type} <url>")
            sys.exit(1)

        test_health_endpoint()
        test_create_and_rate(artifact_type, url)
    elif command == "all":
        _run_comprehensive_suite()
    else:
        _print_usage()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()

