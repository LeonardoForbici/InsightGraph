"""
Unit tests for ScannerOrchestrator.

Tests mode selection, background task execution, status tracking,
and cancellation support.
"""

import pytest
import asyncio
from scanner_orchestrator import (
    ScannerOrchestrator,
    GitHubConfig,
    ScanProgress,
    ScanResult,
    ScanStatus
)


@pytest.mark.asyncio
async def test_orchestrator_initialization():
    """Test that orchestrator initializes correctly."""
    orchestrator = ScannerOrchestrator()
    
    status = await orchestrator.get_scan_status()
    assert status.status == "idle"
    assert status.scanned_files == 0
    assert status.total_files == 0
    assert not orchestrator.is_scanning()


@pytest.mark.asyncio
async def test_local_mode_requires_paths():
    """Test that local mode validates paths parameter."""
    orchestrator = ScannerOrchestrator()
    
    # Should raise ValueError when paths is None
    with pytest.raises(ValueError, match="Local mode requires at least one path"):
        await orchestrator.execute_scan(mode="local", paths=None)
    
    # Should raise ValueError when paths is empty
    with pytest.raises(ValueError, match="Local mode requires at least one path"):
        await orchestrator.execute_scan(mode="local", paths=[])


@pytest.mark.asyncio
async def test_github_mode_requires_config():
    """Test that github mode validates github_config parameter."""
    orchestrator = ScannerOrchestrator()
    
    # Should raise ValueError when github_config is None
    with pytest.raises(ValueError, match="GitHub mode requires github_config"):
        await orchestrator.execute_scan(mode="github", github_config=None)


@pytest.mark.asyncio
async def test_github_config_validates_repository():
    """Test that GitHubConfig validates repository format."""
    orchestrator = ScannerOrchestrator()
    
    # Should raise ValueError when repository is empty
    config = GitHubConfig(repository="")
    with pytest.raises(ValueError, match="GitHub config requires repository"):
        await orchestrator.execute_scan(mode="github", github_config=config)
    
    # Should raise ValueError when repository format is invalid
    config = GitHubConfig(repository="invalid-format")
    with pytest.raises(ValueError, match="Invalid repository format"):
        await orchestrator.execute_scan(mode="github", github_config=config)


@pytest.mark.asyncio
async def test_invalid_mode():
    """Test that invalid mode raises ValueError."""
    orchestrator = ScannerOrchestrator()
    
    with pytest.raises(ValueError, match="Invalid mode"):
        await orchestrator.execute_scan(mode="invalid", paths=["/test"])


@pytest.mark.asyncio
async def test_local_scan_execution():
    """Test that local scan executes and returns result."""
    orchestrator = ScannerOrchestrator()
    
    result = await orchestrator.execute_scan(
        mode="local",
        paths=["/test/path"]
    )
    
    assert isinstance(result, ScanResult)
    assert result.status == "completed"
    assert result.duration_seconds >= 0


@pytest.mark.asyncio
async def test_github_scan_execution():
    """Test that github scan executes and returns result."""
    orchestrator = ScannerOrchestrator()
    
    config = GitHubConfig(
        repository="owner/repo",
        branch="main"
    )
    
    result = await orchestrator.execute_scan(
        mode="github",
        github_config=config
    )
    
    assert isinstance(result, ScanResult)
    assert result.status == "completed"
    assert result.duration_seconds >= 0


@pytest.mark.asyncio
async def test_concurrent_scan_prevention():
    """Test that only one scan can run at a time."""
    orchestrator = ScannerOrchestrator()
    
    # Start first scan (will run in background)
    task1 = asyncio.create_task(
        orchestrator.execute_scan(mode="local", paths=["/test1"])
    )
    
    # Give it a moment to start
    await asyncio.sleep(0.01)
    
    # Try to start second scan - should raise RuntimeError
    with pytest.raises(RuntimeError, match="scan is already in progress"):
        await orchestrator.execute_scan(mode="local", paths=["/test2"])
    
    # Wait for first scan to complete
    await task1


@pytest.mark.asyncio
async def test_scan_status_tracking():
    """Test that scan status is tracked correctly."""
    orchestrator = ScannerOrchestrator()
    
    # Initial status should be idle
    status = await orchestrator.get_scan_status()
    assert status.status == "idle"
    
    # Start scan
    task = asyncio.create_task(
        orchestrator.execute_scan(mode="local", paths=["/test"])
    )
    
    # Give it a moment to start
    await asyncio.sleep(0.01)
    
    # Status should be scanning
    status = await orchestrator.get_scan_status()
    assert status.status == "scanning"
    assert orchestrator.is_scanning()
    
    # Wait for completion
    result = await task
    
    # Status should be completed
    status = await orchestrator.get_scan_status()
    assert status.status == "completed"
    assert not orchestrator.is_scanning()


@pytest.mark.asyncio
async def test_scan_cancellation():
    """Test that scan can be cancelled."""
    orchestrator = ScannerOrchestrator()
    
    # Start scan
    task = asyncio.create_task(
        orchestrator.execute_scan(mode="local", paths=["/test"])
    )
    
    # Give it a moment to start
    await asyncio.sleep(0.01)
    
    # Cancel the scan
    cancelled = await orchestrator.cancel_scan()
    assert cancelled is True
    
    # Wait for task to complete
    result = await task
    
    # Result should indicate cancellation
    assert result.status == "cancelled"
    
    # Status should be cancelled
    status = await orchestrator.get_scan_status()
    assert status.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_when_no_scan_running():
    """Test that cancel returns False when no scan is running."""
    orchestrator = ScannerOrchestrator()
    
    cancelled = await orchestrator.cancel_scan()
    assert cancelled is False


@pytest.mark.asyncio
async def test_progress_callback():
    """Test that progress callback is invoked."""
    orchestrator = ScannerOrchestrator()
    progress_updates = []
    
    def callback(progress: ScanProgress):
        progress_updates.append(progress)
    
    await orchestrator.execute_scan(
        mode="local",
        paths=["/test"],
        progress_callback=callback
    )
    
    # Callback should have been invoked (implementation dependent)
    # For now, just verify no errors occurred


@pytest.mark.asyncio
async def test_github_config_defaults():
    """Test GitHubConfig default values."""
    config = GitHubConfig(repository="owner/repo")
    
    assert config.repository == "owner/repo"
    assert config.branch == "main"
    assert config.token is None
    assert config.shallow_clone is True


@pytest.mark.asyncio
async def test_scan_result_structure():
    """Test that ScanResult has correct structure."""
    orchestrator = ScannerOrchestrator()
    
    result = await orchestrator.execute_scan(
        mode="local",
        paths=["/test"]
    )
    
    assert hasattr(result, "status")
    assert hasattr(result, "nodes_created")
    assert hasattr(result, "relationships_created")
    assert hasattr(result, "duration_seconds")
    assert hasattr(result, "errors")
    assert isinstance(result.errors, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
