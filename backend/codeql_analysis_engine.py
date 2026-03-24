"""
CodeQL Analysis Engine

Executes CodeQL analysis on prepared databases and generates SARIF output files.

Responsibilities:
- Execute CodeQL analysis on prepared databases
- Support different query suites (security-extended, security-and-quality, security-critical)
- Generate SARIF output files with unique timestamps
- Report progress during analysis
- Handle timeouts and errors
- Cache analysis results to avoid reprocessing unchanged code

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 14.2, 14.3, 14.5
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("insightgraph")


class AnalysisEngine:
    """
    Executes CodeQL analysis and generates SARIF output.
    
    Usage:
        engine = AnalysisEngine(codeql_path="/path/to/codeql")
        sarif_path = engine.execute_analysis(
            database_path="/path/to/db",
            suite="security-extended",
            output_dir="./codeql-results",
            project_name="my-project",
            progress_callback=lambda p: print(f"Progress: {p}%")
        )
    """
    
    # Valid query suites
    VALID_SUITES = [
        "security-extended",
        "security-and-quality",
        "security-critical",
    ]
    
    # Default timeout in seconds
    DEFAULT_TIMEOUT = 600
    
    def __init__(self, codeql_path: str = "codeql", timeout: int = DEFAULT_TIMEOUT):
        """
        Args:
            codeql_path: Path to CodeQL CLI executable (default: "codeql" in PATH)
            timeout: Analysis timeout in seconds (default: 600)
        """
        self.codeql_path = codeql_path
        self.timeout = timeout
        self.analysis_threads = os.getenv("CODEQL_ANALYZE_THREADS", "0")
        self.analysis_ram = os.getenv("CODEQL_ANALYZE_RAM", "0")
        self._cache_file = Path(".codeql_analysis_cache.json")
        self._load_cache()
        logger.info(
            "AnalysisEngine initialized with codeql_path=%s, timeout=%ds, threads=%s, ram=%s",
            codeql_path,
            timeout,
            self.analysis_threads,
            self.analysis_ram,
        )
    
    def _load_cache(self) -> None:
        """Load analysis cache from disk."""
        try:
            if self._cache_file.exists():
                with open(self._cache_file, 'r') as f:
                    self._cache = json.load(f)
            else:
                self._cache = {}
        except Exception as e:
            logger.warning("Failed to load analysis cache: %s", e)
            self._cache = {}
    
    def _save_cache(self) -> None:
        """Save analysis cache to disk."""
        try:
            with open(self._cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save analysis cache: %s", e)
    
    def _get_database_hash(self, database_path: Path) -> str:
        """
        Calculate hash of database to detect changes.
        
        Args:
            database_path: Path to database directory
        
        Returns:
            SHA256 hash of database metadata
        """
        try:
            db_yml = database_path / "codeql-database.yml"
            if db_yml.exists():
                # Hash the database metadata file
                with open(db_yml, 'rb') as f:
                    return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.warning("Failed to calculate database hash: %s", e)
        return ""
    
    def _check_cache(self, database_path: Path, suite: str) -> Optional[str]:
        """
        Check if we have a cached SARIF for this database and suite.
        
        Args:
            database_path: Path to database directory
            suite: Query suite used
        
        Returns:
            Path to cached SARIF file if valid, None otherwise
        """
        try:
            db_hash = self._get_database_hash(database_path)
            if not db_hash:
                return None
            
            cache_key = f"{database_path}:{suite}"
            cached = self._cache.get(cache_key)
            
            if cached and cached.get("db_hash") == db_hash:
                sarif_path = Path(cached.get("sarif_path", ""))
                if sarif_path.exists():
                    logger.info(
                        "Found cached SARIF for database %s with suite %s",
                        database_path.name, suite
                    )
                    return str(sarif_path)
        except Exception as e:
            logger.warning("Failed to check cache: %s", e)
        
        return None
    
    def _update_cache(self, database_path: Path, suite: str, sarif_path: str) -> None:
        """
        Update cache with new analysis result.
        
        Args:
            database_path: Path to database directory
            suite: Query suite used
            sarif_path: Path to generated SARIF file
        """
        try:
            db_hash = self._get_database_hash(database_path)
            if not db_hash:
                return
            
            cache_key = f"{database_path}:{suite}"
            self._cache[cache_key] = {
                "db_hash": db_hash,
                "sarif_path": sarif_path,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._save_cache()
            logger.info("Updated analysis cache for %s", cache_key)
        except Exception as e:
            logger.warning("Failed to update cache: %s", e)
    
    # ──────────────────────────────────────────────
    # Path Validation
    # ──────────────────────────────────────────────
    
    def _validate_path(self, path: str, path_type: str = "path") -> Path:
        """
        Validate and sanitize file paths to prevent directory traversal.
        
        Requirements: 8.3, 8.4
        
        Args:
            path: Path to validate
            path_type: Type of path for error messages (e.g., "database", "output")
        
        Returns:
            Validated Path object
        
        Raises:
            AnalysisError: If path contains directory traversal or is invalid
        """
        try:
            path_obj = Path(path).resolve()
            
            # Check for directory traversal attempts
            if ".." in str(path):
                logger.error(
                    "Directory traversal attempt detected in %s path: %s",
                    path_type, path
                )
                raise AnalysisError(
                    f"Invalid {path_type} path: directory traversal not allowed",
                    details=f"Path contains '..' which is not permitted",
                    category="invalid_path",
                )
            
            return path_obj
        
        except Exception as e:
            if isinstance(e, AnalysisError):
                raise
            
            logger.error(
                "Path validation failed for %s path '%s': %s",
                path_type, path, e
            )
            raise AnalysisError(
                f"Invalid {path_type} path",
                details=str(e),
                category="invalid_path",
            )
    
    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────
    
    def execute_analysis(
        self,
        database_path: str,
        suite: str = "security-extended",
        output_dir: str = "./codeql-results",
        project_name: Optional[str] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Execute CodeQL analysis on a database and generate SARIF output.
        
        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 14.2, 14.3, 14.5
        
        Args:
            database_path: Path to CodeQL database directory
            suite: Query suite to use (default: "security-extended")
            output_dir: Directory to store SARIF output (default: "./codeql-results")
            project_name: Project name for SARIF filename (optional, uses database name if not provided)
            progress_callback: Optional callback for progress updates (0-100)
        
        Returns:
            Path to the generated SARIF file
        
        Raises:
            AnalysisError: If analysis fails or times out
        """
        try:
            # Validate suite first (before path validation)
            if suite not in self.VALID_SUITES:
                logger.error("Invalid query suite: %s", suite)
                raise AnalysisError(
                    "Invalid query suite",
                    details=f"Suite '{suite}' is not valid. "
                            f"Valid suites: {', '.join(self.VALID_SUITES)}",
                    category="invalid_suite",
                )
            
            # Validate paths
            database_path_obj = self._validate_path(database_path, "database")
            output_dir_obj = self._validate_path(output_dir, "output")
            
            # Validate database exists
            if not database_path_obj.exists():
                logger.error("Database does not exist: %s", database_path)
                raise AnalysisError(
                    "Database does not exist",
                    details=f"Path: {database_path}",
                    category="invalid_database",
                )
            
            if not (database_path_obj / "codeql-database.yml").exists():
                logger.error("Invalid database directory: %s", database_path)
                raise AnalysisError(
                    "Invalid database directory",
                    details="Missing codeql-database.yml file",
                    category="invalid_database",
                )
            
            # Check cache for existing analysis
            cached_sarif = self._check_cache(database_path_obj, suite)
            if cached_sarif:
                logger.info(
                    "Using cached SARIF for database %s (suite: %s)",
                    database_path_obj.name, suite
                )
                if progress_callback:
                    progress_callback(100)
                return cached_sarif
            
            # Generate unique SARIF output path with timestamp
            sarif_path = self._generate_sarif_path(output_dir_obj, project_name, database_path_obj)
            
            # Ensure output directory exists
            output_dir_obj.mkdir(parents=True, exist_ok=True)
            
            # Build command with optimizations
            # Map suite names to actual query suite files
            suite_mapping = {
                "security-extended": "java-security-extended.qls",
                "security-and-quality": "java-security-and-quality.qls",
                "security-critical": "java-security-extended.qls",  # Use extended for critical
            }
            
            # Get the query suite file name
            suite_file = suite_mapping.get(suite, suite)
            
            # Check if we need to use full path to queries
            queries_path = Path("C:/codeql/codeql-repo/java/ql/src/codeql-suites") / suite_file
            if queries_path.exists():
                query_arg = str(queries_path)
                logger.info("Using query suite from repository: %s", query_arg)
            else:
                # Fallback to suite name (if packs are installed)
                query_arg = suite
                logger.info("Using query suite name: %s", query_arg)

            profiles = self._build_analysis_profiles()
            last_error: Optional[subprocess.CalledProcessError] = None

            for index, (threads, ram, label) in enumerate(profiles, start=1):
                cmd = [
                    self.codeql_path,
                    "database",
                    "analyze",
                    str(database_path_obj),
                    query_arg,
                    "--format=sarif-latest",
                    f"--output={sarif_path}",
                    f"--threads={threads}",
                    f"--ram={ram}",
                ]

                logger.info(
                    "Executing CodeQL analysis (profile %d/%d: %s, threads=%s, ram=%s): %s",
                    index,
                    len(profiles),
                    label,
                    threads,
                    ram,
                    " ".join(cmd),
                )
                logger.info("Suite: %s, Timeout: %ds", suite, self.timeout)

                try:
                    # Execute with progress tracking and timeout
                    self._execute_with_progress(
                        cmd,
                        progress_callback=progress_callback,
                        operation="Analysis",
                    )
                    last_error = None
                    break
                except subprocess.CalledProcessError as e:
                    last_error = e
                    if self._is_oom_error(e) and index < len(profiles):
                        logger.warning(
                            "Analysis ran out of memory with threads=%s, ram=%s. Retrying with safer profile...",
                            threads,
                            ram,
                        )
                        continue
                    raise

            if last_error is not None:
                raise last_error
            
            # Verify SARIF was created
            if not sarif_path.exists():
                logger.error(
                    "Analysis completed but SARIF file was not created: %s",
                    sarif_path
                )
                raise AnalysisError(
                    "SARIF file not created",
                    details=f"Expected file at: {sarif_path}",
                    category="sarif_generation_failed",
                )
            
            # Update cache with successful analysis
            self._update_cache(database_path_obj, suite, str(sarif_path))
            
            logger.info("Analysis completed successfully, SARIF: %s", sarif_path)
            return str(sarif_path)
        
        except subprocess.TimeoutExpired:
            logger.error(
                "Analysis exceeded timeout of %d seconds",
                self.timeout, exc_info=True
            )
            raise AnalysisError(
                "Analysis timeout",
                details=f"Analysis exceeded timeout of {self.timeout} seconds. "
                        "Consider using a more focused query suite (e.g., security-critical) "
                        "or increasing the timeout.",
                category="timeout",
            )
        
        except subprocess.CalledProcessError as e:
            logger.error(
                "Analysis failed with exit code %d: %s",
                e.returncode, e.stderr, exc_info=True
            )
            raise AnalysisError(
                "Analysis failed",
                details=f"CodeQL CLI returned exit code {e.returncode}",
                stderr=e.stderr if hasattr(e, 'stderr') else None,
                category="analysis_failed",
            )
        
        except FileNotFoundError:
            logger.error("CodeQL CLI not found at: %s", self.codeql_path)
            raise AnalysisError(
                "CodeQL CLI not found",
                details=f"Expected location: {self.codeql_path}. "
                        "Install from https://github.com/github/codeql-cli-binaries",
                category="codeql_not_found",
            )
        
        except AnalysisError:
            # Re-raise AnalysisError as-is
            raise
        
        except Exception as e:
            logger.error(
                "Unexpected error during analysis: %s",
                e, exc_info=True
            )
            raise AnalysisError(
                "Failed to execute analysis",
                details=str(e),
                category="analysis_error",
            )
    
    # ──────────────────────────────────────────────
    # Private Helpers
    # ──────────────────────────────────────────────
    
    def _generate_sarif_path(
        self,
        output_dir: Path,
        project_name: Optional[str],
        database_path: Path,
    ) -> Path:
        """
        Generate unique SARIF output path with timestamp.
        
        Requirements: 3.5, 13.2
        
        Args:
            output_dir: Directory to store SARIF
            project_name: Project name (optional)
            database_path: Database path (used as fallback for name)
        
        Returns:
            Path to SARIF file
        """
        # Use project name or database directory name
        if not project_name:
            project_name = database_path.name
        
        # Sanitize project name for filename
        safe_name = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in project_name
        )
        
        # Generate timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Build filename: {project_name}_{timestamp}.sarif
        filename = f"{safe_name}_{timestamp}.sarif"
        
        return output_dir / filename

    def _build_analysis_profiles(self) -> list[tuple[str, str, str]]:
        """
        Build analysis execution profiles.

        First attempt uses configured threads/ram, then progressively safer
        fallbacks to recover from OOM automatically.
        """
        profiles: list[tuple[str, str, str]] = [
            (self.analysis_threads, self.analysis_ram, "configured"),
        ]
        profiles.extend([
            ("6", "12288", "balanced"),
            ("4", "8192", "conservative"),
            ("2", "6144", "low-memory"),
        ])

        # De-duplicate while preserving order.
        unique: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for threads, ram, label in profiles:
            key = (threads, ram)
            if key in seen:
                continue
            seen.add(key)
            unique.append((threads, ram, label))
        return unique

    def _is_oom_error(self, error: subprocess.CalledProcessError) -> bool:
        """Detect out-of-memory failures from CodeQL stderr/output."""
        text = f"{getattr(error, 'stderr', '')}\n{getattr(error, 'output', '')}".lower()
        return (
            error.returncode == 99
            and ("out of memory" in text or "--ram option" in text or "ran out of memory" in text)
        )
    
    def _execute_with_progress(
        self,
        cmd: list[str],
        progress_callback: Optional[Callable[[int], None]],
        operation: str,
    ) -> None:
        """
        Execute a command with progress reporting and timeout.
        
        Requirements: 3.4, 3.7
        
        Args:
            cmd: Command to execute
            progress_callback: Optional callback for progress updates
            operation: Description of operation for logging
        
        Raises:
            subprocess.TimeoutExpired: If command exceeds timeout
            subprocess.CalledProcessError: If command fails
        """
        # Report initial progress
        if progress_callback:
            progress_callback(0)
        
        # Execute command with timeout
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        
        # Track progress by monitoring output
        progress = 0
        stderr_lines: deque[str] = deque(maxlen=2000)
        start_time = time.time()

        def _read_stderr() -> None:
            """Read stderr in background to avoid blocking and expose progress."""
            nonlocal progress
            try:
                for line in process.stderr:
                    if len(line) > 4000:
                        line = line[:4000] + " ... [truncated]\n"
                    stderr_lines.append(line)

                    # Heuristic progress based on CodeQL analysis phases
                    if "Loading" in line or "Preparing" in line:
                        progress = min(progress + 3, 30)
                    elif "Evaluating" in line or "Running" in line:
                        progress = min(progress + 2, 85)
                    elif "Writing" in line or "Finalizing" in line:
                        progress = max(progress, 90)

                    if progress_callback:
                        progress_callback(progress)

                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("%s: %s", operation, line.strip())
            except (ValueError, OSError):
                # Process was killed / stderr closed
                pass

        reader_thread = threading.Thread(target=_read_stderr, daemon=True)
        reader_thread.start()
        
        try:
            # Wait with periodic checks, timeout control, and time-based fallback progress
            while True:
                try:
                    process.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.time() - start_time
                    if elapsed > self.timeout:
                        self._terminate_process_tree(process, operation)
                        raise subprocess.TimeoutExpired(
                            cmd,
                            self.timeout,
                            output="".join(stderr_lines),
                        )

                    # Keep progress moving even when CodeQL output is sparse.
                    # Map elapsed time to up to 95%.
                    time_progress = min(int((elapsed / self.timeout) * 95), 95)
                    effective_progress = max(progress, time_progress)
                    if progress_callback and effective_progress > progress:
                        progress = effective_progress
                        progress_callback(progress)

            # Ensure stderr consumer had a chance to flush final lines
            reader_thread.join(timeout=5)
            
            # Report completion
            if progress_callback:
                progress_callback(100)
            
            # Check exit code
            if process.returncode != 0:
                stderr = "".join(stderr_lines)
                error = subprocess.CalledProcessError(
                    process.returncode, cmd, stderr=stderr
                )
                raise error
        
        except subprocess.TimeoutExpired:
            # Ensure process is terminated
            if process.poll() is None:
                self._terminate_process_tree(process, operation)
            raise
        
        except Exception:
            # Ensure process is terminated on any error
            if process.poll() is None:
                self._terminate_process_tree(process, operation)
            raise

    def _terminate_process_tree(self, process: subprocess.Popen, operation: str) -> None:
        """Terminate process tree to avoid lingering child processes on Windows."""
        try:
            if process.poll() is not None:
                return

            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            else:
                process.kill()

            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "%s process did not exit cleanly after termination (pid=%s)",
                    operation,
                    process.pid,
                )
        except Exception as e:
            logger.warning(
                "Failed to terminate process tree for %s (pid=%s): %s",
                operation,
                process.pid,
                e,
            )


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class AnalysisError(Exception):
    """
    Raised when analysis operations fail.
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
    
    Attributes:
        message: User-friendly error message
        details: Additional technical details
        stderr: CodeQL CLI stderr output (if applicable)
        category: Error category for classification
    """
    
    def __init__(
        self,
        message: str,
        details: Optional[str] = None,
        stderr: Optional[str] = None,
        category: str = "analysis_error",
    ):
        """
        Args:
            message: User-friendly error message
            details: Additional technical details
            stderr: CodeQL CLI stderr output
            category: Error category (codeql_not_found, invalid_database, analysis_failed, timeout, etc.)
        """
        super().__init__(message)
        self.message = message
        self.details = details
        self.stderr = stderr
        self.category = category
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        result = {
            "error": self.message,
            "category": self.category,
        }
        if self.details:
            result["details"] = self.details
        if self.stderr:
            result["stderr"] = self._sanitize_stderr(self.stderr)
        return result
    
    @staticmethod
    def _sanitize_stderr(stderr: str) -> str:
        """
        Sanitize stderr to remove sensitive information.
        
        Requirements: 8.4, 8.5
        
        Removes:
        - Absolute paths (replace with relative paths)
        - User names
        - System-specific information
        """
        import re
        
        # Replace absolute Windows paths with relative
        stderr = re.sub(r'[A-Z]:\\[^:\s]+', '[PATH]', stderr)
        
        # Replace absolute Unix paths with relative
        stderr = re.sub(r'/(?:home|Users)/[^/\s]+', '[PATH]', stderr)
        
        # Replace user names
        stderr = re.sub(r'user[:\s]+\w+', 'user: [USER]', stderr, flags=re.IGNORECASE)
        
        # Limit length to prevent information leakage
        if len(stderr) > 1000:
            stderr = stderr[:1000] + "... (truncated)"
        
        return stderr
