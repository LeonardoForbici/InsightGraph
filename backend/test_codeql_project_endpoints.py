"""
Test CodeQL Project Management Endpoints

Tests the FastAPI endpoints for managing CodeQL projects:
- POST /api/codeql/projects
- GET /api/codeql/projects
- GET /api/codeql/projects/{project_id}
- DELETE /api/codeql/projects/{project_id}

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_registry_file():
    """Create a temporary registry file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        registry_path = f.name
        f.write('{"projects": []}')
    
    yield registry_path
    
    # Cleanup
    Path(registry_path).unlink(missing_ok=True)


@pytest.fixture
def test_source_dir():
    """Create a temporary source directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def client(test_registry_file, monkeypatch):
    """Create a test client with mocked registry."""
    # Mock the registry path
    monkeypatch.setenv("CODEQL_PROJECTS_REGISTRY", test_registry_file)
    
    # Import after setting env var
    from main import app
    
    return TestClient(app)


def test_create_project_success(client, test_source_dir):
    """Test creating a new CodeQL project with valid data."""
    response = client.post(
        "/api/codeql/projects",
        json={
            "name": "Test Project",
            "source_path": test_source_dir,
            "language": "java",
            "database_path": "/tmp/codeql-db/test-project"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == "Test Project"
    assert data["source_path"] == test_source_dir
    assert data["language"] == "java"
    assert data["database_path"] == "/tmp/codeql-db/test-project"
    assert "id" in data
    assert "created_at" in data
    assert data["last_analyzed"] is None


def test_create_project_invalid_path(client):
    """Test creating a project with non-existent source path."""
    response = client.post(
        "/api/codeql/projects",
        json={
            "name": "Invalid Project",
            "source_path": "/nonexistent/path",
            "language": "java",
            "database_path": "/tmp/codeql-db/invalid"
        }
    )
    
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_create_project_unsupported_language(client, test_source_dir):
    """Test creating a project with unsupported language."""
    response = client.post(
        "/api/codeql/projects",
        json={
            "name": "Invalid Language",
            "source_path": test_source_dir,
            "language": "cobol",
            "database_path": "/tmp/codeql-db/invalid"
        }
    )
    
    assert response.status_code == 400
    assert "Unsupported language" in response.json()["detail"]


def test_list_projects_empty(client):
    """Test listing projects when registry is empty."""
    response = client.get("/api/codeql/projects")
    
    assert response.status_code == 200
    assert response.json() == []


def test_list_projects_with_data(client, test_source_dir):
    """Test listing projects after creating some."""
    # Create two projects
    client.post(
        "/api/codeql/projects",
        json={
            "name": "Project 1",
            "source_path": test_source_dir,
            "language": "java",
            "database_path": "/tmp/codeql-db/project1"
        }
    )
    
    client.post(
        "/api/codeql/projects",
        json={
            "name": "Project 2",
            "source_path": test_source_dir,
            "language": "typescript",
            "database_path": "/tmp/codeql-db/project2"
        }
    )
    
    # List projects
    response = client.get("/api/codeql/projects")
    
    assert response.status_code == 200
    projects = response.json()
    assert len(projects) == 2
    assert projects[0]["name"] == "Project 1"
    assert projects[1]["name"] == "Project 2"


def test_get_project_by_id(client, test_source_dir):
    """Test retrieving a specific project by ID."""
    # Create a project
    create_response = client.post(
        "/api/codeql/projects",
        json={
            "name": "Test Project",
            "source_path": test_source_dir,
            "language": "java",
            "database_path": "/tmp/codeql-db/test"
        }
    )
    
    project_id = create_response.json()["id"]
    
    # Get the project
    response = client.get(f"/api/codeql/projects/{project_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert data["name"] == "Test Project"


def test_get_project_not_found(client):
    """Test retrieving a non-existent project."""
    response = client.get("/api/codeql/projects/nonexistent-id")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_delete_project(client, test_source_dir):
    """Test deleting a project."""
    # Create a project
    create_response = client.post(
        "/api/codeql/projects",
        json={
            "name": "To Delete",
            "source_path": test_source_dir,
            "language": "java",
            "database_path": "/tmp/codeql-db/delete"
        }
    )
    
    project_id = create_response.json()["id"]
    
    # Delete the project
    response = client.delete(f"/api/codeql/projects/{project_id}")
    
    assert response.status_code == 204
    
    # Verify it's gone
    get_response = client.get(f"/api/codeql/projects/{project_id}")
    assert get_response.status_code == 404


def test_delete_project_not_found(client):
    """Test deleting a non-existent project."""
    response = client.delete("/api/codeql/projects/nonexistent-id")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_project_validation_missing_fields(client):
    """Test that required fields are validated."""
    response = client.post(
        "/api/codeql/projects",
        json={
            "name": "Incomplete"
            # Missing source_path, language, database_path
        }
    )
    
    assert response.status_code == 422  # Validation error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
