"""
CodeQL Database Manager

Manages CodeQL database creation and updates for projects.

Responsibilities:
- Check if CodeQL database exists for a project
- Create new databases using `codeql database create`
- Update existing databases using `codeql database upgrade`
- Detect project language automatically
- Report progress during database operations

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
"""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import time
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("insightgraph")


class DatabaseManager:
    """
    Manages CodeQL database lifecycle for projects.
    
    Usage:
        manager = DatabaseManager(codeql_path="/path/to/codeql")
        db_path = manager.manage_database(
            project,
            force_recreate=False,
            progress_callback=lambda p: print(f"Progress: {p}%")
        )
    """
    
    # Language detection patterns
    LANGUAGE_PATTERNS = {
        "java": [".java", "pom.xml", "build.gradle", "build.gradle.kts"],
        "javascript": ["package.json", ".js", ".jsx"],
        "typescript": ["tsconfig.json", ".ts", ".tsx"],
        "python": [".py", "requirements.txt", "setup.py", "pyproject.toml"],
        "csharp": [".cs", ".csproj", ".sln"],
        "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
        "go": ["go.mod", ".go"],
        "ruby": [".rb", "Gemfile"],
    }
    
    # Default timeout for database operations (seconds)
    DEFAULT_TIMEOUT = 600
    FINALIZE_TIMEOUT = 300

    def __init__(self, codeql_path: str = "codeql", timeout: int = DEFAULT_TIMEOUT):
        """
        Args:
            codeql_path: Path to CodeQL CLI executable (default: "codeql" in PATH)
            timeout: Timeout in seconds for database operations (default: 600)
        """
        self.codeql_path = codeql_path
        self.timeout = timeout
        self.db_threads = os.getenv("CODEQL_DB_THREADS", "0")
        self.db_ram = os.getenv("CODEQL_DB_RAM", "0")
        logger.info(
            "DatabaseManager initialized with codeql_path=%s, timeout=%ds, threads=%s, ram=%s",
            codeql_path,
            timeout,
            self.db_threads,
            self.db_ram,
        )
    
    # ──────────────────────────────────────────────
    # Path Validation
    # ──────────────────────────────────────────────
    
    def _validate_path(self, path: str, path_type: str = "path") -> Path:
        """
        Validate and sanitize file paths to prevent directory traversal.
        
        Requirements: 8.3, 8.4
        
        Args:
            path: Path to validate
            path_type: Type of path for error messages (e.g., "source", "database")
        
        Returns:
            Validated Path object
        
        Raises:
            DatabaseError: If path contains directory traversal or is invalid
        """
        try:
            path_obj = Path(path).resolve()
            
            # Check for directory traversal attempts
            if ".." in str(path):
                logger.error(
                    "Directory traversal attempt detected in %s path: %s",
                    path_type, path
                )
                raise DatabaseError(
                    f"Invalid {path_type} path: directory traversal not allowed",
                    details=f"Path contains '..' which is not permitted",
                    category="invalid_path",
                )
            
            return path_obj
        
        except Exception as e:
            if isinstance(e, DatabaseError):
                raise
            
            logger.error(
                "Path validation failed for %s path '%s': %s",
                path_type, path, e
            )
            raise DatabaseError(
                f"Invalid {path_type} path",
                details=str(e),
                category="invalid_path",
            )
    
    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────
    
    def manage_database(
        self,
        project,
        force_recreate: bool = False,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Manage CodeQL database for a project (create or update).
        
        Requirements: 2.1, 2.2, 2.3, 2.5, 2.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
        
        Args:
            project: CodeQLProject instance
            force_recreate: If True, always create new database
            progress_callback: Optional callback for progress updates (0-100)
        
        Returns:
            Path to the database directory
        
        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Validate paths
            source_path = self._validate_path(project.source_path, "source")
            db_path = self._validate_path(project.database_path, "database")
            
            # Check if database exists and is valid
            db_exists = db_path.exists() and (db_path / "codeql-database.yml").exists()
            
            if force_recreate:
                logger.info(
                    "Force recreate enabled for project %s, creating new database",
                    project.name
                )
                return self.create_database(
                    str(source_path),
                    str(db_path),
                    project.language,
                    progress_callback=progress_callback,
                )
            
            if not db_exists:
                logger.info(
                    "Database does not exist for project %s, creating new database",
                    project.name
                )
                return self.create_database(
                    str(source_path),
                    str(db_path),
                    project.language,
                    progress_callback=progress_callback,
                )
            
            # Database exists and force_recreate is False
            # Check if database needs finalization
            try:
                if self._is_database_finalized(db_path):
                    logger.info("Database already finalized, skipping finalize step: %s", db_path)
                else:
                    self._ensure_finalized(str(db_path), progress_callback)
            except DatabaseError as e:
                logger.warning(
                    "Database finalization check failed for %s: %s. Will recreate.",
                    project.name, e
                )
                return self.create_database(
                    str(source_path),
                    str(db_path),
                    project.language,
                    progress_callback=progress_callback,
                )
            
            # Check database age
            db_age = self._get_database_age(db_path)
            if db_age:
                logger.info(
                    "Database for project %s exists (age: %d days), reusing without recreation",
                    project.name, db_age.days
                )
                if db_age > timedelta(days=7):
                    logger.warning(
                        "Database for project %s is %d days old, consider recreation for accuracy",
                        project.name, db_age.days
                    )
            else:
                logger.info(
                    "Database for project %s exists, reusing without recreation",
                    project.name
                )
            
            # Report progress immediately since we're reusing the database
            if progress_callback:
                progress_callback(100)
            
            # Return existing database path without update
            # (update can be slow and is often unnecessary)
            logger.info("Reusing existing database at %s", db_path)
            return str(db_path)
        
        except DatabaseError:
            # Re-raise DatabaseError as-is
            raise
        except Exception as e:
            logger.error(
                "Unexpected error managing database for project %s: %s",
                project.name, e, exc_info=True
            )
            raise DatabaseError(
                "Failed to manage database",
                details=str(e),
                category="database_error",
            )
    
    def create_database(
        self,
        source_path: str,
        database_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Create a new CodeQL database.
        
        Requirements: 2.2, 2.4, 2.6, 2.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
        
        Args:
            source_path: Path to source code directory
            database_path: Path where database will be created
            language: Programming language (auto-detected if None)
            progress_callback: Optional callback for progress updates (0-100)
        
        Returns:
            Path to the created database
        
        Raises:
            DatabaseError: If database creation fails
        """
        import time
        
        # Start timer
        start_time = time.time()
        
        try:
            # Validate paths
            source_path_obj = self._validate_path(source_path, "source")
            database_path_obj = self._validate_path(database_path, "database")
            
            # Validate source path exists
            if not source_path_obj.exists():
                logger.error("Source path does not exist: %s", source_path)
                raise DatabaseError(
                    "Source path does not exist",
                    details=f"Path: {source_path}",
                    category="invalid_path",
                )
            
            # Auto-detect language if not provided
            if not language:
                language = self.detect_language(str(source_path_obj))
                logger.info("Auto-detected language: %s", language)
            
            # Ensure parent directory exists
            database_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            # Remove existing database if present (with retry logic)
            if database_path_obj.exists():
                logger.info("Removing existing database at %s", database_path_obj)
                self._remove_directory_with_retries(database_path_obj)
                
                # Verify removal
                if database_path_obj.exists():
                    raise DatabaseError(
                        "Database directory still exists after removal",
                        details=f"Path: {database_path_obj}",
                        category="filesystem_error"
                    )
            
            # Build command with optimizations
            # For Java projects, we'll use --build-mode=none to avoid automatic compilation
            # which can hang if Maven/Gradle is not properly configured
            source_root = self._resolve_effective_source_root(language, source_path_obj)
            cmd = [
                self.codeql_path,
                "database",
                "create",
                str(database_path_obj),
                f"--language={language}",
                f"--source-root={source_root}",
                f"--threads={self.db_threads}",
                f"--ram={self.db_ram}",
                "--overwrite",  # Force overwrite if directory exists
            ]
            
            # For Java, add build-mode=none to skip automatic compilation
            # This is faster and more reliable for analysis-only purposes
            if language.lower() == "java":
                cmd.append("--build-mode=none")
                logger.info("Using --build-mode=none for Java (no compilation required)")
            
            logger.info("⏱️  Iniciando criação do banco de dados CodeQL...")
            logger.info("Creating CodeQL database: %s", " ".join(cmd))
            
            # Execute with progress tracking
            self._execute_with_progress(
                cmd,
                progress_callback=progress_callback,
                operation="Database creation",
            )
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            
            logger.info("✅ Database created successfully at %s", database_path_obj)
            logger.info("⏱️  Tempo de criação: %d minutos e %d segundos (%.1f segundos total)", 
                       minutes, seconds, elapsed_time)
            
            return str(database_path_obj)
        
        except subprocess.CalledProcessError as e:
            logger.error(
                "Database creation failed with exit code %d: %s",
                e.returncode, e.stderr, exc_info=True
            )
            raise DatabaseError(
                "Database creation failed",
                details=f"CodeQL CLI returned exit code {e.returncode}",
                stderr=e.stderr if hasattr(e, 'stderr') else None,
                category="database_creation_failed",
            )
        
        except subprocess.TimeoutExpired:
            logger.error(
                "Database creation timed out after %d seconds", self.timeout
            )
            raise DatabaseError(
                "Database creation timed out",
                details=f"Operation exceeded timeout of {self.timeout} seconds. "
                        "Try with a smaller project or increase CODEQL_TIMEOUT.",
                category="timeout",
            )
        
        except FileNotFoundError:
            logger.error("CodeQL CLI not found at: %s", self.codeql_path)
            raise DatabaseError(
                "CodeQL CLI not found",
                details=f"Expected location: {self.codeql_path}. "
                        "Install from https://github.com/github/codeql-cli-binaries",
                category="codeql_not_found",
            )
        
        except DatabaseError:
            # Re-raise DatabaseError as-is
            raise
        
        except Exception as e:
            logger.error(
                "Unexpected error creating database: %s",
                e, exc_info=True
            )
            raise DatabaseError(
                "Failed to create database",
                details=str(e),
                category="database_error",
            )
    
    def update_database(
        self,
        database_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Update an existing CodeQL database.
        
        Requirements: 2.3, 2.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
        
        Args:
            database_path: Path to existing database
            progress_callback: Optional callback for progress updates (0-100)
        
        Returns:
            Path to the updated database
        
        Raises:
            DatabaseError: If database update fails
        """
        try:
            # Validate path
            database_path_obj = self._validate_path(database_path, "database")
            
            # Validate database exists
            if not database_path_obj.exists():
                logger.error("Database does not exist: %s", database_path)
                raise DatabaseError(
                    "Database does not exist",
                    details=f"Path: {database_path}",
                    category="invalid_path",
                )
            
            if not (database_path_obj / "codeql-database.yml").exists():
                logger.error("Invalid database directory: %s", database_path)
                raise DatabaseError(
                    "Invalid database directory",
                    details="Missing codeql-database.yml file",
                    category="invalid_database",
                )
            
            # Build command
            cmd = [
                self.codeql_path,
                "database",
                "upgrade",
                str(database_path_obj),
            ]
            
            logger.info("Updating CodeQL database: %s", " ".join(cmd))
            
            # Execute with progress tracking
            self._execute_with_progress(
                cmd,
                progress_callback=progress_callback,
                operation="Database update",
            )
            
            logger.info("Database updated successfully at %s", database_path_obj)
            return str(database_path_obj)
        
        except subprocess.CalledProcessError as e:
            logger.error(
                "Database update failed with exit code %d: %s",
                e.returncode, e.stderr, exc_info=True
            )
            raise DatabaseError(
                "Database update failed",
                details=f"CodeQL CLI returned exit code {e.returncode}",
                stderr=e.stderr if hasattr(e, 'stderr') else None,
                category="database_update_failed",
            )
        
        except FileNotFoundError:
            logger.error("CodeQL CLI not found at: %s", self.codeql_path)
            raise DatabaseError(
                "CodeQL CLI not found",
                details=f"Expected location: {self.codeql_path}",
                category="codeql_not_found",
            )
        
        except DatabaseError:
            # Re-raise DatabaseError as-is
            raise
        
        except Exception as e:
            logger.error(
                "Unexpected error updating database: %s",
                e, exc_info=True
            )
            raise DatabaseError(
                "Failed to update database",
                details=str(e),
                category="database_error",
            )
    
    def detect_language(self, source_path: str) -> str:
        """
        Auto-detect programming language of a project.
        
        Requirements: 2.4, 8.1, 8.2, 8.3
        
        Args:
            source_path: Path to source code directory
        
        Returns:
            Detected language name (e.g., "java", "javascript", "python")
        
        Raises:
            DatabaseError: If language cannot be detected
        """
        try:
            # Validate path
            source_path_obj = self._validate_path(source_path, "source")
            
            if not source_path_obj.exists():
                logger.error("Source path does not exist: %s", source_path)
                raise DatabaseError(
                    "Source path does not exist",
                    details=f"Path: {source_path}",
                    category="invalid_path",
                )
            
            # Count files matching each language pattern
            language_scores: dict[str, int] = {}
            
            for language, patterns in self.LANGUAGE_PATTERNS.items():
                score = 0
                
                for pattern in patterns:
                    if pattern.startswith("."):
                        # File extension pattern
                        count = len(list(source_path_obj.rglob(f"*{pattern}")))
                        score += count
                    else:
                        # Specific file pattern
                        count = len(list(source_path_obj.rglob(pattern)))
                        score += count * 10  # Weight specific files higher
                
                if score > 0:
                    language_scores[language] = score
            
            if not language_scores:
                logger.error(
                    "Could not detect language for project at %s. No recognized source files found.",
                    source_path
                )
                raise DatabaseError(
                    "Could not detect language",
                    details=f"No recognized source files found in {source_path}. "
                            f"Supported languages: {', '.join(self.LANGUAGE_PATTERNS.keys())}",
                    category="language_detection_failed",
                )
            
            # Return language with highest score
            detected_language = max(language_scores, key=language_scores.get)
            logger.info(
                "Language detection scores: %s (selected: %s)",
                language_scores, detected_language
            )
            
            return detected_language
        
        except DatabaseError:
            # Re-raise DatabaseError as-is
            raise
        
        except Exception as e:
            logger.error(
                "Unexpected error detecting language for %s: %s",
                source_path, e, exc_info=True
            )
            raise DatabaseError(
                "Failed to detect language",
                details=str(e),
                category="language_detection_failed",
            )
    
    # ──────────────────────────────────────────────
    # Private Helpers
    # ──────────────────────────────────────────────
    
    def _ensure_finalized(
        self,
        database_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """
        Ensure a database is finalized and ready for analysis.
        
        Uses a short timeout (FINALIZE_TIMEOUT) — if finalization fails or hangs,
        we skip gracefully and let the caller decide whether to recreate.
        
        Args:
            database_path: Path to database directory
            progress_callback: Optional callback for progress updates
        
        Raises:
            DatabaseError: If finalization fails
        """
        try:
            database_path_obj = Path(database_path)
            
            # Try to finalize the database
            # If it's already finalized, this will be a no-op
            cmd_finalize = [
                self.codeql_path,
                "database",
                "finalize",
                str(database_path_obj),
            ]
            
            logger.info("Ensuring database is finalized: %s", " ".join(cmd_finalize))
            
            previous_timeout = self.timeout
            self.timeout = self.FINALIZE_TIMEOUT
            try:
                self._execute_with_progress(
                    cmd_finalize,
                    progress_callback=progress_callback,
                    operation="Database finalization",
                )
            finally:
                self.timeout = previous_timeout

            logger.info("Database finalized successfully at %s", database_path)
        
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            # If already finalized, that's okay
            if "already finalized" in stderr.lower() or "already been finalized" in stderr.lower():
                logger.info("Database at %s is already finalized", database_path)
                return

            logger.error("Database finalization failed: %s", stderr)
            raise DatabaseError(
                "Database finalization failed",
                details=stderr or f"CodeQL exited with code {e.returncode}",
                category="database_error",
            )
        
        except subprocess.TimeoutExpired:
            logger.warning(
                "Database finalization timed out after %ds, will recreate",
                self.FINALIZE_TIMEOUT,
            )
            raise DatabaseError(
                "Database finalization timed out",
                details=f"Operation took longer than {self.FINALIZE_TIMEOUT} seconds",
                category="database_error",
            )
        
        except FileNotFoundError:
            logger.error("CodeQL CLI not found at: %s", self.codeql_path)
            raise DatabaseError(
                "CodeQL CLI not found",
                details=f"Expected location: {self.codeql_path}",
                category="codeql_not_found",
            )
        
        except DatabaseError:
            raise
        
        except Exception as e:
            logger.error("Unexpected error checking database finalization: %s", e, exc_info=True)
            raise DatabaseError(
                "Failed to check database finalization",
                details=str(e),
                category="database_error",
            )
    
    def _execute_with_progress(
        self,
        cmd: list[str],
        progress_callback: Optional[Callable[[int], None]],
        operation: str,
    ) -> None:
        """
        Execute a command with progress reporting and timeout.
        
        Requirements: 2.7
        
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
        
        # Execute command
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
        
        def _read_stderr():
            """Read stderr in a background thread to avoid blocking on timeout."""
            nonlocal progress
            try:
                for line in process.stderr:
                    # Keep only recent stderr to bound memory and string-join overhead.
                    if len(line) > 4000:
                        line = line[:4000] + " ... [truncated]\n"
                    stderr_lines.append(line)
                    
                    # Estimate progress based on CodeQL output patterns
                    if "Initializing" in line or "Preparing" in line:
                        progress = min(progress + 3, 15)
                    elif "Extracting" in line or "Building" in line:
                        progress = min(progress + 5, 70)
                    elif "Running" in line or "Evaluating" in line:
                        progress = min(progress + 3, 80)
                    elif "Finalizing" in line or "Writing" in line:
                        progress = 90
                    
                    if progress_callback:
                        progress_callback(progress)
                    
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("%s: %s", operation, line.strip())
            except (ValueError, OSError):
                # Process was killed / stderr closed
                pass
        
        # Start stderr reader in background thread
        reader_thread = threading.Thread(target=_read_stderr, daemon=True)
        reader_thread.start()
        
        try:
            # Wait for process with timeout
            # Also send time-based progress updates while waiting
            while True:
                try:
                    process.wait(timeout=5)  # Check every 5 seconds
                    break  # Process finished
                except subprocess.TimeoutExpired:
                    elapsed = time.time() - start_time
                    if elapsed > self.timeout:
                        # Kill the process
                        logger.error(
                            "%s exceeded timeout of %ds (elapsed: %.0fs)",
                            operation, self.timeout, elapsed
                        )
                        self._terminate_process_tree(process, operation)
                        raise subprocess.TimeoutExpired(
                            cmd, self.timeout,
                            output="".join(stderr_lines)
                        )
                    
                    # Time-based progress fallback (advance slowly if no output)
                    # Maps elapsed time to 0-85% range over the timeout period
                    time_progress = min(int((elapsed / self.timeout) * 85), 85)
                    effective_progress = max(progress, time_progress)
                    if progress_callback and effective_progress > progress:
                        progress = effective_progress
                        progress_callback(progress)
            
            # Wait for reader thread to finish
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
        """
        Terminate a process and its children.

        On Windows, CodeQL can spawn child processes that keep file handles open,
        so taskkill /T helps prevent locked files during cleanup.
        """
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

    def _resolve_effective_source_root(self, language: str, source_path: Path) -> Path:
        """
        Resolve an optimized source root for faster database creation.

        For Java projects, using `src` as source-root avoids scanning heavy build
        directories (like `target`) during finalize/indexing.
        """
        language_name = (language or "").lower()
        if language_name != "java":
            return source_path

        java_src = source_path / "src"
        if java_src.exists() and java_src.is_dir():
            logger.info(
                "Using optimized Java source-root: %s (instead of %s)",
                java_src,
                source_path,
            )
            return java_src

        return source_path

    def _handle_remove_readonly(self, func, path, exc) -> None:
        """Handle readonly files during recursive deletion."""
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
        func(path)

    def _remove_directory_with_retries(self, directory: Path) -> None:
        """Remove directory with retries for transient Windows file locks."""
        import shutil

        max_attempts = 8
        for attempt in range(1, max_attempts + 1):
            try:
                shutil.rmtree(directory, onerror=self._handle_remove_readonly)
                logger.info("Successfully removed existing database")
                return
            except FileNotFoundError:
                return
            except Exception as e:
                if attempt == max_attempts:
                    logger.error(
                        "Failed to remove database after %d attempts: %s",
                        max_attempts,
                        e,
                    )
                    raise DatabaseError(
                        "Cannot remove existing database directory",
                        details=f"Path: {directory}, Error: {e}",
                        category="filesystem_error",
                    )

                wait_seconds = min(attempt, 4)
                logger.warning(
                    "Failed to remove database (attempt %d/%d): %s. Retrying in %ss...",
                    attempt,
                    max_attempts,
                    e,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
    
    def _get_database_age(self, database_path: Path) -> Optional[timedelta]:
        """
        Get the age of a database based on modification time.
        
        Args:
            database_path: Path to database directory
        
        Returns:
            Age as timedelta, or None if cannot determine
        """
        try:
            db_yml = database_path / "codeql-database.yml"
            if db_yml.exists():
                mtime = datetime.fromtimestamp(db_yml.stat().st_mtime)
                age = datetime.now() - mtime
                return age
        except Exception as e:
            logger.warning("Could not determine database age: %s", e)
        
        return None

    def _is_database_finalized(self, database_path: Path) -> bool:
        """
        Fast check to detect whether a database is already finalized.
        """
        db_yml = database_path / "codeql-database.yml"
        if not db_yml.exists():
            return False

        try:
            # Avoid loading YAML parser dependency; simple key lookup is enough.
            with open(db_yml, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().lower() == "finalised: true":
                        return True
        except Exception as e:
            logger.debug("Could not check finalization flag for %s: %s", database_path, e)

        return False


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class DatabaseError(Exception):
    """
    Raised when database operations fail.
    
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
        category: str = "database_error",
    ):
        """
        Args:
            message: User-friendly error message
            details: Additional technical details
            stderr: CodeQL CLI stderr output
            category: Error category (codeql_not_found, invalid_path, database_creation_failed, etc.)
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

