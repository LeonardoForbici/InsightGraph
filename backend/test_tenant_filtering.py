"""
Test script for Task 12.4 — Tenant field support in Neo4j nodes and query filtering.

This script verifies that:
1. Nodes are created with tenant field when TENANT_ID is set
2. Queries filter by tenant when tenant parameter is provided
3. Multi-tenant isolation works correctly
"""

import os
import sys

# Set test tenant ID
os.environ["TENANT_ID"] = "test-tenant-1"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USER"] = "neo4j"
os.environ["NEO4J_PASSWORD"] = "password"

# Import after setting environment variables
from main import neo4j_service, TENANT_ID

def test_tenant_field_in_nodes():
    """Test that nodes are created with tenant field."""
    print(f"Testing tenant field support...")
    print(f"TENANT_ID from environment: {TENANT_ID}")
    
    # Create a test node
    test_node = {
        "namespace_key": "test-tenant-1:test-project:TestClass",
        "name": "TestClass",
        "project": "test-project",
        "layer": "Service",
        "tenant": TENANT_ID
    }
    
    if neo4j_service.is_connected:
        try:
            neo4j_service.merge_node("Java_Class", test_node["namespace_key"], test_node)
            print(f"✓ Node created with tenant field: {TENANT_ID}")
            
            # Verify the node has tenant field
            query = "MATCH (n:Entity {namespace_key: $key}) RETURN n.tenant AS tenant"
            result = neo4j_service.graph.run(query, key=test_node["namespace_key"]).data()
            
            if result and result[0]["tenant"] == TENANT_ID:
                print(f"✓ Node tenant field verified: {result[0]['tenant']}")
            else:
                print(f"✗ Node tenant field not found or incorrect")
                
        except Exception as e:
            print(f"✗ Error creating node: {e}")
    else:
        print("✗ Neo4j not connected, skipping test")


def test_tenant_filtering_in_queries():
    """Test that queries filter by tenant correctly."""
    print(f"\nTesting tenant filtering in queries...")
    
    if not neo4j_service.is_connected:
        print("✗ Neo4j not connected, skipping test")
        return
    
    try:
        # Create nodes for two different tenants
        tenant1_node = {
            "namespace_key": "tenant1:project1:Class1",
            "name": "Class1",
            "project": "project1",
            "layer": "Service",
            "tenant": "tenant1"
        }
        
        tenant2_node = {
            "namespace_key": "tenant2:project2:Class2",
            "name": "Class2",
            "project": "project2",
            "layer": "Service",
            "tenant": "tenant2"
        }
        
        neo4j_service.merge_node("Java_Class", tenant1_node["namespace_key"], tenant1_node)
        neo4j_service.merge_node("Java_Class", tenant2_node["namespace_key"], tenant2_node)
        print("✓ Created test nodes for two tenants")
        
        # Test filtering by tenant1
        result1 = neo4j_service.get_full_graph(tenant="tenant1")
        tenant1_nodes = [n for n in result1["nodes"] if n.get("tenant") == "tenant1"]
        tenant2_in_result1 = [n for n in result1["nodes"] if n.get("tenant") == "tenant2"]
        
        if len(tenant1_nodes) > 0 and len(tenant2_in_result1) == 0:
            print(f"✓ Tenant filtering works: tenant1 query returned {len(tenant1_nodes)} nodes, 0 from tenant2")
        else:
            print(f"✗ Tenant filtering failed: tenant1={len(tenant1_nodes)}, tenant2={len(tenant2_in_result1)}")
        
        # Test filtering by tenant2
        result2 = neo4j_service.get_full_graph(tenant="tenant2")
        tenant2_nodes = [n for n in result2["nodes"] if n.get("tenant") == "tenant2"]
        tenant1_in_result2 = [n for n in result2["nodes"] if n.get("tenant") == "tenant1"]
        
        if len(tenant2_nodes) > 0 and len(tenant1_in_result2) == 0:
            print(f"✓ Tenant filtering works: tenant2 query returned {len(tenant2_nodes)} nodes, 0 from tenant1")
        else:
            print(f"✗ Tenant filtering failed: tenant2={len(tenant2_nodes)}, tenant1={len(tenant1_in_result2)}")
            
        # Test no filter returns all
        result_all = neo4j_service.get_full_graph()
        all_tenant1 = [n for n in result_all["nodes"] if n.get("tenant") == "tenant1"]
        all_tenant2 = [n for n in result_all["nodes"] if n.get("tenant") == "tenant2"]
        
        if len(all_tenant1) > 0 and len(all_tenant2) > 0:
            print(f"✓ No filter returns all tenants: tenant1={len(all_tenant1)}, tenant2={len(all_tenant2)}")
        else:
            print(f"✗ No filter query failed")
            
    except Exception as e:
        print(f"✗ Error testing tenant filtering: {e}")


def test_tenant_index_exists():
    """Test that tenant index was created."""
    print(f"\nTesting tenant index...")
    
    if not neo4j_service.is_connected:
        print("✗ Neo4j not connected, skipping test")
        return
    
    try:
        # Check if index exists
        query = "SHOW INDEXES YIELD name, labelsOrTypes, properties WHERE 'Entity' IN labelsOrTypes AND 'tenant' IN properties RETURN name"
        result = neo4j_service.graph.run(query).data()
        
        if result:
            print(f"✓ Tenant index exists: {result[0]['name']}")
        else:
            print(f"✗ Tenant index not found")
            
    except Exception as e:
        print(f"✗ Error checking tenant index: {e}")


def cleanup():
    """Clean up test data."""
    print(f"\nCleaning up test data...")
    
    if not neo4j_service.is_connected:
        return
    
    try:
        # Delete test nodes
        neo4j_service.graph.run("MATCH (n:Entity) WHERE n.namespace_key STARTS WITH 'test-tenant-1:' OR n.namespace_key STARTS WITH 'tenant1:' OR n.namespace_key STARTS WITH 'tenant2:' DETACH DELETE n")
        print("✓ Test data cleaned up")
    except Exception as e:
        print(f"✗ Error cleaning up: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Task 12.4 — Tenant Field Support Test")
    print("=" * 60)
    
    # Connect to Neo4j
    if neo4j_service.connect():
        neo4j_service.ensure_indexes()
        print(f"✓ Connected to Neo4j\n")
        
        # Run tests
        test_tenant_field_in_nodes()
        test_tenant_filtering_in_queries()
        test_tenant_index_exists()
        
        # Cleanup
        cleanup()
        
        print("\n" + "=" * 60)
        print("Test completed!")
        print("=" * 60)
    else:
        print("✗ Failed to connect to Neo4j")
        print("Please ensure Neo4j is running and credentials are correct")
        sys.exit(1)
