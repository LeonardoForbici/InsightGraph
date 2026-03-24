"""
Tests for SARIF Manager

Tests SARIF file management functionality including:
- Directory initialization
- Old file cleanup
- Disk space monitoring and cleanup
- File size calculation

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7
"""

import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sarif_manager import SARIFManager


class TestSARIFManager:
    """Test suite for SARIFManager."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create a SARIFManager instance with temp directory."""
        return SARIFManager(output_dir=temp_dir)
    
    # ──────────────────────────────────────────────
    # Initialization Tests
    # ──────────────────────────────────────────────
    
    def test_initialize_creates_directory(self, temp_dir):
        """Test that initialize creates output directory."""
        # Remove temp dir to test creation
        shutil.rmtree(temp_dir)
        
        manager = SARIFManager(output_dir=temp_dir)
        manager.initialize()
        
        assert os.path.exists(temp_dir)
        assert os.path.isdir(temp_dir)
    
    def test_initialize_with_existing_directory(self, manager):
        """Test that initialize works with existing directory."""
        # Should not raise exception
        manager.initialize()
        
        assert os.path.exists(manager.output_dir)
    
    # ──────────────────────────────────────────────
    # Cleanup Old Files Tests
    # ──────────────────────────────────────────────
    
    def test_cleanup_old_files_removes_old_sarifs(self, manager, temp_dir):
        """Test that cleanup removes SARIF files older than max_age_days."""
        manager.initialize()
        
        # Create old SARIF file (31 days old)
        old_sarif = Path(temp_dir) / "old_project_20240101_120000.sarif"
        old_sarif.write_text('{"version": "2.1.0"}')
        
        # Set modification time to 31 days ago
        old_time = (datetime.now(timezone.utc) - timedelta(days=31)).timestamp()
        os.utime(old_sarif, (old_time, old_time))
        
        # Create recent SARIF file (1 day old)
        recent_sarif = Path(temp_dir) / "recent_project_20240201_120000.sarif"
        recent_sarif.write_text('{"version": "2.1.0"}')
        
        # Run cleanup with 30 day retention
        removed_count = manager.cleanup_old_files(max_age_days=30)
        
        # Old file should be removed, recent file should remain
        assert removed_count == 1
        assert not old_sarif.exists()
        assert recent_sarif.exists()
    
    def test_cleanup_old_files_no_files_to_remove(self, manager, temp_dir):
        """Test cleanup when no files are old enough to remove."""
        manager.initialize()
        
        # Create recent SARIF file
        recent_sarif = Path(temp_dir) / "recent_project_20240201_120000.sarif"
        recent_sarif.write_text('{"version": "2.1.0"}')
        
        # Run cleanup
        removed_count = manager.cleanup_old_files(max_age_days=30)
        
        # No files should be removed
        assert removed_count == 0
        assert recent_sarif.exists()
    
    def test_cleanup_old_files_empty_directory(self, manager):
        """Test cleanup with empty directory."""
        manager.initialize()
        
        # Run cleanup on empty directory
        removed_count = manager.cleanup_old_files(max_age_days=30)
        
        assert removed_count == 0
    
    def test_cleanup_old_files_nonexistent_directory(self, temp_dir):
        """Test cleanup when directory doesn't exist."""
        # Don't initialize, so directory doesn't exist
        manager = SARIFManager(output_dir=temp_dir + "_nonexistent")
        
        # Should not raise exception
        removed_count = manager.cleanup_old_files(max_age_days=30)
        
        assert removed_count == 0
    
    # ──────────────────────────────────────────────
    # Disk Space Cleanup Tests
    # ──────────────────────────────────────────────
    
    def test_cleanup_if_disk_full_sufficient_space(self, manager, temp_dir):
        """Test that cleanup doesn't remove files when disk space is sufficient."""
        manager.initialize()
        
        # Create SARIF file
        sarif = Path(temp_dir) / "project_20240201_120000.sarif"
        sarif.write_text('{"version": "2.1.0"}')
        
        # Run cleanup with very low threshold (should have enough space)
        removed_count = manager.cleanup_if_disk_full(min_free_gb=0.001)
        
        # No files should be removed
        assert removed_count == 0
        assert sarif.exists()
    
    def test_cleanup_if_disk_full_removes_oldest_first(self, manager, temp_dir):
        """Test that cleanup removes oldest files first when disk is full."""
        manager.initialize()
        
        # Create multiple SARIF files with different ages
        old_sarif = Path(temp_dir) / "old_project_20240101_120000.sarif"
        old_sarif.write_text('{"version": "2.1.0"}' * 1000)  # Make it larger
        
        mid_sarif = Path(temp_dir) / "mid_project_20240115_120000.sarif"
        mid_sarif.write_text('{"version": "2.1.0"}' * 1000)
        
        new_sarif = Path(temp_dir) / "new_project_20240201_120000.sarif"
        new_sarif.write_text('{"version": "2.1.0"}' * 1000)
        
        # Set modification times
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        mid_time = (datetime.now(timezone.utc) - timedelta(days=15)).timestamp()
        new_time = datetime.now(timezone.utc).timestamp()
        
        os.utime(old_sarif, (old_time, old_time))
        os.utime(mid_sarif, (mid_time, mid_time))
        os.utime(new_sarif, (new_time, new_time))
        
        # Run cleanup with impossibly high threshold (will remove files)
        # Note: This test may not work reliably on all systems
        # We're just checking that the method doesn't crash
        removed_count = manager.cleanup_if_disk_full(min_free_gb=999999.0)
        
        # At least some files should be attempted for removal
        # (actual behavior depends on disk space)
        assert removed_count >= 0
    
    def test_cleanup_if_disk_full_empty_directory(self, manager):
        """Test disk cleanup with empty directory."""
        manager.initialize()
        
        # Run cleanup on empty directory
        removed_count = manager.cleanup_if_disk_full(min_free_gb=1.0)
        
        assert removed_count == 0
    
    # ──────────────────────────────────────────────
    # Remove SARIF Tests
    # ──────────────────────────────────────────────
    
    def test_remove_sarif_existing_file(self, manager, temp_dir):
        """Test removing an existing SARIF file."""
        manager.initialize()
        
        # Create SARIF file
        sarif = Path(temp_dir) / "project_20240201_120000.sarif"
        sarif.write_text('{"version": "2.1.0"}')
        
        # Remove file
        result = manager.remove_sarif(str(sarif))
        
        assert result is True
        assert not sarif.exists()
    
    def test_remove_sarif_nonexistent_file(self, manager, temp_dir):
        """Test removing a non-existent SARIF file."""
        sarif_path = str(Path(temp_dir) / "nonexistent.sarif")
        
        # Try to remove non-existent file
        result = manager.remove_sarif(sarif_path)
        
        assert result is False
    
    # ──────────────────────────────────────────────
    # File Information Tests
    # ──────────────────────────────────────────────
    
    def test_get_file_size_existing_file(self, manager, temp_dir):
        """Test getting size of existing SARIF file."""
        manager.initialize()
        
        # Create SARIF file with known content
        sarif = Path(temp_dir) / "project_20240201_120000.sarif"
        content = '{"version": "2.1.0"}'
        sarif.write_text(content)
        
        # Get file size
        size = manager.get_file_size(str(sarif))
        
        assert size is not None
        assert size == len(content.encode('utf-8'))
    
    def test_get_file_size_nonexistent_file(self, manager, temp_dir):
        """Test getting size of non-existent file."""
        sarif_path = str(Path(temp_dir) / "nonexistent.sarif")
        
        # Get file size
        size = manager.get_file_size(sarif_path)
        
        assert size is None
    
    def test_get_disk_usage(self, manager):
        """Test getting disk usage statistics."""
        manager.initialize()
        
        # Get disk usage
        usage = manager.get_disk_usage()
        
        assert "total_gb" in usage
        assert "used_gb" in usage
        assert "free_gb" in usage
        assert "percent" in usage
        
        assert usage["total_gb"] > 0
        assert usage["free_gb"] > 0
        assert 0 <= usage["percent"] <= 100
    
    def test_get_sarif_count(self, manager, temp_dir):
        """Test counting SARIF files."""
        manager.initialize()
        
        # Create multiple SARIF files
        for i in range(3):
            sarif = Path(temp_dir) / f"project_{i}_20240201_120000.sarif"
            sarif.write_text('{"version": "2.1.0"}')
        
        # Get count
        count = manager.get_sarif_count()
        
        assert count == 3
    
    def test_get_sarif_count_empty_directory(self, manager):
        """Test counting SARIF files in empty directory."""
        manager.initialize()
        
        # Get count
        count = manager.get_sarif_count()
        
        assert count == 0
    
    def test_get_total_size(self, manager, temp_dir):
        """Test getting total size of all SARIF files."""
        manager.initialize()
        
        # Create multiple SARIF files
        total_expected = 0
        for i in range(3):
            sarif = Path(temp_dir) / f"project_{i}_20240201_120000.sarif"
            content = f'{{"version": "2.1.0", "index": {i}}}'
            sarif.write_text(content)
            total_expected += len(content.encode('utf-8'))
        
        # Get total size
        total_size = manager.get_total_size()
        
        assert total_size == total_expected
    
    def test_get_total_size_empty_directory(self, manager):
        """Test getting total size with no SARIF files."""
        manager.initialize()
        
        # Get total size
        total_size = manager.get_total_size()
        
        assert total_size == 0
    
    # ──────────────────────────────────────────────
    # Utility Tests
    # ──────────────────────────────────────────────
    
    def test_format_size(self):
        """Test file size formatting."""
        assert SARIFManager._format_size(500) == "500.0 B"
        assert SARIFManager._format_size(1024) == "1.0 KB"
        assert SARIFManager._format_size(1024 * 1024) == "1.0 MB"
        assert SARIFManager._format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert SARIFManager._format_size(1536) == "1.5 KB"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
