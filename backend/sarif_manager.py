"""
SARIF File Manager

Manages SARIF file persistence, cleanup, and disk space monitoring.

Responsibilities:
- Create SARIF output directory on startup
- Cleanup SARIF files older than 30 days
- Monitor disk space and cleanup oldest files when needed
- Calculate file sizes for history responses

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("insightgraph")


class SARIFManager:
    """
    Manages SARIF file persistence and cleanup.
    
    Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7
    
    Usage:
        manager = SARIFManager(output_dir="./codeql-results")
        
        # Initialize on startup
        manager.initialize()
        
        # Periodic cleanup
        manager.cleanup_old_files(max_age_days=30)
        manager.cleanup_if_disk_full(min_free_gb=1.0)
    """
    
    # Default retention period in days
    DEFAULT_MAX_AGE_DAYS = 30
    
    # Minimum free disk space in GB before triggering cleanup
    DEFAULT_MIN_FREE_GB = 1.0
    
    def __init__(self, output_dir: str = "./codeql-results"):
        """
        Args:
            output_dir: Directory to store SARIF files
        """
        self.output_dir = Path(output_dir)
        logger.info("SARIFManager initialized with output_dir=%s", output_dir)
    
    # ──────────────────────────────────────────────
    # Initialization
    # ──────────────────────────────────────────────
    
    def initialize(self) -> None:
        """
        Initialize SARIF manager on startup.
        
        Creates output directory and performs initial cleanup.
        
        Requirements: 13.1, 13.3
        """
        try:
            # Create output directory if it doesn't exist
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info("SARIF output directory ready: %s", self.output_dir)
            
            # Perform initial cleanup
            self.cleanup_old_files()
            self.cleanup_if_disk_full()
            
            logger.info("SARIF manager initialization complete")
        
        except Exception as e:
            logger.error("Failed to initialize SARIF manager: %s", e, exc_info=True)
            raise
    
    # ──────────────────────────────────────────────
    # Cleanup Operations
    # ──────────────────────────────────────────────
    
    def cleanup_old_files(self, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> int:
        """
        Remove SARIF files older than specified age.
        
        Requirements: 13.3, 13.4
        
        Args:
            max_age_days: Maximum age in days (default: 30)
        
        Returns:
            Number of files removed
        """
        try:
            if not self.output_dir.exists():
                logger.debug("SARIF output directory does not exist, skipping cleanup")
                return 0
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            removed_count = 0
            total_size = 0
            
            # Find and remove old SARIF files
            for sarif_file in self.output_dir.glob("*.sarif"):
                try:
                    # Get file modification time
                    mtime = datetime.fromtimestamp(
                        sarif_file.stat().st_mtime,
                        tz=timezone.utc
                    )
                    
                    if mtime < cutoff_time:
                        file_size = sarif_file.stat().st_size
                        sarif_file.unlink()
                        removed_count += 1
                        total_size += file_size
                        
                        logger.info(
                            "Removed old SARIF file: %s (age: %d days, size: %s)",
                            sarif_file.name,
                            (datetime.now(timezone.utc) - mtime).days,
                            self._format_size(file_size)
                        )
                
                except Exception as e:
                    logger.warning(
                        "Failed to remove SARIF file %s: %s",
                        sarif_file, e
                    )
            
            if removed_count > 0:
                logger.info(
                    "Cleanup complete: removed %d SARIF files (total: %s, max_age: %d days)",
                    removed_count, self._format_size(total_size), max_age_days
                )
            else:
                logger.debug("No old SARIF files to remove (max_age: %d days)", max_age_days)
            
            return removed_count
        
        except Exception as e:
            logger.error("Failed to cleanup old SARIF files: %s", e, exc_info=True)
            return 0
    
    def cleanup_if_disk_full(
        self,
        min_free_gb: float = DEFAULT_MIN_FREE_GB,
    ) -> int:
        """
        Remove oldest SARIF files if disk space is low.
        
        Requirements: 13.6
        
        Args:
            min_free_gb: Minimum free disk space in GB (default: 1.0)
        
        Returns:
            Number of files removed
        """
        try:
            if not self.output_dir.exists():
                logger.debug("SARIF output directory does not exist, skipping disk check")
                return 0
            
            # Check available disk space
            disk_usage = shutil.disk_usage(self.output_dir)
            free_gb = disk_usage.free / (1024 ** 3)
            
            if free_gb >= min_free_gb:
                logger.debug(
                    "Sufficient disk space available: %.2f GB (min: %.2f GB)",
                    free_gb, min_free_gb
                )
                return 0
            
            logger.warning(
                "Low disk space detected: %.2f GB free (min: %.2f GB), cleaning up oldest SARIF files",
                free_gb, min_free_gb
            )
            
            # Get all SARIF files sorted by modification time (oldest first)
            sarif_files = sorted(
                self.output_dir.glob("*.sarif"),
                key=lambda f: f.stat().st_mtime
            )
            
            if not sarif_files:
                logger.info("No SARIF files to remove")
                return 0
            
            removed_count = 0
            total_size = 0
            
            # Remove oldest files until we have enough space
            for sarif_file in sarif_files:
                try:
                    file_size = sarif_file.stat().st_size
                    sarif_file.unlink()
                    removed_count += 1
                    total_size += file_size
                    
                    logger.info(
                        "Removed oldest SARIF file: %s (size: %s)",
                        sarif_file.name,
                        self._format_size(file_size)
                    )
                    
                    # Check if we have enough space now
                    disk_usage = shutil.disk_usage(self.output_dir)
                    free_gb = disk_usage.free / (1024 ** 3)
                    
                    if free_gb >= min_free_gb:
                        logger.info(
                            "Sufficient disk space restored: %.2f GB free",
                            free_gb
                        )
                        break
                
                except Exception as e:
                    logger.warning(
                        "Failed to remove SARIF file %s: %s",
                        sarif_file, e
                    )
            
            logger.info(
                "Disk cleanup complete: removed %d SARIF files (total: %s)",
                removed_count, self._format_size(total_size)
            )
            
            return removed_count
        
        except Exception as e:
            logger.error("Failed to cleanup disk space: %s", e, exc_info=True)
            return 0
    
    def remove_sarif(self, sarif_path: str) -> bool:
        """
        Remove a specific SARIF file.
        
        Requirements: 13.5
        
        Args:
            sarif_path: Path to SARIF file to remove
        
        Returns:
            True if file was removed, False otherwise
        """
        try:
            sarif_file = Path(sarif_path)
            
            if not sarif_file.exists():
                logger.warning("SARIF file does not exist: %s", sarif_path)
                return False
            
            file_size = sarif_file.stat().st_size
            sarif_file.unlink()
            
            logger.info(
                "Removed SARIF file: %s (size: %s)",
                sarif_file.name,
                self._format_size(file_size)
            )
            
            return True
        
        except Exception as e:
            logger.error("Failed to remove SARIF file %s: %s", sarif_path, e)
            return False
    
    # ──────────────────────────────────────────────
    # File Information
    # ──────────────────────────────────────────────
    
    def get_file_size(self, sarif_path: str) -> Optional[int]:
        """
        Get size of a SARIF file in bytes.
        
        Requirements: 13.7
        
        Args:
            sarif_path: Path to SARIF file
        
        Returns:
            File size in bytes, or None if file doesn't exist
        """
        try:
            sarif_file = Path(sarif_path)
            
            if not sarif_file.exists():
                return None
            
            return sarif_file.stat().st_size
        
        except Exception as e:
            logger.warning("Failed to get SARIF file size for %s: %s", sarif_path, e)
            return None
    
    def get_disk_usage(self) -> dict:
        """
        Get disk usage statistics for SARIF output directory.
        
        Returns:
            Dictionary with total, used, free, and percent usage
        """
        try:
            if not self.output_dir.exists():
                return {
                    "total_gb": 0.0,
                    "used_gb": 0.0,
                    "free_gb": 0.0,
                    "percent": 0.0,
                }
            
            disk_usage = shutil.disk_usage(self.output_dir)
            
            return {
                "total_gb": disk_usage.total / (1024 ** 3),
                "used_gb": disk_usage.used / (1024 ** 3),
                "free_gb": disk_usage.free / (1024 ** 3),
                "percent": (disk_usage.used / disk_usage.total) * 100,
            }
        
        except Exception as e:
            logger.error("Failed to get disk usage: %s", e)
            return {
                "total_gb": 0.0,
                "used_gb": 0.0,
                "free_gb": 0.0,
                "percent": 0.0,
            }
    
    def get_sarif_count(self) -> int:
        """
        Get count of SARIF files in output directory.
        
        Returns:
            Number of SARIF files
        """
        try:
            if not self.output_dir.exists():
                return 0
            
            return len(list(self.output_dir.glob("*.sarif")))
        
        except Exception as e:
            logger.error("Failed to count SARIF files: %s", e)
            return 0
    
    def get_total_size(self) -> int:
        """
        Get total size of all SARIF files in bytes.
        
        Returns:
            Total size in bytes
        """
        try:
            if not self.output_dir.exists():
                return 0
            
            total_size = 0
            for sarif_file in self.output_dir.glob("*.sarif"):
                try:
                    total_size += sarif_file.stat().st_size
                except Exception:
                    pass
            
            return total_size
        
        except Exception as e:
            logger.error("Failed to calculate total SARIF size: %s", e)
            return 0
    
    # ──────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """
        Format file size in human-readable format.
        
        Args:
            size_bytes: Size in bytes
        
        Returns:
            Formatted string (e.g., "1.5 MB")
        """
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
