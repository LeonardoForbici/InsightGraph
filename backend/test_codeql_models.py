"""
Unit tests for CodeQL data models and persistence.

Tests:
- Project creation and persistence
- History tracking and retention
- JSON serialization/deserialization
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from codeql_models import (
    CodeQLProject,
    AnalysisJob,
    IngestionSummary,
    AnalysisHistoryEntry,
    ProjectRegistry,
    AnalysisHistory,
    load_projects,
    save_project,
    load_history,
    save_history_entry,
)


# ──────────────────────────────────────────────
# CodeQLProject Tests
# ──────────────────────────────────────────────

def test_project_creation():
    """Test creating a project with generated ID and timestamp."""
    project = CodeQLProject.create(
        name="Test Project",
        source_path="/path/to/source",
        language="java",
        database_path="/path/to/db",
    )
    
    assert project.id is not None
    assert len(project.id) == 36  # UUID format
    assert project.name == "Test Project"
    assert project.source_path == "/path/to/source"
    assert project.language == "java"
    assert project.database_path == "/path/to/db"
    assert project.created_at is not None
    assert project.last_analyzed is None


def test_project_serialization():
    """Test project can be serialized to/from dict."""
    project = CodeQLProject.create(
        name="Test",
        source_path="/src",
        language="javascript",
        database_path="/db",
    )
    
    # Convert to dict
    data = {
        "id": project.id,
        "name": project.name,
        "source_path": project.source_path,
        "language": project.language,
        "database_path": project.database_path,
        "created_at": project.created_at,
        "last_analyzed": project.last_analyzed,
    }
    
    # Recreate from dict
    restored = CodeQLProject(**data)
    
    assert restored.id == project.id
    assert restored.name == project.name
    assert restored.source_path == project.source_path


# ──────────────────────────────────────────────
# AnalysisJob Tests
# ──────────────────────────────────────────────

def test_job_creation():
    """Test creating an analysis job with defaults."""
    job = AnalysisJob.create(
        project_id="test-project-id",
        suite="security-extended",
        force_recreate=False,
    )
    
    assert job.job_id is not None
    assert len(job.job_id) == 36  # UUID format
    assert job.project_id == "test-project-id"
    assert job.status == "queued"
    assert job.stage == "database_creation"
    assert job.progress == 0
    assert job.suite == "security-extended"
    assert job.force_recreate is False
    assert job.started_at is not None


def test_ingestion_summary():
    """Test IngestionSummary dataclass."""
    summary = IngestionSummary(
        total_issues=10,
        ingested=8,
        skipped=2,
        tainted_paths=3,
        vulnerabilities_by_severity={"error": 5, "warning": 3},
    )
    
    assert summary.total_issues == 10
    assert summary.ingested == 8
    assert summary.skipped == 2
    assert summary.tainted_paths == 3
    assert summary.vulnerabilities_by_severity["error"] == 5


# ──────────────────────────────────────────────
# ProjectRegistry Tests
# ──────────────────────────────────────────────

def test_project_registry_persistence():
    """Test project registry saves and loads from JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "projects.json"
        
        # Create registry and add project
        registry = ProjectRegistry(str(registry_path))
        project = CodeQLProject.create(
            name="Test Project",
            source_path="/src",
            language="java",
            database_path="/db",
        )
        registry.add_project(project)
        
        # Verify file was created
        assert registry_path.exists()
        
        # Load in new registry instance
        registry2 = ProjectRegistry(str(registry_path))
        loaded_project = registry2.get_project(project.id)
        
        assert loaded_project is not None
        assert loaded_project.name == "Test Project"
        assert loaded_project.source_path == "/src"


def test_project_registry_list():
    """Test listing all projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(str(registry_path))
        
        # Add multiple projects
        p1 = CodeQLProject.create("Project 1", "/src1", "java", "/db1")
        p2 = CodeQLProject.create("Project 2", "/src2", "javascript", "/db2")
        
        registry.add_project(p1)
        registry.add_project(p2)
        
        projects = registry.list_projects()
        assert len(projects) == 2
        assert any(p.name == "Project 1" for p in projects)
        assert any(p.name == "Project 2" for p in projects)


def test_project_registry_remove():
    """Test removing a project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(str(registry_path))
        
        project = CodeQLProject.create("Test", "/src", "java", "/db")
        registry.add_project(project)
        
        # Remove project
        result = registry.remove_project(project.id)
        assert result is True
        
        # Verify removed
        assert registry.get_project(project.id) is None
        assert len(registry.list_projects()) == 0
        
        # Try removing non-existent project
        result = registry.remove_project("non-existent-id")
        assert result is False


def test_project_registry_update_last_analyzed():
    """Test updating last_analyzed timestamp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "projects.json"
        registry = ProjectRegistry(str(registry_path))
        
        project = CodeQLProject.create("Test", "/src", "java", "/db")
        registry.add_project(project)
        
        # Update timestamp
        timestamp = "2024-01-20T10:30:00Z"
        registry.update_last_analyzed(project.id, timestamp)
        
        # Verify updated
        updated_project = registry.get_project(project.id)
        assert updated_project.last_analyzed == timestamp


# ──────────────────────────────────────────────
# AnalysisHistory Tests
# ──────────────────────────────────────────────

def test_history_persistence():
    """Test history saves and loads from JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "history.json"
        
        # Create history and add entry
        history = AnalysisHistory(str(history_path))
        entry = AnalysisHistoryEntry(
            job_id="job-1",
            project_id="proj-1",
            project_name="Test Project",
            started_at="2024-01-20T10:00:00Z",
            completed_at="2024-01-20T10:05:00Z",
            duration_seconds=300.0,
            suite="security-extended",
            status="completed",
        )
        history.add_entry(entry)
        
        # Verify file was created
        assert history_path.exists()
        
        # Load in new history instance
        history2 = AnalysisHistory(str(history_path))
        loaded_entry = history2.get_entry("job-1")
        
        assert loaded_entry is not None
        assert loaded_entry.project_name == "Test Project"
        assert loaded_entry.duration_seconds == 300.0


