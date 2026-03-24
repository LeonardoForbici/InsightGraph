"""
Manual Test Script for CodeQL Results Endpoints

This script tests the new CodeQL results endpoints manually.
Run this after starting the backend server.

Usage:
    python test_results_endpoints_manual.py
"""

import requests
import json

BASE_URL = "http://localhost:8000"


def test_health_endpoint():
    """Test the health endpoint includes CodeQL CLI status."""
    print("\n=== Testing /api/health ===")
    response = requests.get(f"{BASE_URL}/api/health")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"CodeQL CLI: {data.get('codeql_cli')}")
    print(f"CodeQL Version: {data.get('codeql_version')}")
    print(f"Response: {json.dumps(data, indent=2)}")
    return response.status_code == 200


def test_codeql_config():
    """Test the CodeQL configuration endpoint."""
    print("\n=== Testing /api/codeql/config ===")
    response = requests.get(f"{BASE_URL}/api/codeql/config")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    return response.status_code == 200


def test_node_vulnerabilities():
    """Test retrieving vulnerabilities for a node."""
    print("\n=== Testing /api/codeql/vulnerabilities/{node_key} ===")
    
    # Use a test node key (this will return empty if no vulnerabilities exist)
    node_key = "test:node:key"
    response = requests.get(f"{BASE_URL}/api/codeql/vulnerabilities/{node_key}")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Vulnerabilities found: {data.get('count', 0)}")
    print(f"Response: {json.dumps(data, indent=2)}")
    return response.status_code == 200


def test_sarif_download_not_found():
    """Test downloading SARIF file for non-existent job."""
    print("\n=== Testing /api/codeql/sarif/{job_id} (not found) ===")
    
    job_id = "nonexistent-job-id"
    response = requests.get(f"{BASE_URL}/api/codeql/sarif/{job_id}")
    print(f"Status: {response.status_code}")
    if response.status_code == 404:
        print(f"Expected 404: {response.json()}")
        return True
    return False


def test_sarif_delete_not_found():
    """Test deleting SARIF file for non-existent job."""
    print("\n=== Testing DELETE /api/codeql/sarif/{job_id} (not found) ===")
    
    job_id = "nonexistent-job-id"
    response = requests.delete(f"{BASE_URL}/api/codeql/sarif/{job_id}")
    print(f"Status: {response.status_code}")
    if response.status_code == 404:
        print(f"Expected 404: {response.json()}")
        return True
    return False


def main():
    """Run all manual tests."""
    print("=" * 60)
    print("Manual Test Suite for CodeQL Results Endpoints")
    print("=" * 60)
    
    tests = [
        ("Health Endpoint", test_health_endpoint),
        ("CodeQL Config", test_codeql_config),
        ("Node Vulnerabilities", test_node_vulnerabilities),
        ("SARIF Download (404)", test_sarif_download_not_found),
        ("SARIF Delete (404)", test_sarif_delete_not_found),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"ERROR: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")


if __name__ == "__main__":
    main()
