#!/usr/bin/env python3
"""
Local test script for Lambda handlers.

Run this to test Lambda functions locally without deploying to AWS:
    python test_lambda_local.py
"""

import json
from lambda_handlers import create_artifact, rate_artifact, health_check


def test_create_artifact():
    """Test POST /artifact/model"""
    print("=" * 60)
    print("TEST 1: Create Artifact (POST /artifact/model)")
    print("=" * 60)

    event = {
        "httpMethod": "POST",
        "pathParameters": {"artifact_type": "model"},
        "body": json.dumps({"url": "https://huggingface.co/gpt2"}),
        "headers": {"Content-Type": "application/json"}
    }

    print(f"\nRequest: POST /artifact/model")
    print(f"Body: {event['body']}")

    response = create_artifact(event, None)

    print(f"\nResponse Status: {response['statusCode']}")

    if response['statusCode'] == 201:
        body = json.loads(response['body'])
        print(f"✅ SUCCESS - Artifact registered!")
        print(f"\nArtifact Metadata:")
        print(f"  ID: {body['metadata']['id']}")
        print(f"  Name: {body['metadata']['name']}")
        print(f"  Version: {body['metadata']['version']}")
        print(f"  Type: {body['metadata']['type']}")
        return body['metadata']['id']
    else:
        body = json.loads(response['body'])
        print(f"❌ FAILED")
        print(f"Error: {body.get('error', 'Unknown error')}")
        return None


def test_rate_artifact(artifact_id: str):
    """Test GET /artifact/model/{id}/rate"""
    print("\n" + "=" * 60)
    print(f"TEST 2: Rate Artifact (GET /artifact/model/{artifact_id}/rate)")
    print("=" * 60)

    event = {
        "httpMethod": "GET",
        "pathParameters": {"id": artifact_id},
        "headers": {}
    }

    print(f"\nRequest: GET /artifact/model/{artifact_id}/rate")

    response = rate_artifact(event, None)

    print(f"\nResponse Status: {response['statusCode']}")

    if response['statusCode'] == 200:
        body = json.loads(response['body'])
        print(f"✅ SUCCESS - Rating retrieved!")
        print(f"\nModel Rating:")
        print(f"  Name: {body['name']}")
        print(f"  Category: {body['category']}")
        print(f"  Net Score: {body['net_score']:.3f}")
        print(f"\nPhase 1 Metrics:")
        print(f"  License: {body['license']:.3f}")
        print(f"  Bus Factor: {body['bus_factor']:.3f}")
        print(f"  Ramp Up Time: {body['ramp_up_time']:.3f}")
        print(f"  Code Quality: {body['code_quality']:.3f}")
        print(f"  Performance Claims: {body['performance_claims']:.3f}")
        print(f"\nPhase 2 Metrics:")
        print(f"  Reproducibility: {body['reproducibility']:.3f}")
        print(f"  Reviewedness: {body['reviewedness']:.3f}")
        print(f"  Tree Score: {body['tree_score']:.3f}")
        print(f"\nSize Scores:")
        print(f"  Raspberry Pi: {body['size_score']['raspberry_pi']:.3f}")
        print(f"  Jetson Nano: {body['size_score']['jetson_nano']:.3f}")
        print(f"  Desktop PC: {body['size_score']['desktop_pc']:.3f}")
        print(f"  AWS Server: {body['size_score']['aws_server']:.3f}")
        print(f"\nLatencies (seconds):")
        print(f"  Net Score: {body['net_score_latency']:.3f}s")
        print(f"  License: {body['license_latency']:.3f}s")
        return True
    else:
        body = json.loads(response['body'])
        print(f"❌ FAILED")
        print(f"Error: {body.get('error', 'Unknown error')}")
        return False


def test_duplicate_artifact():
    """Test duplicate registration (should fail with 409)"""
    print("\n" + "=" * 60)
    print("TEST 3: Duplicate Registration (expect 409)")
    print("=" * 60)

    event = {
        "httpMethod": "POST",
        "pathParameters": {"artifact_type": "model"},
        "body": json.dumps({"url": "https://huggingface.co/gpt2"}),
        "headers": {"Content-Type": "application/json"}
    }

    print(f"\nRequest: POST /artifact/model (duplicate)")
    print(f"Body: {event['body']}")

    response = create_artifact(event, None)

    print(f"\nResponse Status: {response['statusCode']}")

    if response['statusCode'] == 409:
        print(f"✅ SUCCESS - Correctly rejected duplicate (409)")
        return True
    else:
        print(f"⚠️  WARNING - Expected 409, got {response['statusCode']}")
        return False


def test_health_check():
    """Test GET /health"""
    print("\n" + "=" * 60)
    print("TEST 4: Health Check (GET /health)")
    print("=" * 60)

    event = {
        "httpMethod": "GET",
        "pathParameters": {},
        "headers": {}
    }

    print(f"\nRequest: GET /health")

    response = health_check(event, None)

    print(f"\nResponse Status: {response['statusCode']}")

    if response['statusCode'] == 200:
        body = json.loads(response['body'])
        print(f"✅ SUCCESS - Service healthy!")
        print(f"  Status: {body['status']}")
        print(f"  Service: {body['service']}")
        print(f"  Artifacts Count: {body['artifacts_count']}")
        return True
    else:
        print(f"❌ FAILED")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("LAMBDA HANDLER LOCAL TESTS")
    print("=" * 60)
    print("\nTesting Lambda handlers without AWS deployment...")
    print("This simulates how API Gateway would call your functions.\n")

    results = []

    # Test 1: Create artifact
    artifact_id = test_create_artifact()
    results.append(("Create Artifact", artifact_id is not None))

    if artifact_id:
        # Test 2: Rate artifact
        success = test_rate_artifact(artifact_id)
        results.append(("Rate Artifact", success))

        # Test 3: Duplicate check
        success = test_duplicate_artifact()
        results.append(("Duplicate Check", success))
    else:
        print("\n⚠️  Skipping tests 2 & 3 due to failed artifact creation")
        results.append(("Rate Artifact", False))
        results.append(("Duplicate Check", False))

    # Test 4: Health check
    success = test_health_check()
    results.append(("Health Check", success))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
