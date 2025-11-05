#!/usr/bin/env python3
"""Command line helpers for manually exercising the ACME API."""

import json
import sys

from api_artifacts import test_create_and_rate
from api_config import (
    CONFIG_FILE_PATH,
    TEST_URLS,
    is_placeholder,
    require_api_base_url,
    set_api_base_url,
)
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


def _prompt_for_api_base_url() -> str:
    """Interactively ask the user for the API base URL and persist it."""

    if not sys.stdin.isatty():
        raise RuntimeError(
            "API base URL is not configured. Set the API_BASE_URL environment variable "
            f"or add your URL to {CONFIG_FILE_PATH.name}."
        )

    print("\nPlease provide the full API Gateway URL, e.g.")
    print("  https://abc123xyz.execute-api.us-east-1.amazonaws.com/dev")

    while True:
        try:
            entered = input("\nAPI base URL: ").strip()
        except EOFError as exc:  # pragma: no cover - interactive convenience
            raise RuntimeError(
                "Input closed before the API base URL was provided. "
                "Set API_BASE_URL or update the configuration file manually."
            ) from exc

        if not entered:
            print("\n✗ ERROR: API base URL cannot be empty.")
            continue

        try:
            set_api_base_url(entered)
        except ValueError as exc:
            print(f"\n✗ ERROR: {exc}")
            continue

        print(f"\n✓ Saved API base URL to {CONFIG_FILE_PATH}")
        return entered


def _resolve_api_base_url() -> str:
    """Fetch the configured API base URL, prompting if necessary."""

    try:
        return require_api_base_url()
    except RuntimeError as exc:
        print(f"\n⚠ WARNING: {exc}")
        print(
            "You can either set the API_BASE_URL environment variable or store the URL in "
            f"{CONFIG_FILE_PATH.name}."
        )
        return _prompt_for_api_base_url()


def _run_comprehensive_suite(api_base_url: str) -> None:
    print("\nRunning comprehensive test suite...")

    test_health_endpoint(api_base_url=api_base_url)

    print("\n" + "=" * 60)
    print("TEST 1: Create Model Artifact")
    print("=" * 60)
    test_create_and_rate("model", TEST_URLS["model"], api_base_url=api_base_url)

    print("\n" + "=" * 60)
    print("TEST 2: List All Artifacts")
    print("=" * 60)
    test_list_artifacts([{"name": "*"}], api_base_url=api_base_url)

    print("\n" + "=" * 60)
    print("TEST 3: Query Specific Artifact")
    print("=" * 60)
    test_list_artifacts(
        [{"name": "gpt2", "types": ["model"]}],
        api_base_url=api_base_url,
    )


def main() -> None:
    """Main entrypoint for manual API tests."""

    print("=" * 60)
    print("ACME Package Registry API Test Script")
    print("=" * 60)

    try:
        base_url = _resolve_api_base_url()
    except RuntimeError as exc:
        print(f"\n✗ ERROR: {exc}")
        sys.exit(1)

    if is_placeholder(base_url):
        print("\n✗ ERROR: API base URL is still using the placeholder value.")
        print("  Update the value and re-run the script.")
        sys.exit(1)

    if len(sys.argv) <= 1:
        print("\nNo command specified. Running comprehensive test suite...")
        print("Use 'python test_api.py health|list|reset|model|dataset|code|all' for specific tests\n")
        _run_comprehensive_suite(base_url)
        print("\n" + "=" * 60)
        print("Test completed!")
        print("=" * 60)
        return

    command = sys.argv[1]

    if command == "health":
        test_health_endpoint(api_base_url=base_url)
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

        test_list_artifacts(queries, offset, api_base_url=base_url)
    elif command == "reset":
        test_reset_registry(api_base_url=base_url)
    elif command in ["model", "dataset", "code"]:
        artifact_type = command
        url = sys.argv[2] if len(sys.argv) > 2 else TEST_URLS.get(artifact_type)

        if not url:
            print(f"\n✗ ERROR: No URL provided for artifact type '{artifact_type}'")
            print(f"  Usage: python test_api.py {artifact_type} <url>")
            sys.exit(1)

        test_health_endpoint(api_base_url=base_url)
        test_create_and_rate(artifact_type, url, api_base_url=base_url)
    elif command == "all":
        _run_comprehensive_suite(base_url)
    else:
        _print_usage()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()

