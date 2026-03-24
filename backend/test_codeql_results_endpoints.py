"""
Test CodeQL Results Endpoints

Tests the FastAPI endpoints for retrieving CodeQL analysis results:
- GET /api/codeql/vulnerabilities/{node_key}
- GET /api/codeql/sarif/{job_id}
- DELETE /api/codeql/sarif/{job_id}
- GET /api/codeql/config
- GET /api/health (CodeQL CLI status)

Requirements: 10.7, 11.4, 11.5, 11.7, 13.3, 13.5
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_neo4j_service():
    """Mock Neo4j service for testing."""
    service = Mock()
    service.is_connected = True
    service.graph = Mock()
    return service


@pytest.fixture
def mock_orchestrator():
    """Mock CodeQL orchestrator for testing."""
    orchestrator = Mock()
    orchestrator.analysis_history = Mock()
    return orchestrator


@pytest.fixture
def client(mock_neo4j_service, mock_orchestrator):
    """Create a test client with mocked dependencies."""
    with patch('main.neo4j_service', mock_neo4j_service), \
         patch('main.codeql_orchestrator', mock_orchestrator):
        from main import app
        return TestClient(app)


def test_get_node_vulnerabilities_success(client, mock_neo4j_service):
    """Test retrieving vulnerabilities for a specific node."""
    # Mock Neo4j query result
    mock_neo4j_service.graph.run.return_value.data.return_value = [
        {
            "issue_key": "security:sql-injection:file.java:10",
            "rule_id": "java/sql-injection",
            "severity": "error",
            "message": "SQL injection vulnerability",
            "file": "src/main/java/file.java",
            "start_line": 10,
            "end_line": 12,
            "has_taint_flow": True,
            "help_text": "Avoid concatenating user input into SQL queries"
        }
    ]
    
    response = client.get("/api/codeql/vulnerabilities/test:node:key")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["count"] == 1
    assert len(data["vulnerabilities"]) == 1
    assert data["vulnerabilities"][0]["rule_id"] == "java/sql-injection"
    assert data["vulnerabilities"][0]["severity"] == "error"


def test_get_node_vulnerabilities_no_neo4j(client, mock_neo4j_service):
    """Test retrieving vulnerabilities when Neo4j is disconnected."""
    mock_neo4j_service.is_connected = False
    
    response = client.get("/api/codeql/vulnerabilities/test:node:key")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["count"] == 0
    assert data["vulnerabilities"] == []


def test_download_sarif_success(client, mock_orchestrator):
    """Test downloading SARIF file for a completed job."""
    # Create a temporary SARIF file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sarif', delete=False) as f:
        sarif_path = f.name
        json.dump({"version": "2.1.0", "runs": []}, f)
    
    try:
        # Mock job with SARIF path
        mock_job = Mock()
        mock_job.sarif_path = sarif_path
        mock_orchestrator.get_status.return_value = mock_job
        
        response = client.get("/api/codeql/sarif/test-job-id")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
    
    finally:
        Path(sarif_path).unlink(missing_ok=True)


def test_download_sarif_not_found(client, mock_orchestrator):
    """Test downloading SARIF file when job doesn't exist."""
    mock_orchestrator.get_status.return_value = None
    mock_orchestrator.analysis_history.get_entry.return_value = None
    
    response = client.get("/api/codeql/sarif/nonexistent-job")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_delete_sarif_success(client, mock_orchestrator):
    """Test deleting SARIF file for a completed job."""
    # Create a temporary SARIF file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sarif', delete=False) as f:
        sarif_path = f.name
        json.dump({"version": "2.1.0", "runs": []}, f)
    
    # Mock job with SARIF path
    mock_job = Mock()
    mock_job.sarif_path = sarif_path
    mock_orchestrator.get_status.return_value = mock_job
    
    response = client.delete(f"/api/codeql/sarif/test-job-id")
    
    assert response.status_code == 204
    assert not Path(sarif_path).exists()


def test_delete_sarif_not_found(client, mock_orchestrator):
    """Test deleting SARIF file when job doesn't exist."""
    mock_orchestrator.get_status.return_value = None
    mock_orchestrator.analysis_history.get_entry.return_value = None
    
    response = client.delete("/api/codeql/sarif/nonexistent-job")
    
    assert response.status_code == 404


def test_get_codeql_config_success(client):
    """Test retrieving CodeQL configuration."""
    with patch('subprocess.run') as mock_run:
        # Mock CodeQL version command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "CodeQL command-line toolchain release 2.15.0"
        mock_run.return_value = mock_result
        
        with patch('pathlib.Path.exists', return_value=True):
            response = client.get("/api/codeql/config")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "codeql_path" in data
    assert "codeql_version" in data
    assert "codeql_available" in data
    assert "database_directory" in data
    assert "results_directory" in data
    assert "max_concurrent_analyses" in data
    assert "analysis_timeout_seconds" in data
    
    assert data["codeql_available"] is True
    assert "2.15.0" in data["codeql_version"]


def test_get_codeql_config_cli_not_found(client):
    """Test retrieving CodeQL configuration when CLI is not installed."""
    with patch('pathlib.Path.exists', return_value=False):
        response = client.get("/api/codeql/config")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["codeql_available"] is False
    assert data["codeql_version"] is None


def test_health_endpoint_with_codeql(client, mock_orchestrator):
    """Test health endpoint includes CodeQL CLI status."""
    with patch('subprocess.run') as mock_run:
        # Mock CodeQL version command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "CodeQL command-line toolchain release 2.15.0"
        mock_run.return_value = mock_result
        
        with patch('pathlib.Path.exists', return_value=True):
            response = client.get("/api/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "codeql_cli" in data
    assert "codeql_version" in data
    assert data["codeql_cli"] == "available"
    assert "2.15.0" in data["codeql_version"]


def test_health_endpoint_codeql_not_initialized(client):
    """Test health endpoint when CodeQL orchestrator is not initialized."""
    with patch('main.codeql_orchestrator', None):
        response = client.get("/api/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["codeql_cli"] == "not_initialized"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
