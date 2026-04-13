"""
Scanner Orchestrator - Coordinates scan execution with mode selection.

This module provides the ScannerOrchestrator class that manages scanning operations
for both local filesystem and GitHub repositories. It handles mode selection,
background task execution, progress tracking, and cancellation support.

Requirements: 3.1, 3.4, 3.5, 3.8, 3.10
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional, Callable, Awaitable
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class GitHubConfig:
    """Configuration for GitHub repository scanning."""
    repository: str  # Format: "owner/repo"
    branch: str = "main"
    token: Optional[str] = None
    shallow_clone: bool = True


@dataclass
class ScanProgress:
    """Progress information for an ongoing scan."""
    scanned_files: int = 0
    total_files: int = 0
    total_nodes: int = 0
    total_relationships: int = 0
    progress_percent: float = 0.0
    current_file: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    """Result of a completed scan operation."""
    status: Literal["completed", "error", "cancelled"]
    nodes_created: int
    relationships_created: int
    duration_seconds: float
    errors: list[str] = field(default_factory=list)


@dataclass
class ScanStatus:
    """Current status of the scanner."""
    status: Literal["idle", "scanning", "completed", "error", "cancelled"]
    scanned_files: int = 0
    total_files: int = 0
    total_nodes: int = 0
    total_relationships: int = 0
    progress_percent: float = 0.0
    current_file: str = ""
    errors: list[str] = field(default_factory=list)


class ScannerOrchestrator:
    """
    Orchestrates scan execution with mode selection (local vs github).
    
    This class coordinates scanning operations, manages background task execution,
    tracks scan progress, and provides cancellation support.
    
    Requirements:
    - 3.1: Mode selection logic (local vs github)
    - 3.4: Background task execution with asyncio
    - 3.5: Scan status tracking
    - 3.8: Cancellation support
    - 3.10: API integration
    """
    
    def __init__(
        self,
        local_scan_fn: Optional[Callable[..., Awaitable[dict]]] = None,
    ):
        """Initialize the scanner orchestrator.

        Args:
            local_scan_fn: Optional coroutine to execute a local scan.
                Signature: (paths: list[str], progress_callback: Optional[Callable]) -> dict
        """
        self._current_task: Optional[asyncio.Task] = None
        self._cancel_requested: bool = False
        self._status: ScanStatus = ScanStatus(status="idle")
        self._lock = asyncio.Lock()
        self._local_scan_fn = local_scan_fn
        logger.info("ScannerOrchestrator initialized")

    def set_local_scan_fn(
        self,
        local_scan_fn: Callable[..., Awaitable[dict]],
    ) -> None:
        self._local_scan_fn = local_scan_fn
    
    async def execute_scan(
        self,
        mode: Literal["local", "github"],
        paths: Optional[list[str]] = None,
        github_config: Optional[GitHubConfig] = None,
        override_commit_hash: Optional[str] = None,
        progress_callback: Optional[Callable[[ScanProgress], None]] = None
    ) -> ScanResult:
        """
        Execute a scan with the specified mode and configuration.
        
        Args:
            mode: Scan mode - either "local" or "github"
            paths: List of local directory paths (required for local mode)
            github_config: GitHub configuration (required for github mode)
            progress_callback: Optional callback for progress updates
            
        Returns:
            ScanResult with completion status and metrics
            
        Raises:
            ValueError: If configuration is invalid for the selected mode
            RuntimeError: If a scan is already in progress
        """
        async with self._lock:
            # Check if scan is already running
            if self._current_task and not self._current_task.done():
                raise RuntimeError("A scan is already in progress")
            
            # Validate configuration based on mode
            if mode == "local":
                if not paths or len(paths) == 0:
                    raise ValueError("Local mode requires at least one path")
            elif mode == "github":
                if not github_config:
                    raise ValueError("GitHub mode requires github_config")
                if not github_config.repository:
                    raise ValueError("GitHub config requires repository")
                # Validate repository format (owner/repo)
                if "/" not in github_config.repository:
                    raise ValueError("Invalid repository format. Expected: owner/repo")
            else:
                raise ValueError(f"Invalid mode: {mode}. Must be 'local' or 'github'")
            
            # Reset cancellation flag
            self._cancel_requested = False
            
            # Initialize status
            self._status = ScanStatus(status="scanning")
            
            # Create and start background task
            self._current_task = asyncio.create_task(
                self._run_scan_background(mode, paths, github_config, override_commit_hash, progress_callback)
            )
            
            logger.info(f"Scan started in {mode} mode")
            
            # Wait for completion
            try:
                return await self._current_task
            except asyncio.CancelledError:
                # Ensure a consistent result for callers that await execute_scan()
                self._status.status = "cancelled"
                duration = 0.0
                return ScanResult(
                    status="cancelled",
                    nodes_created=self._status.total_nodes,
                    relationships_created=self._status.total_relationships,
                    duration_seconds=duration,
                    errors=self._status.errors,
                )
    
    async def _run_scan_background(
        self,
        mode: Literal["local", "github"],
        paths: Optional[list[str]],
        github_config: Optional[GitHubConfig],
        override_commit_hash: Optional[str],
        progress_callback: Optional[Callable[[ScanProgress], None]]
    ) -> ScanResult:
        """
        Background task that executes the actual scan.
        
        This method runs the scan in the background and handles cancellation,
        error tracking, and progress reporting.
        """
        start_time = datetime.now()
        
        try:
            # Execute scan based on mode
            if mode == "local":
                result = await self._execute_local_scan(paths, override_commit_hash, progress_callback)
            else:  # github mode
                result = await self._execute_github_scan(github_config, progress_callback)
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()
            
            # Check if cancelled
            if self._cancel_requested:
                self._status.status = "cancelled"
                return ScanResult(
                    status="cancelled",
                    nodes_created=self._status.total_nodes,
                    relationships_created=self._status.total_relationships,
                    duration_seconds=duration,
                    errors=self._status.errors
                )
            
            # Update final status
            self._status.status = "completed"
            
            return ScanResult(
                status="completed",
                nodes_created=result["nodes_created"],
                relationships_created=result["relationships_created"],
                duration_seconds=duration,
                errors=self._status.errors
            )

        except asyncio.CancelledError:
            duration = (datetime.now() - start_time).total_seconds()
            self._status.status = "cancelled"
            return ScanResult(
                status="cancelled",
                nodes_created=self._status.total_nodes,
                relationships_created=self._status.total_relationships,
                duration_seconds=duration,
                errors=self._status.errors,
            )
            
        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
            self._status.status = "error"
            self._status.errors.append(str(e))
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ScanResult(
                status="error",
                nodes_created=self._status.total_nodes,
                relationships_created=self._status.total_relationships,
                duration_seconds=duration,
                errors=self._status.errors
            )
    
    async def _execute_local_scan(
        self,
        paths: list[str],
        override_commit_hash: Optional[str],
        progress_callback: Optional[Callable[[ScanProgress], None]]
    ) -> dict:
        """
        Execute a local filesystem scan.
        
        This is a placeholder that will be integrated with LocalScanner
        in subsequent tasks.
        """
        logger.info("Executing local scan for paths: %s", paths)

        def combined_callback(progress: ScanProgress) -> None:
            self._update_progress(progress, progress_callback)

        if self._local_scan_fn:
            try:
                return await self._local_scan_fn(paths, combined_callback, override_commit_hash=override_commit_hash)
            except TypeError:
                # Backward-compatible signature: (paths, progress_callback)
                return await self._local_scan_fn(paths, combined_callback)

        # Fallback placeholder implementation (keeps unit tests lightweight)
        await asyncio.sleep(0.05)
        self._update_progress(
            ScanProgress(scanned_files=0, total_files=0, progress_percent=0.0),
            progress_callback,
        )
        return {"nodes_created": 0, "relationships_created": 0}
    
    async def _execute_github_scan(
        self,
        github_config: GitHubConfig,
        progress_callback: Optional[Callable[[ScanProgress], None]]
    ) -> dict:
        """
        Execute a GitHub repository scan.
        
        This is a placeholder that will be integrated with GitHubScanner
        in subsequent tasks.
        """
        logger.info("Executing GitHub scan for repository: %s", github_config.repository)

        # If no local scan function is wired, keep a lightweight placeholder behavior
        # (unit tests and minimal environments without git/network).
        if not self._local_scan_fn:
            await asyncio.sleep(0.05)
            self._update_progress(
                ScanProgress(scanned_files=0, total_files=0, progress_percent=0.0),
                progress_callback,
            )
            return {"nodes_created": 0, "relationships_created": 0}

        def combined_callback(progress: ScanProgress) -> None:
            self._update_progress(progress, progress_callback)

        # Lazy import to avoid import cycles at module import time.
        from github_scanner import GitHubScanner

        async def _local(paths: list[str], cb: Optional[Callable[[ScanProgress], None]] = None) -> dict:
            return await self._local_scan_fn(paths, cb)

        scanner = GitHubScanner(local_scan_fn=_local)
        return await scanner.scan_repository(github_config, combined_callback)
    
    async def get_scan_status(self) -> ScanStatus:
        """
        Get the current scan status.
        
        Returns:
            ScanStatus with current progress and state
        """
        return self._status
    
    async def cancel_scan(self) -> bool:
        """
        Request cancellation of the current scan.
        
        Returns:
            True if cancellation was requested, False if no scan is running
        """
        async with self._lock:
            if not self._current_task or self._current_task.done():
                logger.warning("No active scan to cancel")
                return False
            
            logger.info("Scan cancellation requested")
            self._cancel_requested = True
            
            # Give the task a moment to notice the cancellation
            await asyncio.sleep(0.1)
            
            # If task is still running, cancel it forcefully
            if not self._current_task.done():
                self._current_task.cancel()
                try:
                    await self._current_task
                except asyncio.CancelledError:
                    logger.info("Scan task cancelled")
            
            self._status.status = "cancelled"
            return True
    
    def _update_progress(
        self,
        progress: ScanProgress,
        callback: Optional[Callable[[ScanProgress], None]]
    ) -> None:
        """
        Update internal status and invoke progress callback.
        
        Args:
            progress: Current progress information
            callback: Optional callback to invoke with progress
        """
        # Update internal status
        self._status.scanned_files = progress.scanned_files
        self._status.total_files = progress.total_files
        self._status.total_nodes = progress.total_nodes
        self._status.total_relationships = progress.total_relationships
        self._status.progress_percent = progress.progress_percent
        self._status.current_file = progress.current_file
        self._status.errors = progress.errors.copy()
        
        # Invoke callback if provided
        if callback:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"Progress callback failed: {e}")
    
    def is_scanning(self) -> bool:
        """
        Check if a scan is currently in progress.
        
        Returns:
            True if scanning, False otherwise
        """
        return self._status.status == "scanning"