def test_history_retention_policy():
    """Test history enforces max 100 entries retention policy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "history.json"
        history = AnalysisHistory(str(history_path))
        
        # Add 105 entries
        for i in range(105):
            entry = AnalysisHistoryEntry(
                job_id=f"job-{i}",
                project_id="proj-1",
                project_name="Test",
                started_at=f"2024-01-20T10:{i:02d}:00Z",
                completed_at=f"2024-01-20T10:{i:02d}:30Z",
                duration_seconds=30.0,
                suite="security-extended",
                status="completed",
            )
            history.add_entry(entry)
        
        # Verify only 100 entries remain
        entries = history.list_entries()
        assert len(entries) == 100
        
        # Verify oldest entries were removed (job-0 through job-4 should be gone)
        assert history.get_entry("job-0") is None
        assert history.get_entry("job-4") is None
        
        # Verify newest entries remain
        assert history.get_entry("job-104") is not None
        assert history.get_entry("job-100") is not None


def test_history_list_filtering():
    """Test filtering history by project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "history.json"
        history = AnalysisHistory(str(history_path))
        
        # Add entries for different projects
        for i in range(5):
            project_id = "proj-1" if i % 2 == 0 else "proj-2"
            entry = AnalysisHistoryEntry(
                job_id=f"job-{i}",
                project_id=project_id,
                project_name=f"Project {project_id}",
                started_at=f"2024-01-20T10:{i:02d}:00Z",
                completed_at=f"2024-01-20T10:{i:02d}:30Z",
                duration_seconds=30.0,
                suite="security-extended",
                status="completed",
            )
            history.add_entry(entry)
        
        # Filter by project
        proj1_entries = history.list_entries(project_id="proj-1")
        assert len(proj1_entries) == 3  # jobs 0, 2, 4
        
        proj2_entries = history.list_entries(project_id="proj-2")
        assert len(proj2_entries) == 2  # jobs 1, 3


def test_history_list_limit():
    """Test limiting number of history entries returned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "history.json"
        history = AnalysisHistory(str(history_path))
        
        # Add 10 entries
        for i in range(10):
            entry = AnalysisHistoryEntry(
                job_id=f"job-{i}",
                project_id="proj-1",
                project_name="Test",
                started_at=f"2024-01-20T10:{i:02d}:00Z",
                completed_at=f"2024-01-20T10:{i:02d}:30Z",
                duration_seconds=30.0,
                suite="security-extended",
                status="completed",
            )
            history.add_entry(entry)
        
        # Get only 3 most recent
        entries = history.list_entries(limit=3)
        assert len(entries) == 3
        
        # Verify they are the most recent (sorted descending)
        assert entries[0].job_id == "job-9"
        assert entries[1].job_id == "job-8"
        assert entries[2].job_id == "job-7"


def test_history_date_filtering():
    """Test filtering history by date range."""
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "history.json"
        history = AnalysisHistory(str(history_path))
        
        # Add entries with different dates
        dates = [
            "2024-01-15T10:00:00Z",
            "2024-01-20T10:00:00Z",
            "2024-01-25T10:00:00Z",
            "2024-01-30T10:00:00Z",
            "2024-02-05T10:00:00Z",
        ]
        
        for i, date in enumerate(dates):
            entry = AnalysisHistoryEntry(
                job_id=f"job-{i}",
                project_id="proj-1",
                project_name="Test",
                started_at=date,
                completed_at=date,
                duration_seconds=30.0,
                suite="security-extended",
                status="completed",
            )
            history.add_entry(entry)
        
        # Filter by start_date only
        entries = history.list_entries(start_date="2024-01-25T00:00:00Z")
        assert len(entries) == 3  # jobs 2, 3, 4
        assert all(e.started_at >= "2024-01-25T00:00:00Z" for e in entries)
        
        # Filter by end_date only
        entries = history.list_entries(end_date="2024-01-25T23:59:59Z")
        assert len(entries) == 3  # jobs 0, 1, 2
        assert all(e.started_at <= "2024-01-25T23:59:59Z" for e in entries)
        
        # Filter by date range
        entries = history.list_entries(
            start_date="2024-01-20T00:00:00Z",
            end_date="2024-01-30T23:59:59Z"
        )
        assert len(entries) == 3  # jobs 1, 2, 3
        assert all("2024-01-20" <= e.started_at <= "2024-01-30T23:59:59Z" for e in entries)


# ──────────────────────────────────────────────
# Utility Function Tests
# ──────────────────────────────────────────────

def test_convenience_functions():
    """Test convenience functions for loading/saving."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "projects.json"
        history_path = Path(tmpdir) / "history.json"
        
        # Test save_project and load_projects
        project = CodeQLProject.create("Test", "/src", "java", "/db")
        save_project(project, str(registry_path))
        
        projects = load_projects(str(registry_path))
        assert len(projects) == 1
        assert projects[0].name == "Test"
        
        # Test save_history_entry and load_history
        entry = AnalysisHistoryEntry(
            job_id="job-1",
            project_id=project.id,
            project_name="Test",
            started_at="2024-01-20T10:00:00Z",
            completed_at="2024-01-20T10:05:00Z",
            duration_seconds=300.0,
            suite="security-extended",
            status="completed",
        )
        save_history_entry(entry, str(history_path))
        
        history = load_history(str(history_path))
        assert len(history) == 1
        assert history[0].job_id == "job-1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
