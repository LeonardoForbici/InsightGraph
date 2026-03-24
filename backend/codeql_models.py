"""
CodeQL Data Models and Persistence

Provides data models and JSON-based persistence for:
- CodeQL project configurations (codeql_projects.json)
- Analysis job tracking (in-memory with history persistence)
- Analysis history (codeql_history.json)

Requirements: 6.4, 6.7, 9.2, 9.3, 13.1
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("insightgraph")


# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

@dataclass
class CodeQLProject:
    """
    Represents a project configured for CodeQL analysis.
    
    Requirements: 6.4, 6.7
    """
    id: str
    name: str
    source_path: str
    language: str
    database_path: str
    created_at: str
    last_analyzed: Optional[str] = None
    
    @staticmethod
    def create(
        name: str,
        source_path: str,
        language: str,
        database_path: str,
    ) -> CodeQLProject:
        """Create a new project with generated ID and timestamp."""
        return CodeQLProject(
            id=str(uuid.uuid4()),
            name=name,
            source_path=source_path,
            language=language,
            database_path=database_path,
            created_at=datetime.utcnow().isoformat(),
            last_analyzed=None,
        )


@dataclass
class IngestionSummary:
    """
    Summary of SARIF ingestion results.
    
    Requirements: 9.3
    """
    total_issues: int = 0
    ingested: int = 0
    skipped: int = 0
    tainted_paths: int = 0
    vulnerabilities_by_severity: dict[str, int] = field(default_factory=dict)


@dataclass
class AnalysisJob:
    """
    Represents an analysis job (queued, running, or completed).
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.2, 9.3
    """
    job_id: str
    project_id: str
    status: str  # queued | running | completed | failed | cancelled
    stage: str  # database_creation | analysis | ingestion
    progress: int  # 0-100
    suite: str
    force_recreate: bool
    started_at: str
    current_file: Optional[str] = None
    stage_progress: int = 0  # 0-100 within current stage
    elapsed_seconds: int = 0
    eta_seconds: Optional[int] = None
    heartbeat_at: Optional[str] = None
    stage_started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None  # Structured error information (Requirements: 8.1, 8.2, 8.4, 8.5)
    sarif_path: Optional[str] = None
    results_summary: Optional[dict] = None
    
    @staticmethod
    def create(
        project_id: str,
        suite: str = "security-extended",
        force_recreate: bool = False,
    ) -> AnalysisJob:
        """Create a new analysis job with generated ID and timestamp."""
        return AnalysisJob(
            job_id=str(uuid.uuid4()),
            project_id=project_id,
            status="queued",
            stage="database_creation",
            progress=0,
            suite=suite,
            force_recreate=force_recreate,
            started_at=datetime.now(timezone.utc).isoformat(),
            heartbeat_at=datetime.now(timezone.utc).isoformat(),
            stage_started_at=datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class AnalysisHistoryEntry:
    """
    Historical record of a completed analysis.
    
    Requirements: 9.2, 9.3, 13.1
    """
    job_id: str
    project_id: str
    project_name: str
    started_at: str
    completed_at: str
    duration_seconds: float
    suite: str
    status: str  # completed | failed
    results_summary: Optional[dict] = None
    sarif_path: Optional[str] = None
    sarif_size_bytes: Optional[int] = None
    error_message: Optional[str] = None


# ──────────────────────────────────────────────
# Project Registry Persistence
# ──────────────────────────────────────────────

class ProjectRegistry:
    """
    Manages project configurations with JSON persistence.
    
    Requirements: 6.4, 6.7
    """
    
    def __init__(self, registry_path: str = "codeql_projects.json"):
        """
        Args:
            registry_path: Path to JSON file storing project configurations
        """
        self.registry_path = Path(registry_path)
        self._projects: dict[str, CodeQLProject] = {}
        self._load()
    
    def add_project(self, project: CodeQLProject) -> None:
        """Add or update a project in the registry."""
        self._projects[project.id] = project
        self._save()
        logger.info("Added project to registry: %s (id=%s)", project.name, project.id)
    
    def get_project(self, project_id: str) -> Optional[CodeQLProject]:
        """Retrieve a project by ID."""
        return self._projects.get(project_id)
    
    def list_projects(self) -> list[CodeQLProject]:
        """List all registered projects."""
        return list(self._projects.values())
    
    def remove_project(self, project_id: str) -> bool:
        """
        Remove a project from the registry.
        
        Returns:
            True if project was removed, False if not found
        """
        if project_id in self._projects:
            project = self._projects.pop(project_id)
            self._save()
            logger.info("Removed project from registry: %s (id=%s)", project.name, project_id)
            return True
        return False
    
    def update_last_analyzed(self, project_id: str, timestamp: Optional[str] = None) -> None:
        """Update the last_analyzed timestamp for a project."""
        if project_id in self._projects:
            if timestamp is None:
                timestamp = datetime.utcnow().isoformat()
            self._projects[project_id].last_analyzed = timestamp
            self._save()
    
    def _load(self) -> None:
        """Load projects from JSON file."""
        if not self.registry_path.exists():
            logger.info("Project registry not found, creating new: %s", self.registry_path)
            self._projects = {}
            self._save()
            return
        
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._projects = {
                p["id"]: CodeQLProject(**p)
                for p in data.get("projects", [])
            }
            logger.info("Loaded %d projects from registry", len(self._projects))
        
        except json.JSONDecodeError as e:
            logger.error("Failed to parse project registry JSON: %s", e)
            self._projects = {}
        except Exception as e:
            logger.error("Failed to load project registry: %s", e)
            self._projects = {}
    
    def _save(self) -> None:
        """Save projects to JSON file."""
        try:
            data = {
                "projects": [asdict(p) for p in self._projects.values()]
            }
            
            # Ensure parent directory exists
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug("Saved %d projects to registry", len(self._projects))
        
        except Exception as e:
            logger.error("Failed to save project registry: %s", e)


# ──────────────────────────────────────────────
# Analysis History Persistence
# ──────────────────────────────────────────────

class AnalysisHistory:
    """
    Manages analysis history with JSON persistence and retention policy.
    
    Requirements: 9.2, 9.3, 13.1
    """
    
    MAX_ENTRIES = 100  # Requirement 9.6, 9.7
    
    def __init__(self, history_path: str = "codeql_history.json"):
        """
        Args:
            history_path: Path to JSON file storing analysis history
        """
        self.history_path = Path(history_path)
        self._entries: list[AnalysisHistoryEntry] = []
        self._load()
    
    def add_entry(self, entry: AnalysisHistoryEntry) -> None:
        """
        Add an analysis history entry.
        
        Automatically enforces retention policy (max 100 entries).
        Requirements: 9.6, 9.7
        """
        self._entries.append(entry)
        
        # Enforce retention policy: keep only last MAX_ENTRIES
        if len(self._entries) > self.MAX_ENTRIES:
            removed_count = len(self._entries) - self.MAX_ENTRIES
            self._entries = self._entries[-self.MAX_ENTRIES:]
            logger.info("Removed %d oldest history entries (retention policy)", removed_count)
        
        self._save()
        logger.info("Added history entry: job_id=%s, project=%s", entry.job_id, entry.project_name)
    
    def get_entry(self, job_id: str) -> Optional[AnalysisHistoryEntry]:
        """Retrieve a history entry by job ID."""
        for entry in self._entries:
            if entry.job_id == job_id:
                return entry
        return None
    
    def list_entries(
        self,
        project_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[AnalysisHistoryEntry]:
        """
        List history entries with optional filtering.
        
        Requirements: 9.1, 9.2, 9.3
        
        Args:
            project_id: Filter by project ID (optional)
            start_date: Filter entries started on or after this date (ISO format, optional)
            end_date: Filter entries started on or before this date (ISO format, optional)
            limit: Maximum number of entries to return (optional)
        
        Returns:
            List of entries, most recent first
        """
        entries = self._entries
        
        # Filter by project if specified
        if project_id:
            entries = [e for e in entries if e.project_id == project_id]
        
        # Filter by date range if specified
        if start_date:
            entries = [e for e in entries if e.started_at >= start_date]
        
        if end_date:
            entries = [e for e in entries if e.started_at <= end_date]
        
        # Sort by started_at descending (most recent first)
        entries = sorted(entries, key=lambda e: e.started_at, reverse=True)
        
        # Apply limit if specified
        if limit:
            entries = entries[:limit]
        
        return entries
    
    def _load(self) -> None:
        """Load history from JSON file."""
        if not self.history_path.exists():
            logger.info("Analysis history not found, creating new: %s", self.history_path)
            self._entries = []
            self._save()
            return
        
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._entries = [
                AnalysisHistoryEntry(**e)
                for e in data.get("analyses", [])
            ]
            logger.info("Loaded %d history entries", len(self._entries))
        
        except json.JSONDecodeError as e:
            logger.error("Failed to parse history JSON: %s", e)
            self._entries = []
        except Exception as e:
            logger.error("Failed to load history: %s", e)
            self._entries = []
    
    def _save(self) -> None:
        """Save history to JSON file."""
        try:
            data = {
                "analyses": [asdict(e) for e in self._entries]
            }
            
            # Ensure parent directory exists
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug("Saved %d history entries", len(self._entries))
        
        except Exception as e:
            logger.error("Failed to save history: %s", e)


# ──────────────────────────────────────────────
# Utility Functions
# ──────────────────────────────────────────────

def load_projects(registry_path: str = "codeql_projects.json") -> list[CodeQLProject]:
    """
    Convenience function to load all projects from registry.
    
    Args:
        registry_path: Path to project registry JSON file
    
    Returns:
        List of CodeQLProject objects
    """
    registry = ProjectRegistry(registry_path)
    return registry.list_projects()


def save_project(
    project: CodeQLProject,
    registry_path: str = "codeql_projects.json",
) -> None:
    """
    Convenience function to save a project to registry.
    
    Args:
        project: CodeQLProject to save
        registry_path: Path to project registry JSON file
    """
    registry = ProjectRegistry(registry_path)
    registry.add_project(project)


def load_history(
    history_path: str = "codeql_history.json",
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[AnalysisHistoryEntry]:
    """
    Convenience function to load analysis history.
    
    Requirements: 9.1, 9.2, 9.3
    
    Args:
        history_path: Path to history JSON file
        project_id: Filter by project ID (optional)
        start_date: Filter entries started on or after this date (ISO format, optional)
        end_date: Filter entries started on or before this date (ISO format, optional)
        limit: Maximum number of entries (optional)
    
    Returns:
        List of AnalysisHistoryEntry objects, most recent first
    """
    history = AnalysisHistory(history_path)
    return history.list_entries(
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )


def save_history_entry(
    entry: AnalysisHistoryEntry,
    history_path: str = "codeql_history.json",
) -> None:
    """
    Convenience function to save a history entry.
    
    Args:
        entry: AnalysisHistoryEntry to save
        history_path: Path to history JSON file
    """
    history = AnalysisHistory(history_path)
    history.add_entry(entry)
