"""
Test script for Task 12.5 — Tenant Management API

This script verifies that:
1. POST /api/admin/tenants creates tenants with admin token
2. GET /api/admin/tenants lists tenants
3. GET /api/admin/tenants/{id} retrieves specific tenant
4. DELETE /api/admin/tenants/{id} soft-deletes tenant
5. Admin token protection works correctly
"""

import os
import sys
import httpx

# Configuration
BASE_URL = os.getenv("INSIGHTGRAPH_URL", "http://localhost:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "test-admin-token-12345")

def test_create_tenant_without_token():
    """Test that creating tenant without admin token fails."""
    print("Testing tenant creation without admin token...")
    
    try:
        response = httpx.post(
            f"{BASE_URL}/api/admin/tenants",
            json={"name": "test-tenant", "display_name": "Test Tenant"}
        )
        
        if response.status_code == 401:
            print("✓ Unauthorized access blocked (401)")
            return True
        else:
            print(f"✗ Expected 401, got {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_create_tenant_with_invalid_token():
    """Test that creating tenant with invalid admin token fails."""
    print("\nTesting tenant creation with invalid admin token...")
    
    try:
        response = httpx.post(
            f"{BASE_URL}/api/admin/tenants",
            json={"name": "test-tenant", "display_name": "Test Tenant"},
            headers={"X-Admin-Token": "invalid-token"}
        )
        
        if response.status_code == 401:
            print("✓ Invalid token rejected (401)")
            return True
        else:
            print(f"✗ Expected 401, got {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_create_tenant():
    """Test creating a tenant with valid admin token."""
    print("\nTesting tenant creation with valid admin token...")
    
    try:
        response = httpx.post(
            f"{BASE_URL}/api/admin/tenants",
            json={"name": "test-tenant-1", "display_name": "Test Tenant 1"},
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response.status_code == 200:
            tenant = response.json()
            print(f"✓ Tenant created: {tenant['name']} (ID: {tenant['id']})")
            return tenant
        else:
            print(f"✗ Failed to create tenant: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def test_create_duplicate_tenant():
    """Test that creating duplicate tenant fails."""
    print("\nTesting duplicate tenant creation...")
    
    try:
        # Create first tenant
        response1 = httpx.post(
            f"{BASE_URL}/api/admin/tenants",
            json={"name": "test-tenant-dup", "display_name": "Duplicate Test"},
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        # Try to create duplicate
        response2 = httpx.post(
            f"{BASE_URL}/api/admin/tenants",
            json={"name": "test-tenant-dup", "display_name": "Duplicate Test 2"},
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response2.status_code == 409:
            print("✓ Duplicate tenant rejected (409)")
            return True
        else:
            print(f"✗ Expected 409, got {response2.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_create_tenant_invalid_name():
    """Test that invalid tenant names are rejected."""
    print("\nTesting invalid tenant name...")
    
    try:
        response = httpx.post(
            f"{BASE_URL}/api/admin/tenants",
            json={"name": "Test Tenant!", "display_name": "Invalid Name"},
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response.status_code == 422:
            print("✓ Invalid tenant name rejected (422)")
            return True
        else:
            print(f"✗ Expected 422, got {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_list_tenants():
    """Test listing all tenants."""
    print("\nTesting tenant listing...")
    
    try:
        response = httpx.get(
            f"{BASE_URL}/api/admin/tenants",
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response.status_code == 200:
            tenants = response.json()
            print(f"✓ Listed {len(tenants)} tenant(s)")
            for tenant in tenants:
                print(f"  - {tenant['name']} ({tenant['display_name']})")
            return tenants
        else:
            print(f"✗ Failed to list tenants: {response.status_code}")
            return []
    except Exception as e:
        print(f"✗ Error: {e}")
        return []


def test_get_tenant(tenant_id: str):
    """Test getting a specific tenant."""
    print(f"\nTesting get tenant by ID: {tenant_id}...")
    
    try:
        response = httpx.get(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}",
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response.status_code == 200:
            tenant = response.json()
            print(f"✓ Retrieved tenant: {tenant['name']}")
            return tenant
        else:
            print(f"✗ Failed to get tenant: {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def test_delete_tenant(tenant_id: str):
    """Test soft-deleting a tenant."""
    print(f"\nTesting tenant deletion: {tenant_id}...")
    
    try:
        response = httpx.delete(
            f"{BASE_URL}/api/admin/tenants/{tenant_id}",
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response.status_code == 200:
            print(f"✓ Tenant soft-deleted")
            return True
        else:
            print(f"✗ Failed to delete tenant: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_list_active_tenants_only():
    """Test listing only active tenants."""
    print("\nTesting active tenants filter...")
    
    try:
        response = httpx.get(
            f"{BASE_URL}/api/admin/tenants?active_only=true",
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response.status_code == 200:
            tenants = response.json()
            all_active = all(t['is_active'] for t in tenants)
            if all_active:
                print(f"✓ All {len(tenants)} tenant(s) are active")
                return True
            else:
                print(f"✗ Some tenants are not active")
                return False
        else:
            print(f"✗ Failed to list tenants: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def cleanup():
    """Clean up test tenants."""
    print("\nCleaning up test tenants...")
    
    try:
        # List all tenants
        response = httpx.get(
            f"{BASE_URL}/api/admin/tenants?active_only=false",
            headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        
        if response.status_code == 200:
            tenants = response.json()
            test_tenants = [t for t in tenants if t['name'].startswith('test-tenant')]
            
            for tenant in test_tenants:
                httpx.delete(
                    f"{BASE_URL}/api/admin/tenants/{tenant['id']}",
                    headers={"X-Admin-Token": ADMIN_TOKEN}
                )
            
            print(f"✓ Cleaned up {len(test_tenants)} test tenant(s)")
    except Exception as e:
        print(f"✗ Cleanup error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Task 12.5 — Tenant Management API Test")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin Token: {ADMIN_TOKEN[:10]}...")
    print()
    
    # Check if server is running
    try:
        response = httpx.get(f"{BASE_URL}/api/health", timeout=5)
        if response.status_code != 200:
            print("✗ Server is not responding correctly")
            sys.exit(1)
    except Exception as e:
        print(f"✗ Cannot connect to server: {e}")
        print(f"  Make sure the server is running at {BASE_URL}")
        sys.exit(1)
    
    print("✓ Server is running\n")
    
    # Run tests
    results = []
    
    results.append(("Unauthorized access blocked", test_create_tenant_without_token()))
    results.append(("Invalid token rejected", test_create_tenant_with_invalid_token()))
    results.append(("Invalid name rejected", test_create_tenant_invalid_name()))
    
    tenant = test_create_tenant()
    results.append(("Tenant creation", tenant is not None))
    
    results.append(("Duplicate tenant rejected", test_create_duplicate_tenant()))
    
    tenants = test_list_tenants()
    results.append(("Tenant listing", len(tenants) > 0))
    
    if tenant:
        retrieved = test_get_tenant(tenant['id'])
        results.append(("Get tenant by ID", retrieved is not None))
        
        deleted = test_delete_tenant(tenant['id'])
        results.append(("Tenant deletion", deleted))
    
    results.append(("Active tenants filter", test_list_active_tenants_only()))
    
    # Cleanup
    cleanup()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    sys.exit(0 if passed == total else 1)
