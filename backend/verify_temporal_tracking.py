"""
Verification script for temporal tracking fields.

This script demonstrates that the temporal tracking fields (last_modified, 
change_frequency, first_seen) are properly set when nodes are created or updated.
"""

import sys
import time
from main import Neo4jService

def verify_temporal_tracking():
    """Verify temporal tracking fields are working correctly."""
    print("=" * 60)
    print("Temporal Tracking Verification")
    print("=" * 60)
    
    # Initialize Neo4j service
    neo4j = Neo4jService()
    
    if not neo4j.connect():
        print("❌ Failed to connect to Neo4j")
        return False
    
    print("✓ Connected to Neo4j")
    
    # Ensure indexes (including temporal ones)
    neo4j.ensure_indexes()
    print("✓ Indexes ensured (including temporal tracking indexes)")
    
    # Test node key
    test_key = "test:temporal:verification"
    
    # Clean up any existing test node
    try:
        neo4j.graph.run(
            "MATCH (n:Entity {namespace_key: $key}) DELETE n",
            key=test_key
        )
        print("✓ Cleaned up existing test node")
    except Exception as e:
        print(f"⚠ Cleanup warning: {e}")
    
    # Test 1: Create a new node
    print("\n--- Test 1: Creating new node ---")
    create_time = time.time()
    neo4j.merge_node("Test_Entity", test_key, {
        "name": "TemporalTestNode",
        "file": "test.py",
        "project": "test_project"
    })
    print("✓ Node created")
    
    # Query the node to verify temporal fields
    result = neo4j.graph.run(
        """
        MATCH (n:Entity {namespace_key: $key})
        RETURN n.last_modified as last_modified,
               n.first_seen as first_seen,
               n.change_frequency as change_frequency
        """,
        key=test_key
    ).data()
    
    if not result:
        print("❌ Node not found after creation")
        return False
    
    node_data = result[0]
    print(f"  last_modified: {node_data['last_modified']}")
    print(f"  first_seen: {node_data['first_seen']}")
    print(f"  change_frequency: {node_data['change_frequency']}")
    
    # Verify initial values
    if node_data['change_frequency'] != 0:
        print(f"❌ Expected change_frequency=0, got {node_data['change_frequency']}")
        return False
    
    if node_data['first_seen'] is None:
        print("❌ first_seen should be set on creation")
        return False
    
    if node_data['last_modified'] is None:
        print("❌ last_modified should be set on creation")
        return False
    
    print("✓ Initial temporal fields are correct")
    
    first_seen = node_data['first_seen']
    first_modified = node_data['last_modified']
    
    # Test 2: Update the node
    print("\n--- Test 2: Updating existing node ---")
    time.sleep(0.1)  # Small delay to ensure timestamp difference
    
    neo4j.merge_node("Test_Entity", test_key, {
        "name": "TemporalTestNode_Updated",
        "file": "test.py",
        "project": "test_project"
    })
    print("✓ Node updated")
    
    # Query again to verify changes
    result = neo4j.graph.run(
        """
        MATCH (n:Entity {namespace_key: $key})
        RETURN n.last_modified as last_modified,
               n.first_seen as first_seen,
               n.change_frequency as change_frequency,
               n.name as name
        """,
        key=test_key
    ).data()
    
    node_data = result[0]
    print(f"  last_modified: {node_data['last_modified']}")
    print(f"  first_seen: {node_data['first_seen']}")
    print(f"  change_frequency: {node_data['change_frequency']}")
    print(f"  name: {node_data['name']}")
    
    # Verify update behavior
    if node_data['change_frequency'] != 1:
        print(f"❌ Expected change_frequency=1, got {node_data['change_frequency']}")
        return False
    
    if node_data['first_seen'] != first_seen:
        print("❌ first_seen should not change on update")
        return False
    
    if node_data['last_modified'] <= first_modified:
        print("❌ last_modified should be updated to a newer timestamp")
        return False
    
    if node_data['name'] != "TemporalTestNode_Updated":
        print("❌ Node properties should be updated")
        return False
    
    print("✓ Update temporal fields are correct")
    
    # Test 3: Multiple updates
    print("\n--- Test 3: Multiple updates ---")
    for i in range(3):
        time.sleep(0.05)
        neo4j.merge_node("Test_Entity", test_key, {
            "name": f"TemporalTestNode_Update_{i}",
            "file": "test.py",
            "project": "test_project"
        })
    
    result = neo4j.graph.run(
        """
        MATCH (n:Entity {namespace_key: $key})
        RETURN n.change_frequency as change_frequency
        """,
        key=test_key
    ).data()
    
    final_frequency = result[0]['change_frequency']
    print(f"  Final change_frequency: {final_frequency}")
    
    if final_frequency != 4:  # 1 from test 2 + 3 from test 3
        print(f"❌ Expected change_frequency=4, got {final_frequency}")
        return False
    
    print("✓ Multiple updates tracked correctly")
    
    # Cleanup
    print("\n--- Cleanup ---")
    neo4j.graph.run(
        "MATCH (n:Entity {namespace_key: $key}) DELETE n",
        key=test_key
    )
    print("✓ Test node deleted")
    
    print("\n" + "=" * 60)
    print("✅ All temporal tracking tests passed!")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = verify_temporal_tracking()
    sys.exit(0 if success else 1)
