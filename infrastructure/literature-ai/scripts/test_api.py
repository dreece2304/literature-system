#!/usr/bin/env python3
"""
Quick test script for literature-ai API endpoints.

Tests basic connectivity and response structure for all main endpoints.
"""

import sys
import requests
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://localhost:8002"


def test_endpoint(name: str, method: str, endpoint: str, data: dict = None):
    """Test a single endpoint."""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {method} {url}")

    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")

        print(f"Status: {response.status_code}")

        if response.status_code < 400:
            result = response.json()
            print(f"Response preview: {json.dumps(result, indent=2)[:500]}...")
            return True
        else:
            print(f"Error: {response.text[:200]}")
            return False

    except requests.exceptions.ConnectionRefused:
        print("❌ Connection refused - is the server running?")
        print("   Start it with: uvicorn src.api.main:app --host 0.0.0.0 --port 8002")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all endpoint tests."""
    print("="*60)
    print("Literature-AI API Test Suite")
    print("="*60)

    results = {}

    # System endpoints
    results["Root"] = test_endpoint(
        "Root", "GET", "/"
    )

    results["Health Check"] = test_endpoint(
        "Health Check", "GET", "/api/v1/health"
    )

    results["Stats"] = test_endpoint(
        "System Stats", "GET", "/api/v1/stats"
    )

    results["GPU Info"] = test_endpoint(
        "GPU Info", "GET", "/api/v1/gpu"
    )

    # Search endpoints
    results["Search Stats"] = test_endpoint(
        "Search Stats", "GET", "/api/v1/search/stats"
    )

    # Note: These will fail if no papers in DB, but that's expected
    results["Search Papers"] = test_endpoint(
        "Search Papers", "POST", "/api/v1/search/",
        data={
            "query": "machine learning",
            "top_k": 5
        }
    )

    # Context endpoints
    results["Current Context"] = test_endpoint(
        "Current Context", "GET", "/api/v1/context/current"
    )

    results["Context Stats"] = test_endpoint(
        "Context Stats", "GET", "/api/v1/context/stats"
    )

    # Writer endpoints (will fail without papers, but tests the endpoint)
    results["Citation Suggestions"] = test_endpoint(
        "Citation Suggestions", "POST", "/api/v1/writer/suggest-citations",
        data={
            "text": "Deep learning has revolutionized computer vision.",
            "n": 3
        }
    )

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {name}")

    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
