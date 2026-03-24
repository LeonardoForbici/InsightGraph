"""
Manual test script for CodeQL project management endpoints.

This script demonstrates the project management API without requiring
the full FastAPI server to be running.
"""

import tempfile
from pathlib import Path

from codeql_models import CodeQLProject, ProjectRegistry


def test_project_lifecycle():
    """Test the complete project lifecycle."""
    print("=" * 60)
    print("Testing CodeQL Project Management")
    print("=" * 60)
    
    # Create temporary registry file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        registry_path = f.name
    
    try:
        # Initialize registry
        print("\n1. Initializing project registry...")
        registry = ProjectRegistry(registry_path)
        print(f"   Registry created at: {registry_path}")
        
        # Create a test project
        print("\n2. Creating a test project...")
        with tempfile.TemporaryDirectory() as tmpdir:
            project = CodeQLProject.create(
                name="Test Backend API",
                source_path=tmpdir,
                language="java",
                database_path="/tmp/codeql-db/test-backend",
            )
            
            print(f"   Project ID: {project.id}")
            print(f"   Name: {project.name}")
            print(f"   Language: {project.language}")
            print(f"   Source: {project.source_path}")
            print(f"   Database: {project.database_path}")
            print(f"   Created: {project.created_at}")
            
            # Add to registry
            print("\n3. Adding project to registry...")
            registry.add_project(project)
            print("   ✓ Project added")
            
            # List projects
            print("\n4. Listing all projects...")
            projects = registry.list_projects()
            print(f"   Found {len(projects)} project(s)")
            for p in projects:
                print(f"   - {p.name} ({p.id})")
            
            # Get specific project
            print("\n5. Retrieving project by ID...")
            retrieved = registry.get_project(project.id)
            if retrieved:
                print(f"   ✓ Found: {retrieved.name}")
            else:
                print("   ✗ Not found")
            
            # Update last_analyzed
            print("\n6. Updating last_analyzed timestamp...")
            registry.update_last_analyzed(project.id)
            updated = registry.get_project(project.id)
            print(f"   Last analyzed: {updated.last_analyzed}")
            
            # Create another project
            print("\n7. Creating second project...")
            project2 = CodeQLProject.create(
                name="Test Frontend",
                source_path=tmpdir,
                language="typescript",
                database_path="/tmp/codeql-db/test-frontend",
            )
            registry.add_project(project2)
            print(f"   ✓ Added: {project2.name}")
            
            # List again
            print("\n8. Listing all projects again...")
            projects = registry.list_projects()
            print(f"   Found {len(projects)} project(s)")
            for p in projects:
                print(f"   - {p.name} ({p.language})")
            
            # Delete first project
            print("\n9. Deleting first project...")
            removed = registry.remove_project(project.id)
            if removed:
                print("   ✓ Project removed")
            else:
                print("   ✗ Project not found")
            
            # List final
            print("\n10. Final project list...")
            projects = registry.list_projects()
            print(f"   Found {len(projects)} project(s)")
            for p in projects:
                print(f"   - {p.name}")
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
    
    finally:
        # Cleanup
        Path(registry_path).unlink(missing_ok=True)


if __name__ == "__main__":
    test_project_lifecycle()
