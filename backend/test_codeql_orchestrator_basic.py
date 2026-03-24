"""
Basic unit tests for CodeQLOrchestrator

Tests core functionality:
- Job creation and queueing
- Status tracking
- Concurrent job limits
- Job cancellation
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from codeql_orchestrator import CodeQLOrchestrator
from codeql_models import (
    CodeQLProject,
    AnalysisJob,
    ProjectRegistry,
    AnalysisHistory,
)
from codeql_database_manager import DatabaseManager
from codeql_analysis_engine import AnalysisEngine
from codeql_bridge import CodeQLBridge


@pytest.fixture
def mock_components():
    """Create mock components for orchestrator."""
    db_manager = Mock(spec=DatabaseManager)
    analysis_engine = Mock(spec=AnalysisEngine)
    sarif_ingestor = Mock(spec=CodeQLBridge)
    project_registry = Mock(spec=ProjectRegistry)
    analysis_history = Mock(spec=AnalysisHistory)
    
    return {
        "db_manager": db_manager,
        "analysis_engine": analysis_engine,
        "sarif_ingestor": sarif_ingestor,
        "project_registry": project_registry,
        "analysis_history": analysis_history,
    }


@pytest.fixture
def orchestrator(mock_components):
    """Create orchestrator with mock components."""
    return CodeQLOrchestrator(
        database_manager=mock_components["db_manager"],
        analysis_engine=mock_components["analysis_engine"],
        sarif_ingestor=mock_components["sarif_ingestor"],
        project_registry=mock_components["project_registry"],
        analysis_history=mock_components["analysis_history"],
        max_concurrent=3,
    )


@pytest.fixture
def sample_project():
    """Create a sample project for testing."""
    return CodeQLProject(
        id="test-project-1",
        name="Test Project",
        source_path="/path/to/source",
        language="java",
        database_path="/path/to/db",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ──────────────────────────────────────────────
# Test Job Creation and Queueing
# ──────────────────────────────────────────────

def test_start_analysis_creates_job(orchestrator, mock_components, sample_project):
    """Test that start_analysis creates a job and returns job_id."""
    mock_components["project_registry"].get_project.return_value = sample_project
    
    # Run async function in event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        job_id = loop.run_until_complete(
            orchestrator.start_analysis(
                project_id=sample_project.id,
                suite="security-extended",
                force_recreate=False,
            )
        )
        
        assert job_id is not None
        assert job_id in orchestrator.jobs
        
        job = orchestrator.jobs[job_id]
        assert job.project_id == sample_project.id
        assert job.suite == "security-extended"
        assert job.force_recreate is False
        assert job.status in ("queued", "running")
    finally:
        loop.close()


def test_start_analysis_project_not_found(orchestrator, mock_components):
    """Test that start_analysis raises ValueError for non-existent project."""
    mock_components["project_registry"].get_project.return_value = None
    
    # Run async function in event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with pytest.raises(ValueError, match="Project not found"):
            loop.run_until_complete(
                orchestrator.start_analysis(
                    project_id="non-existent",
                    suite="security-extended",
                    force_recreate=False,
                )
            )
    finally:
        loop.close()


def test_concurrent_job_limit(orchestrator, mock_components, sample_project):
    """Test that jobs are queued when concurrent limit is reached."""
    mock_components["project_registry"].get_project.return_value = sample_project
    
    # Mock the async execution to prevent actual execution
    with patch.object(orchestrator, '_execute_analysis', new_callable=AsyncMock):
        # Run async function in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Start 4 jobs (max_concurrent=3)
            job_ids = []
            for i in range(4):
                job_id = loop.run_until_complete(
                    orchestrator.start_analysis(
                        project_id=sample_project.id,
                        suite="security-extended",
                        force_recreate=False,
                    )
                )
                job_ids.append(job_id)
            
            # First 3 should be running, 4th should be queued
            running_count = sum(
                1 for job_id in job_ids
                if orchestrator.jobs[job_id].status == "running"
            )
            queued_count = sum(
                1 for job_id in job_ids
                if orchestrator.jobs[job_id].status == "queued"
            )
            
            assert running_count == 3, f"Expected 3 running jobs, got {running_count}"
            assert queued_count == 1, f"Expected 1 queued job, got {queued_count}"
            assert len(orchestrator.active_jobs) == 3
        finally:
            loop.close()


# ──────────────────────────────────────────────
# Test Status Tracking
# ──────────────────────────────────────────────

def test_get_status_existing_job(orchestrator, sample_project):
    """Test getting status of an existing job."""
    job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    orchestrator.jobs[job.job_id] = job
    
    retrieved_job = orchestrator.get_status(job.job_id)
    
    assert retrieved_job is not None
    assert retrieved_job.job_id == job.job_id
    assert retrieved_job.project_id == sample_project.id


def test_get_status_non_existent_job(orchestrator):
    """Test getting status of non-existent job returns None."""
    retrieved_job = orchestrator.get_status("non-existent-job")
    
    assert retrieved_job is None


def test_update_progress(orchestrator, sample_project):
    """Test updating job progress."""
    job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    orchestrator.jobs[job.job_id] = job
    
    orchestrator.update_progress(job.job_id, 50, current_file="test.java")
    
    assert job.progress == 50
    assert job.current_file == "test.java"


def test_update_progress_clamps_values(orchestrator, sample_project):
    """Test that progress is clamped to 0-100 range."""
    job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    orchestrator.jobs[job.job_id] = job
    
    # Test upper bound
    orchestrator.update_progress(job.job_id, 150)
    assert job.progress == 100
    
    # Test lower bound
    orchestrator.update_progress(job.job_id, -10)
    assert job.progress == 0


# ──────────────────────────────────────────────
# Test Job Cancellation
# ──────────────────────────────────────────────

def test_cancel_queued_job(orchestrator, sample_project):
    """Test cancelling a queued job."""
    job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    job.status = "queued"
    orchestrator.jobs[job.job_id] = job
    orchestrator.job_queue.append(job.job_id)
    
    result = orchestrator.cancel_job(job.job_id)
    
    assert result is True
    assert job.status == "cancelled"
    assert job.job_id not in orchestrator.job_queue
    assert job.completed_at is not None


def test_cancel_running_job(orchestrator, sample_project):
    """Test cancelling a running job."""
    job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    job.status = "running"
    orchestrator.jobs[job.job_id] = job
    orchestrator.active_jobs.add(job.job_id)
    
    result = orchestrator.cancel_job(job.job_id)
    
    assert result is True
    assert job.status == "cancelled"
    assert job.job_id not in orchestrator.active_jobs
    assert job.completed_at is not None


def test_cancel_completed_job(orchestrator, sample_project):
    """Test that completed jobs cannot be cancelled."""
    job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    job.status = "completed"
    orchestrator.jobs[job.job_id] = job
    
    result = orchestrator.cancel_job(job.job_id)
    
    assert result is False
    assert job.status == "completed"


def test_cancel_non_existent_job(orchestrator):
    """Test cancelling non-existent job returns False."""
    result = orchestrator.cancel_job("non-existent-job")
    
    assert result is False


# ──────────────────────────────────────────────
# Test Queue Processing
# ──────────────────────────────────────────────

def test_process_queue_starts_next_job(orchestrator, sample_project):
    """Test that process_queue starts next job when capacity available."""
    # Create a queued job
    job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    job.status = "queued"
    orchestrator.jobs[job.job_id] = job
    orchestrator.job_queue.append(job.job_id)
    
    # Mock asyncio.create_task to avoid event loop issues
    with patch('asyncio.create_task') as mock_create_task:
        # Process queue
        orchestrator._process_queue()
        
        # Job should be moved to active
        assert job.job_id in orchestrator.active_jobs
        assert job.status == "running"
        assert job.job_id not in orchestrator.job_queue
        
        # Verify create_task was called
        assert mock_create_task.called


def test_process_queue_respects_concurrent_limit(orchestrator, sample_project):
    """Test that process_queue respects max_concurrent limit."""
    # Fill active jobs to max
    for i in range(3):
        job = AnalysisJob.create(
            project_id=sample_project.id,
            suite="security-extended",
            force_recreate=False,
        )
        job.status = "running"
        orchestrator.jobs[job.job_id] = job
        orchestrator.active_jobs.add(job.job_id)
    
    # Create a queued job
    queued_job = AnalysisJob.create(
        project_id=sample_project.id,
        suite="security-extended",
        force_recreate=False,
    )
    queued_job.status = "queued"
    orchestrator.jobs[queued_job.job_id] = queued_job
    orchestrator.job_queue.append(queued_job.job_id)
    
    # Process queue
    orchestrator._process_queue()
    
    # Queued job should remain queued
    assert queued_job.status == "queued"
    assert queued_job.job_id in orchestrator.job_queue
    assert len(orchestrator.active_jobs) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
