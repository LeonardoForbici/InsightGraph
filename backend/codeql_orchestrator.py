"""
CodeQL Orchestrator

Coordinates the full CodeQL analysis workflow by managing:
- Analysis job lifecycle (queued, running, completed, failed)
- Background task execution with concurrent job limits
- Progress tracking and status reporting
- Integration of DatabaseManager, AnalysisEngine, and SARIF Ingestor

Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from codeql_models import (
    AnalysisJob,
    AnalysisHistoryEntry,
    ProjectRegistry,
    AnalysisHistory,
)
from codeql_database_manager import DatabaseManager, DatabaseError
from codeql_analysis_engine import AnalysisEngine, AnalysisError
from codeql_bridge import CodeQLBridge

logger = logging.getLogger("insightgraph")


class CodeQLOrchestrator:
    """
    Orchestrates CodeQL analysis workflow with job management and concurrency control.
    
    Responsibilities:
    - Manage analysis job lifecycle (create, queue, execute, complete)
    - Execute full workflow: database creation → analysis → SARIF ingestion
    - Track progress and status for each job
    - Enforce concurrent job limits (max 3 simultaneous analyses)
    - Maintain job queue for excess requests
    - Support job cancellation
    
    Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
    
    Usage:
        orchestrator = CodeQLOrchestrator(
            database_manager=db_manager,
            analysis_engine=engine,
            sarif_ingestor=bridge,
            project_registry=registry,
            analysis_history=history,
            max_concurrent=3
        )
        
        # Start analysis (returns immediately with job_id)
        job_id = await orchestrator.start_analysis(
            project_id="uuid-1",
            suite="security-extended",
            force_recreate=False
        )
        
        # Check status
        job = orchestrator.get_status(job_id)
        print(f"Status: {job.status}, Progress: {job.progress}%")
        
        # Cancel if needed
        orchestrator.cancel_job(job_id)
    """
    
    def __init__(
        self,
        database_manager: DatabaseManager,
        analysis_engine: AnalysisEngine,
        sarif_ingestor: CodeQLBridge,
        project_registry: ProjectRegistry,
        analysis_history: AnalysisHistory,
        max_concurrent: int = 3,
        sarif_manager: Optional[object] = None,
    ):
        """
        Args:
            database_manager: DatabaseManager instance for database operations
            analysis_engine: AnalysisEngine instance for running CodeQL analysis
            sarif_ingestor: CodeQLBridge instance for SARIF ingestion
            project_registry: ProjectRegistry for project configuration
            analysis_history: AnalysisHistory for storing completed analyses
            max_concurrent: Maximum number of concurrent analyses (default: 3)
            sarif_manager: SARIFManager instance for file management (optional)
        """
        self.database_manager = database_manager
        self.analysis_engine = analysis_engine
        self.sarif_ingestor = sarif_ingestor
        self.project_registry = project_registry
        self.analysis_history = analysis_history
        self.max_concurrent = max_concurrent
        self.sarif_manager = sarif_manager
        
        # Job tracking
        self.jobs: dict[str, AnalysisJob] = {}
        self.active_jobs: set[str] = set()
        self.job_queue: deque[str] = deque()
        
        # Cancellation tracking
        self._cancelled_jobs: set[str] = set()
        
        logger.info(
            "CodeQLOrchestrator initialized (max_concurrent=%d)",
            max_concurrent
        )
    
    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────
    
    async def start_analysis(
        self,
        project_id: str,
        suite: str = "security-extended",
        force_recreate: bool = False,
    ) -> str:
        """
        Start a new analysis job.
        
        Requirements: 12.1, 12.2, 12.3, 12.4
        
        Args:
            project_id: ID of project to analyze
            suite: CodeQL query suite to use
            force_recreate: Force database recreation
        
        Returns:
            job_id for tracking the analysis
        
        Raises:
            ValueError: If project not found
        """
        # Validate project exists
        project = self.project_registry.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        # Create job
        job = AnalysisJob.create(
            project_id=project_id,
            suite=suite,
            force_recreate=force_recreate,
        )
        
        self.jobs[job.job_id] = job
        
        logger.info(
            "Created analysis job %s for project %s (suite=%s, force_recreate=%s)",
            job.job_id, project.name, suite, force_recreate
        )
        
        # Start execution or queue
        if len(self.active_jobs) < self.max_concurrent:
            # Start immediately
            self.active_jobs.add(job.job_id)
            job.status = "running"
            
            # Execute in background (fire and forget)
            asyncio.create_task(self._execute_analysis(job.job_id))
            
            logger.info(
                "Started analysis job %s immediately (active: %d/%d)",
                job.job_id, len(self.active_jobs), self.max_concurrent
            )
        else:
            # Queue for later
            self.job_queue.append(job.job_id)
            job.status = "queued"
            
            logger.info(
                "Queued analysis job %s (queue size: %d, active: %d/%d)",
                job.job_id, len(self.job_queue),
                len(self.active_jobs), self.max_concurrent
            )
        
        return job.job_id
    
    def get_status(self, job_id: str) -> Optional[AnalysisJob]:
        """
        Get current status of an analysis job.
        
        Requirements: 7.1, 7.2, 7.3, 7.6, 7.7
        
        Args:
            job_id: Job ID to query
        
        Returns:
            AnalysisJob object or None if not found
        """
        return self.jobs.get(job_id)
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running or queued analysis job.
        
        Requirements: 12.6, 12.7
        
        Args:
            job_id: Job ID to cancel
        
        Returns:
            True if job was cancelled, False if not found or already completed
        """
        job = self.jobs.get(job_id)
        
        if not job:
            logger.warning("Cannot cancel job %s: not found", job_id)
            return False
        
        if job.status in ("completed", "failed", "cancelled"):
            logger.warning(
                "Cannot cancel job %s: already in terminal state %s",
                job_id, job.status
            )
            return False
        
        # Mark as cancelled
        self._cancelled_jobs.add(job_id)
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        
        # Remove from queue if queued
        if job_id in self.job_queue:
            self.job_queue.remove(job_id)
            logger.info("Cancelled queued job %s", job_id)
        
        # Remove from active jobs if running
        if job_id in self.active_jobs:
            self.active_jobs.remove(job_id)
            logger.info("Cancelled running job %s", job_id)
            
            # Process queue to start next job
            self._process_queue()
        
        return True
    
    def update_progress(
        self,
        job_id: str,
        progress: int,
        current_file: Optional[str] = None,
    ) -> None:
        """
        Update progress for a running job.
        
        Requirements: 7.4, 7.5, 7.6
        
        Args:
            job_id: Job ID to update
            progress: Progress percentage (0-100)
            current_file: Current file being processed (optional)
        """
        job = self.jobs.get(job_id)
        
        if job:
            now = datetime.now(timezone.utc)
            # Keep progress monotonic to avoid UI "going backwards" on retries.
            incoming = max(0, min(100, progress))  # Clamp to 0-100
            if job.status == "running":
                job.progress = max(job.progress, incoming)
            else:
                job.progress = incoming
            job.heartbeat_at = now.isoformat()
            job.elapsed_seconds = self._elapsed_seconds(job.started_at, now)
            job.stage_progress = self._compute_stage_progress(job.stage, job.progress)
            job.eta_seconds = self._compute_eta_seconds(job.progress, job.elapsed_seconds)
            
            if current_file:
                job.current_file = current_file
            
            logger.debug(
                "Job %s progress: %d%% (stage: %s, file: %s)",
                job_id, job.progress, job.stage, current_file or "N/A"
            )

    def set_stage(self, job_id: str, stage: str, initial_progress: int, detail: Optional[str] = None) -> None:
        """Update stage metadata and reset stage telemetry."""
        job = self.jobs.get(job_id)
        if not job:
            return

        now = datetime.now(timezone.utc)
        job.stage = stage
        job.stage_started_at = now.isoformat()
        self.update_progress(job_id, initial_progress, detail)
    
    def cleanup_sarif_files(self) -> dict:
        """
        Perform SARIF file cleanup (old files and disk space check).
        
        Requirements: 13.3, 13.4, 13.6
        
        Returns:
            Dictionary with cleanup statistics
        """
        if not self.sarif_manager:
            logger.debug("SARIF manager not available, skipping cleanup")
            return {
                "old_files_removed": 0,
                "disk_cleanup_removed": 0,
                "total_removed": 0,
            }
        
        try:
            # Cleanup old files (30 days)
            old_files_removed = self.sarif_manager.cleanup_old_files(max_age_days=30)
            
            # Cleanup if disk is full (1 GB minimum)
            disk_cleanup_removed = self.sarif_manager.cleanup_if_disk_full(min_free_gb=1.0)
            
            total_removed = old_files_removed + disk_cleanup_removed
            
            if total_removed > 0:
                logger.info(
                    "SARIF cleanup complete: %d files removed (old: %d, disk: %d)",
                    total_removed, old_files_removed, disk_cleanup_removed
                )
            
            return {
                "old_files_removed": old_files_removed,
                "disk_cleanup_removed": disk_cleanup_removed,
                "total_removed": total_removed,
            }
        
        except Exception as e:
            logger.error("Failed to cleanup SARIF files: %s", e, exc_info=True)
            return {
                "old_files_removed": 0,
                "disk_cleanup_removed": 0,
                "total_removed": 0,
                "error": str(e),
            }
    
    # ──────────────────────────────────────────────
    # Private Implementation
    # ──────────────────────────────────────────────
    
    async def _execute_analysis(self, job_id: str) -> None:
        """
        Execute full analysis workflow for a job.
        
        Workflow:
        1. Database creation/update (stage: database_creation)
        2. CodeQL analysis (stage: analysis)
        3. SARIF ingestion (stage: ingestion)
        
        Requirements: 7.1, 7.2, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 12.1, 12.5
        
        Args:
            job_id: Job ID to execute
        """
        job = self.jobs.get(job_id)
        
        if not job:
            logger.error("Cannot execute job %s: not found", job_id)
            return
        
        project = self.project_registry.get_project(job.project_id)
        
        if not project:
            logger.error(
                "Cannot execute job %s: project %s not found",
                job_id, job.project_id
            )
            job.status = "failed"
            job.error_message = f"Project not found: {job.project_id}"
            job.error_details = {
                "error": "Project not found",
                "category": "invalid_project",
                "job_id": job_id,
                "stage": "initialization"
            }
            job.completed_at = datetime.now(timezone.utc).isoformat()
            self.active_jobs.discard(job_id)
            self._process_queue()
            return
        
        try:
            logger.info(
                "Executing analysis job %s for project %s",
                job_id, project.name
            )
            
            # ──────────────────────────────────────────────
            # Stage 1: Database Management
            # ──────────────────────────────────────────────
            if self._is_cancelled(job_id):
                return
            
            self.set_stage(job_id, "database_creation", 0, "Preparando banco CodeQL")
            
            logger.info("Job %s: Creating/updating database", job_id)
            
            # Scale database creation progress to 0-33% of overall
            def db_progress(p: int) -> None:
                self.update_progress(job_id, int(p * 0.33))
            
            db_path = await asyncio.to_thread(
                self.database_manager.manage_database,
                project,
                job.force_recreate,
                progress_callback=db_progress,
            )
            
            if self._is_cancelled(job_id):
                return
            
            logger.info("Job %s: Database ready at %s", job_id, db_path)
            
            # ──────────────────────────────────────────────
            # Stage 2: Analysis Execution
            # ──────────────────────────────────────────────
            if self._is_cancelled(job_id):
                return
            
            self.set_stage(job_id, "analysis", 34, "Inicializando análise CodeQL")
            
            logger.info("Job %s: Running CodeQL analysis", job_id)
            
            # Scale analysis progress to 34-66% of overall
            def analysis_progress(p: int) -> None:
                overall = 34 + int(p * 0.33)
                if p < 15:
                    detail = "Preparando consultas"
                elif p < 70:
                    detail = "Executando consultas (pode levar alguns minutos)"
                elif p < 95:
                    detail = "Consolidando resultados"
                else:
                    detail = "Finalizando análise"
                self.update_progress(job_id, overall, f"{detail} [{p}% etapa]")
            
            sarif_path = await asyncio.to_thread(
                self.analysis_engine.execute_analysis,
                db_path,
                job.suite,
                output_dir="./codeql-results",
                project_name=project.name,
                progress_callback=analysis_progress,
            )
            
            if self._is_cancelled(job_id):
                return
            
            job.sarif_path = sarif_path
            logger.info("Job %s: SARIF generated at %s", job_id, sarif_path)
            
            # ──────────────────────────────────────────────
            # Stage 3: SARIF Ingestion
            # ──────────────────────────────────────────────
            if self._is_cancelled(job_id):
                return
            
            self.set_stage(job_id, "ingestion", 67, "Preparando ingestão SARIF")
            
            logger.info("Job %s: Ingesting SARIF into Neo4j", job_id)
            
            # Set project root for this analysis
            self.sarif_ingestor.set_project_root(project.source_path)
            
            # Scale ingestion progress to 67-100% of overall
            def ingestion_progress(p: int) -> None:
                self.update_progress(job_id, 67 + int(p * 0.33))
            
            summary = await asyncio.to_thread(
                self.sarif_ingestor.ingest_sarif,
                sarif_path,
                progress_callback=ingestion_progress,
            )
            
            if self._is_cancelled(job_id):
                return
            
            # Check if ingestion had errors
            if "error" in summary:
                logger.error(
                    "Job %s: SARIF ingestion failed: %s",
                    job_id, summary.get("error")
                )
                job.status = "failed"
                job.error_message = summary.get("error", "SARIF ingestion failed")
                job.error_details = {
                    "error": summary.get("error", "SARIF ingestion failed"),
                    "details": summary.get("details", ""),
                    "category": summary.get("category", "ingestion_error"),
                    "job_id": job_id,
                    "stage": "ingestion"
                }
                job.completed_at = datetime.now(timezone.utc).isoformat()
                return
            
            job.results_summary = summary
            logger.info("Job %s: Ingestion complete: %s", job_id, summary)
            
            # ──────────────────────────────────────────────
            # Completion
            # ──────────────────────────────────────────────
            job.status = "completed"
            self.update_progress(job_id, 100, "Concluído")
            job.completed_at = datetime.now(timezone.utc).isoformat()
            
            # Update project last_analyzed timestamp
            self.project_registry.update_last_analyzed(job.project_id)
            
            # Save to history
            self._save_to_history(job, project.name)
            
            # Perform SARIF cleanup after successful analysis (Requirements: 13.3, 13.4, 13.6)
            if self.sarif_manager:
                try:
                    cleanup_stats = self.cleanup_sarif_files()
                    if cleanup_stats.get("total_removed", 0) > 0:
                        logger.info(
                            "Post-analysis cleanup: removed %d SARIF files",
                            cleanup_stats["total_removed"]
                        )
                except Exception as e:
                    logger.warning("Post-analysis cleanup failed: %s", e)
            
            logger.info(
                "Job %s completed successfully (duration: %s)",
                job_id, self._calculate_duration(job)
            )
        
        except DatabaseError as e:
            logger.error(
                "Job %s failed during database stage: %s",
                job_id, e, exc_info=True
            )
            job.status = "failed"
            job.error_message = e.message
            job.error_details = {
                **e.to_dict(),
                "job_id": job_id,
                "stage": job.stage
            }
            job.completed_at = datetime.now(timezone.utc).isoformat()
        
        except AnalysisError as e:
            logger.error(
                "Job %s failed during analysis stage: %s",
                job_id, e, exc_info=True
            )
            job.status = "failed"
            job.error_message = e.message
            job.error_details = {
                **e.to_dict(),
                "job_id": job_id,
                "stage": job.stage
            }
            job.completed_at = datetime.now(timezone.utc).isoformat()
        
        except Exception as e:
            logger.error(
                "Job %s failed with unexpected error: %s",
                job_id, e, exc_info=True
            )
            job.status = "failed"
            job.error_message = f"Unexpected error: {str(e)}"
            job.error_details = {
                "error": "Unexpected error",
                "details": str(e),
                "category": "unexpected_error",
                "job_id": job_id,
                "stage": job.stage
            }
            job.completed_at = datetime.now(timezone.utc).isoformat()
        
        finally:
            # Clean up
            self.active_jobs.discard(job_id)
            self._cancelled_jobs.discard(job_id)
            
            # Process queue to start next job
            self._process_queue()
    
    def _process_queue(self) -> None:
        """
        Process job queue to start next job if capacity available.
        
        Requirements: 12.4, 12.5
        """
        if not self.job_queue:
            return
        
        if len(self.active_jobs) >= self.max_concurrent:
            return
        
        # Start next job from queue
        next_job_id = self.job_queue.popleft()
        next_job = self.jobs.get(next_job_id)
        
        if not next_job:
            logger.warning("Job %s in queue but not found, skipping", next_job_id)
            # Try next job
            self._process_queue()
            return
        
        # Check if cancelled while queued
        if next_job.status == "cancelled":
            logger.info("Job %s was cancelled while queued, skipping", next_job_id)
            # Try next job
            self._process_queue()
            return
        
        # Start execution
        self.active_jobs.add(next_job_id)
        next_job.status = "running"
        
        # Execute in background
        asyncio.create_task(self._execute_analysis(next_job_id))
        
        logger.info(
            "Started queued job %s (active: %d/%d, queue: %d)",
            next_job_id, len(self.active_jobs),
            self.max_concurrent, len(self.job_queue)
        )
    
    def _is_cancelled(self, job_id: str) -> bool:
        """
        Check if a job has been cancelled.
        
        Args:
            job_id: Job ID to check
        
        Returns:
            True if cancelled, False otherwise
        """
        if job_id in self._cancelled_jobs:
            logger.info("Job %s was cancelled, stopping execution", job_id)
            return True
        return False
    
    def _save_to_history(self, job: AnalysisJob, project_name: str) -> None:
        """
        Save completed job to analysis history.
        
        Requirements: 9.1, 9.2, 9.3
        
        Args:
            job: Completed AnalysisJob
            project_name: Name of the project
        """
        try:
            # Calculate SARIF file size if available
            sarif_size = None
            if job.sarif_path:
                try:
                    sarif_size = Path(job.sarif_path).stat().st_size
                except Exception as e:
                    logger.warning(
                        "Could not get SARIF file size for %s: %s",
                        job.sarif_path, e
                    )
            
            # Create history entry
            entry = AnalysisHistoryEntry(
                job_id=job.job_id,
                project_id=job.project_id,
                project_name=project_name,
                started_at=job.started_at,
                completed_at=job.completed_at,
                duration_seconds=self._calculate_duration_seconds(job),
                suite=job.suite,
                status=job.status,
                results_summary=job.results_summary,
                sarif_path=job.sarif_path,
                sarif_size_bytes=sarif_size,
                error_message=job.error_message,
            )
            
            self.analysis_history.add_entry(entry)
            
            logger.info("Saved job %s to history", job.job_id)
        
        except Exception as e:
            logger.error(
                "Failed to save job %s to history: %s",
                job.job_id, e, exc_info=True
            )
    
    def _calculate_duration(self, job: AnalysisJob) -> str:
        """
        Calculate human-readable duration for a job.
        
        Args:
            job: AnalysisJob to calculate duration for
        
        Returns:
            Duration string (e.g., "2m 30s")
        """
        try:
            duration_seconds = self._calculate_duration_seconds(job)
            
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            
            if minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        
        except Exception:
            return "unknown"
    
    def _calculate_duration_seconds(self, job: AnalysisJob) -> float:
        """
        Calculate duration in seconds for a job.
        
        Args:
            job: AnalysisJob to calculate duration for
        
        Returns:
            Duration in seconds
        """
        try:
            started = self._parse_iso_datetime(job.started_at)
            completed = self._parse_iso_datetime(job.completed_at)
            duration = (completed - started).total_seconds()
            return duration
        except Exception:
            return 0.0

    def _elapsed_seconds(self, started_at: str, now: datetime) -> int:
        """Calculate elapsed seconds from an ISO timestamp."""
        try:
            started = self._parse_iso_datetime(started_at)
            return max(0, int((now - started).total_seconds()))
        except Exception:
            return 0

    def _parse_iso_datetime(self, value: Optional[str]) -> datetime:
        """Parse ISO datetime and normalize to timezone-aware UTC."""
        if not value:
            return datetime.now(timezone.utc)

        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _compute_eta_seconds(self, progress: int, elapsed_seconds: int) -> Optional[int]:
        """
        Estimate remaining time from overall progress and elapsed time.
        Returns None when estimate is not reliable yet.
        """
        if progress <= 3 or progress >= 100 or elapsed_seconds <= 0:
            return None

        # Simple linear projection on overall progress.
        total_estimated = elapsed_seconds * (100.0 / progress)
        remaining = int(max(0.0, total_estimated - elapsed_seconds))
        return remaining

    def _compute_stage_progress(self, stage: str, overall_progress: int) -> int:
        """Map overall progress (0-100) to current stage progress (0-100)."""
        stage_ranges = {
            "database_creation": (0, 33),
            "analysis": (34, 66),
            "ingestion": (67, 100),
        }
        start, end = stage_ranges.get(stage, (0, 100))
        if overall_progress <= start:
            return 0
        if overall_progress >= end:
            return 100

        span = max(1, end - start)
        return int(((overall_progress - start) / span) * 100)
