"""
Test CodeQL Analysis Endpoints

Tests the FastAPI endpoints for CodeQL analysis execution:
- POST /api/codeql/analyze - Start analysis
- GET /api/codeql/jobs/{job_id} - Get job status
- DELETE /api/codeql/jobs/{job_id} - Cancel job
- GET /api/codeql/history - List history

Requirements: 3.1, 7.1, 7.2, 7.3, 9.1, 9.2, 9.3, 9.4, 12.1, 12.2, 12.6
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_orchestrator():
    """Create a mock CodeQL orchestrator."""
    orchestrator = Mock()
    orchestrator.start_analysis = AsyncMock(return_value="test-job-id-123")
    orchestrator.get_status = Mock()
    orchestrator.cancel_job = Mock(return_value=True)
    return orchestrator


@pytest.fixture
def client(mock_orchestrator):
    """Create a test client with mocked orchestrator."""
    # Import main and patch the global orchestrator before creating the app
    import main
    
    # Patch the global orchestrator
    with patch.object(main, 'codeql_orchestrator', mock_orchestrator):
        # Create test client
        from main import app
        yield TestClient(app)


def test_start_analysis_success(client, mock_orchestrator):
    """Test starting a new analysis job."""
    response = client.post(
        "/api/codeql/analyze",
        json={
            "project_id": "test-project-id",
            "suite": "security-extended",
            "force_recreate": False,
        }
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"] == "test-job-id-123"
    assert data["status"] == "queued"
    assert "message" in data
    
    # Verify orchestrator was called correctly
    mock_orchestrator.start_analysis.assert_called_once()


def test_start_analysis_project_not_found(client, mock_orchestrator):
    """Test starting analysis with non-existent project."""
    mock_orchestrator.start_analysis.side_effect = ValueError("Project not found: invalid-id")
    
    response = client.post(
        "/api/codeql/analyze",
        json={
            "project_id": "invalid-id",
            "suite": "security-extended",
            "force_recreate": False,
        }
    )
    
    assert response.status_code == 400
    assert "Project not found" in response.json()["detail"]


def test_start_analysis_orchestrator_not_initialized():
    """Test starting analysis when orchestrator is not initialized."""
    import main
    
    with patch.object(main, 'codeql_orchestrator', None):
        from main import app
        client = TestClient(app)
        
        response = client.post(
            "/api/codeql/analyze",
            json={
                "project_id": "test-project-id",
                "suite": "security-extended",
                "force_recreate": False,
            }
        )
        
        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"]


def test_get_job_status_success(client, mock_orchestrator):
    """Test getting job status."""
    from codeql_models import AnalysisJob
    
    job = AnalysisJob(
        job_id="test-job-id",
        project_id="test-project-id",
        status="running",
        stage="analysis",
        progress=50,
        suite="security-extended",
        force_recreate=False,
        started_at="2024-01-01T10:00:00",
        current_file="test.java",
        completed_at=None,
        error_message=None,
        sarif_path=None,
        results_summary=None,
    )
    mock_orchestrator.get_status.return_value = job
    
    response = client.get("/api/codeql/jobs/test-job-id")
    
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test-job-id"
    assert data["status"] == "running"
    assert data["stage"] == "analysis"
    assert data["progress"] == 50
    assert data["current_file"] == "test.java"


def test_get_job_status_not_found(client, mock_orchestrator):
    """Test getting status of non-existent job."""
    mock_orchestrator.get_status.return_value = None
    
    response = client.get("/api/codeql/jobs/invalid-job-id")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_cancel_job_success(client, mock_orchestrator):
    """Test cancelling a job."""
    mock_orchestrator.cancel_job.return_value = True
    
    response = client.delete("/api/codeql/jobs/test-job-id")
    
    assert response.status_code == 204
    mock_orchestrator.cancel_job.assert_called_once_with("test-job-id")


def test_cancel_job_not_found(client, mock_orchestrator):
    """Test cancelling a non-existent or completed job."""
    mock_orchestrator.cancel_job.return_value = False
    
    response = client.delete("/api/codeql/jobs/invalid-job-id")
    
    assert response.status_code == 404
    assert "not found or already completed" in response.json()["detail"]


def test_get_history_success(client):
    """Test getting analysis history."""
    from codeql_models import AnalysisHistoryEntry
    
    # Mock the AnalysisHistory class
    mock_history = Mock()
    entries = [
        AnalysisHistoryEntry(
            job_id="job-1",
            project_id="project-1",
            project_name="Project 1",
            started_at="2024-01-01T10:00:00",
            completed_at="2024-01-01T10:05:00",
            duration_seconds=300,
            suite="security-extended",
            status="completed",
            results_summary={"total_issues": 5, "ingested": 5, "skipped": 0},
            sarif_path="/path/to/sarif",
            sarif_size_bytes=1024,
            error_message=None,
        ),
    ]
    mock_history.list_entries.return_value = entries
    
    with patch('codeql_models.AnalysisHistory', return_value=mock_history):
        response = client.get("/api/codeql/history")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["job_id"] == "job-1"
        assert data[0]["project_name"] == "Project 1"
        assert data[0]["status"] == "completed"
        assert data[0]["duration_seconds"] == 300


def test_get_history_with_filters(client):
    """Test getting history with project and date filters."""
    mock_history = Mock()
    mock_history.list_entries.return_value = []
    
    with patch('codeql_models.AnalysisHistory', return_value=mock_history):
        response = client.get(
            "/api/codeql/history?project_id=project-1&start_date=2024-01-01T00:00:00Z&end_date=2024-01-31T23:59:59Z&limit=10"
        )
        
        assert response.status_code == 200
        mock_history.list_entries.assert_called_once_with(
            project_id="project-1",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-31T23:59:59Z",
            limit=10
        )


def test_get_history_limit_exceeded(client):
    """Test getting history with limit exceeding maximum."""
    response = client.get("/api/codeql/history?limit=200")
    
    assert response.status_code == 400
    assert "cannot exceed 100" in response.json()["detail"]


def test_get_history_invalid_date_format(client):
    """Test getting history with invalid date format."""
    response = client.get("/api/codeql/history?start_date=invalid-date")
    
    assert response.status_code == 400
    assert "Invalid start_date format" in response.json()["detail"]
    
    response = client.get("/api/codeql/history?end_date=2024-13-45")
    
    assert response.status_code == 400
    assert "Invalid end_date format" in response.json()["detail"]


def test_analyze_request_validation():
    """Test request model validation."""
    from main import CodeQLAnalyzeRequest
    
    # Valid request
    req = CodeQLAnalyzeRequest(
        project_id="test-id",
        suite="security-extended",
        force_recreate=True,
    )
    assert req.project_id == "test-id"
    assert req.suite == "security-extended"
    assert req.force_recreate is True
    
    # Default values
    req = CodeQLAnalyzeRequest(project_id="test-id")
    assert req.suite == "security-extended"
    assert req.force_recreate is False


def test_job_response_model():
    """Test job response model."""
    from main import CodeQLJobResponse
    
    response = CodeQLJobResponse(
        job_id="job-1",
        project_id="project-1",
        status="completed",
        stage="ingestion",
        progress=100,
        suite="security-extended",
        force_recreate=False,
        started_at="2024-01-01T10:00:00",
        completed_at="2024-01-01T10:05:00",
        results_summary={"total_issues": 5},
    )
    
    assert response.job_id == "job-1"
    assert response.status == "completed"
    assert response.progress == 100


def test_history_response_model():
    """Test history response model."""
    from main import CodeQLHistoryResponse
    
    response = CodeQLHistoryResponse(
        job_id="job-1",
        project_id="project-1",
        project_name="Test Project",
        started_at="2024-01-01T10:00:00",
        completed_at="2024-01-01T10:05:00",
        duration_seconds=300,
        suite="security-extended",
        status="completed",
        results_summary={"total_issues": 5},
        sarif_path="/path/to/sarif",
        sarif_size_bytes=1024,
    )
    
    assert response.job_id == "job-1"
    assert response.project_name == "Test Project"
    assert response.duration_seconds == 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
