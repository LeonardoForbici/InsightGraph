"""
CodeQL Bridge — Integrates CodeQL SARIF analysis results into InsightGraph Neo4j.

Provides industrial-grade taint tracking and vulnerability detection by:
1. Running CodeQL database analysis
2. Parsing SARIF output
3. Mapping findings to existing Neo4j entities
4. Creating SecurityIssue nodes and HAS_VULNERABILITY relationships
5. Marking tainted paths with is_tainted property

Requirements: CodeQL CLI installed and in PATH
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("insightgraph")


@dataclass
class CodeFlowStep:
    """Represents a single step in a taint flow path."""
    file_path: str
    start_line: int
    end_line: int
    message: str


@dataclass
class SecurityIssue:
    """Represents a CodeQL security finding."""
    rule_id: str
    severity: str
    message: str
    file_path: str
    start_line: int
    end_line: int
    code_flows: list[CodeFlowStep]


class CodeQLBridge:
    """
    Bridge between CodeQL SARIF analysis and InsightGraph Neo4j.
    
    Usage:
        bridge = CodeQLBridge(neo4j_service, project_root)
        bridge.run_analysis(database_path, output_path)
        summary = bridge.ingest_sarif(output_path)
    """

    def __init__(self, neo4j_service, project_root: Optional[str] = None):
        """
        Args:
            neo4j_service: Neo4jService instance for graph operations
            project_root: Root directory of the project being analyzed (optional, can be set per-analysis)
        """
        self._neo4j = neo4j_service
        self._project_root = None
        
        if project_root:
            try:
                # Validate project root path
                self._project_root = self._validate_path(project_root, "project_root")
                logger.info("CodeQLBridge initialized with project_root=%s", project_root)
            except ValueError as e:
                logger.error("Failed to validate project_root: %s", e, exc_info=True)
                raise
        else:
            logger.info("CodeQLBridge initialized without project_root (will be set per-analysis)")
    
    def set_project_root(self, project_root: str):
        """
        Set or update the project root directory.
        
        Args:
            project_root: Root directory of the project being analyzed
        
        Raises:
            ValueError: If path is invalid
        """
        self._project_root = self._validate_path(project_root, "project_root")
        logger.debug("Project root set to: %s", project_root)
    
    # ──────────────────────────────────────────────
    # Path Validation
    # ──────────────────────────────────────────────
    
    def _validate_path(self, path: str, path_type: str = "path") -> Path:
        """
        Validate and sanitize file paths to prevent directory traversal.
        
        Requirements: 8.3, 8.4
        
        Args:
            path: Path to validate
            path_type: Type of path for error messages (e.g., "sarif", "project")
        
        Returns:
            Validated Path object
        
        Raises:
            ValueError: If path contains directory traversal or is invalid
        """
        try:
            path_obj = Path(path).resolve()
            
            # Check for directory traversal attempts
            if ".." in str(path):
                logger.error(
                    "Directory traversal attempt detected in %s path: %s",
                    path_type, path
                )
                raise ValueError(
                    f"Invalid {path_type} path: directory traversal not allowed"
                )
            
            return path_obj
        
        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Path validation failed for %s path '%s': %s",
                path_type, path, e
            )
            raise ValueError(f"Invalid {path_type} path: {str(e)}")

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def run_analysis(
        self,
        database_path: str,
        output_path: str,
        suite: str = "security-extended",
        timeout: int = 600,
    ) -> dict:
        """
        Execute CodeQL database analysis and export SARIF results.
        
        Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6

        Args:
            database_path: Path to CodeQL database directory
            output_path: Path where SARIF JSON will be written
            suite: CodeQL query suite to run (default: security-extended)
            timeout: Command timeout in seconds

        Returns:
            Dict with success status or error information
        """
        try:
            # Validate paths
            db_path = self._validate_path(database_path, "database")
            out_path = self._validate_path(output_path, "output")
            
            # Validate database exists
            if not db_path.exists():
                logger.error("Database does not exist: %s", database_path)
                return {
                    "success": False,
                    "error": "Database does not exist",
                    "details": f"Path: {database_path}",
                    "category": "invalid_database",
                    "stage": "analysis"
                }
            
            if not (db_path / "codeql-database.yml").exists():
                logger.error("Invalid database directory: %s", database_path)
                return {
                    "success": False,
                    "error": "Invalid database directory",
                    "details": "Missing codeql-database.yml file",
                    "category": "invalid_database",
                    "stage": "analysis"
                }
            
            cmd = [
                "codeql",
                "database",
                "analyze",
                str(db_path),
                suite,
                "--format=sarif-latest",
                f"--output={out_path}",
                "--threads=0",  # Use all available cores
            ]

            logger.info("Running CodeQL analysis: %s", " ".join(cmd))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                logger.error(
                    "CodeQL analysis failed with exit code %d: %s",
                    result.returncode, result.stderr
                )
                return {
                    "success": False,
                    "error": "CodeQL analysis failed",
                    "details": f"CodeQL CLI returned exit code {result.returncode}",
                    "stderr": self._sanitize_stderr(result.stderr),
                    "category": "analysis_failed",
                    "stage": "analysis"
                }

            logger.info("CodeQL analysis completed successfully")
            return {"success": True}

        except subprocess.TimeoutExpired:
            logger.error(
                "CodeQL analysis timed out after %d seconds",
                timeout, exc_info=True
            )
            return {
                "success": False,
                "error": "Analysis timeout",
                "details": f"Analysis exceeded timeout of {timeout} seconds",
                "category": "timeout",
                "stage": "analysis"
            }
        
        except FileNotFoundError:
            logger.error(
                "CodeQL CLI not found. Install from https://github.com/github/codeql-cli-binaries",
                exc_info=True
            )
            return {
                "success": False,
                "error": "CodeQL CLI not found",
                "details": "Install from https://github.com/github/codeql-cli-binaries",
                "category": "codeql_not_found",
                "stage": "analysis"
            }
        
        except ValueError as e:
            logger.error("Path validation error: %s", e, exc_info=True)
            return {
                "success": False,
                "error": "Invalid path",
                "details": str(e),
                "category": "invalid_path",
                "stage": "analysis"
            }
        
        except Exception as e:
            logger.error("CodeQL analysis error: %s", e, exc_info=True)
            return {
                "success": False,
                "error": "Analysis failed",
                "details": str(e),
                "category": "analysis_error",
                "stage": "analysis"
            }

    def ingest_sarif(self, sarif_path: str, progress_callback=None) -> dict:
        """
        Parse SARIF file and ingest findings into Neo4j.
        
        Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6

        Args:
            sarif_path: Path to SARIF JSON file
            progress_callback: Optional callback function(progress: int) for reporting progress (0-100)

        Returns:
            Summary dict with counts of ingested issues and vulnerabilities by severity
        """
        try:
            # Validate path
            sarif_path_obj = self._validate_path(sarif_path, "sarif")
            
            # Report initial progress
            if progress_callback:
                progress_callback(0)

            # Check if file exists
            if not sarif_path_obj.exists():
                logger.error("SARIF file not found: %s", sarif_path)
                return {
                    "error": "SARIF file not found",
                    "details": f"Path: {sarif_path}",
                    "category": "invalid_path",
                    "stage": "ingestion",
                    "total_issues": 0,
                    "ingested": 0,
                    "skipped": 0
                }

            with open(sarif_path_obj, "r", encoding="utf-8") as f:
                sarif_data = json.load(f)

            if progress_callback:
                progress_callback(10)

            issues = self._parse_sarif(sarif_data)
            logger.info("Parsed %d security issues from SARIF", len(issues))

            if progress_callback:
                progress_callback(20)

            summary = {
                "total_issues": len(issues),
                "ingested": 0,
                "skipped": 0,
                "tainted_paths": 0,
                "vulnerabilities_by_severity": {
                    "error": 0,
                    "warning": 0,
                    "note": 0,
                },
            }

            # Check Neo4j connection
            if not self._neo4j.is_connected:
                logger.error("Neo4j not connected, cannot ingest SARIF")
                summary["error"] = "Neo4j disconnected"
                summary["details"] = "Database connection is not available"
                summary["category"] = "neo4j_error"
                summary["stage"] = "ingestion"
                return summary

            # Process issues with progress reporting
            total = len(issues)
            for idx, issue in enumerate(issues):
                try:
                    if self._ingest_issue(issue):
                        summary["ingested"] += 1
                        # Count by severity
                        severity = issue.severity.lower()
                        if severity in summary["vulnerabilities_by_severity"]:
                            summary["vulnerabilities_by_severity"][severity] += 1
                        else:
                            # Default to warning for unknown severities
                            summary["vulnerabilities_by_severity"]["warning"] += 1
                        
                        if issue.code_flows:
                            summary["tainted_paths"] += 1
                    else:
                        summary["skipped"] += 1
                except Exception as e:
                    logger.error(
                        "Failed to ingest issue %s: %s",
                        issue.rule_id, e, exc_info=True
                    )
                    summary["skipped"] += 1

                # Report progress (20% to 100%)
                if progress_callback and total > 0:
                    progress = 20 + int((idx + 1) / total * 80)
                    progress_callback(progress)

            logger.info("Ingestion summary: %s", summary)
            return summary

        except FileNotFoundError:
            logger.error("SARIF file not found: %s", sarif_path, exc_info=True)
            return {
                "error": "SARIF file not found",
                "details": f"Path: {sarif_path}",
                "category": "invalid_path",
                "stage": "ingestion",
                "total_issues": 0,
                "ingested": 0,
                "skipped": 0
            }
        
        except json.JSONDecodeError as e:
            logger.error("Invalid SARIF JSON: %s", e, exc_info=True)
            return {
                "error": "Invalid SARIF format",
                "details": f"JSON parsing error: {str(e)}",
                "category": "invalid_sarif",
                "stage": "ingestion",
                "total_issues": 0,
                "ingested": 0,
                "skipped": 0
            }
        
        except ValueError as e:
            logger.error("Path validation error: %s", e, exc_info=True)
            return {
                "error": "Invalid path",
                "details": str(e),
                "category": "invalid_path",
                "stage": "ingestion",
                "total_issues": 0,
                "ingested": 0,
                "skipped": 0
            }
        
        except Exception as e:
            logger.error("SARIF ingestion error: %s", e, exc_info=True)
            return {
                "error": "SARIF ingestion failed",
                "details": str(e),
                "category": "ingestion_error",
                "stage": "ingestion",
                "total_issues": 0,
                "ingested": 0,
                "skipped": 0
            }

    # ──────────────────────────────────────────────
    # SARIF Parsing
    # ──────────────────────────────────────────────

    def _parse_sarif(self, sarif_data: dict) -> list[SecurityIssue]:
        """Extract SecurityIssue objects from SARIF JSON."""
        issues: list[SecurityIssue] = []

        for run in sarif_data.get("runs", []):
            tool_name = run.get("tool", {}).get("driver", {}).get("name", "unknown")
            logger.info("Processing SARIF run from tool: %s", tool_name)

            for result in run.get("results", []):
                issue = self._parse_result(result)
                if issue:
                    issues.append(issue)

        return issues

    def _parse_result(self, result: dict) -> Optional[SecurityIssue]:
        """Parse a single SARIF result into a SecurityIssue."""
        try:
            rule_id = result.get("ruleId", "unknown")
            severity = result.get("level", "warning")
            message = result.get("message", {}).get("text", "No description")

            # Extract primary location
            locations = result.get("locations", [])
            if not locations:
                logger.warning("Result has no locations, skipping: %s", rule_id)
                return None

            primary_loc = locations[0].get("physicalLocation", {})
            artifact_loc = primary_loc.get("artifactLocation", {})
            region = primary_loc.get("region", {})

            file_path = artifact_loc.get("uri", "")
            start_line = region.get("startLine", 0)
            end_line = region.get("endLine", start_line)

            if not file_path or start_line == 0:
                logger.warning("Invalid location for rule %s, skipping", rule_id)
                return None

            # Extract code flows (taint paths)
            code_flows = self._parse_code_flows(result.get("codeFlows", []))

            return SecurityIssue(
                rule_id=rule_id,
                severity=severity,
                message=message,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                code_flows=code_flows,
            )

        except Exception as e:
            logger.warning("Failed to parse SARIF result: %s", e)
            return None

    def _parse_code_flows(self, code_flows: list) -> list[CodeFlowStep]:
        """Extract taint flow steps from SARIF codeFlows."""
        steps: list[CodeFlowStep] = []

        for flow in code_flows:
            for thread_flow in flow.get("threadFlows", []):
                for location in thread_flow.get("locations", []):
                    step = self._parse_flow_location(location)
                    if step:
                        steps.append(step)

        return steps

    def _parse_flow_location(self, location: dict) -> Optional[CodeFlowStep]:
        """Parse a single flow location into a CodeFlowStep."""
        try:
            phys_loc = location.get("location", {}).get("physicalLocation", {})
            artifact = phys_loc.get("artifactLocation", {})
            region = phys_loc.get("region", {})
            message = location.get("location", {}).get("message", {}).get("text", "")

            file_path = artifact.get("uri", "")
            start_line = region.get("startLine", 0)
            end_line = region.get("endLine", start_line)

            if not file_path or start_line == 0:
                return None

            return CodeFlowStep(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                message=message,
            )

        except Exception:
            return None

    # ──────────────────────────────────────────────
    # Neo4j Ingestion
    # ──────────────────────────────────────────────

    def _ingest_issue(self, issue: SecurityIssue) -> bool:
        """
        Ingest a SecurityIssue into Neo4j.

        Creates:
        - SecurityIssue node
        - HAS_VULNERABILITY relationship to affected Entity
        - Marks tainted paths with is_tainted property

        Returns:
            True if ingestion succeeded, False otherwise
        """
        if not self._neo4j.is_connected:
            logger.warning("Neo4j not connected, skipping ingestion")
            return False

        try:
            # Normalize file path relative to project root
            rel_path = self._normalize_path(issue.file_path)

            # Find affected entity node by file and line range
            entity_key = self._find_entity_by_location(rel_path, issue.start_line, issue.end_line)

            if not entity_key:
                logger.debug(
                    "No entity found for %s:%d-%d (rule: %s), creating orphan SecurityIssue",
                    rel_path, issue.start_line, issue.end_line, issue.rule_id
                )

            # Create SecurityIssue node with enhanced error handling
            issue_key = f"security:{issue.rule_id}:{rel_path}:{issue.start_line}"
            
            try:
                self._neo4j.graph.run("""
                    MERGE (s:SecurityIssue {namespace_key: $key})
                    SET s.rule_id = $rule_id,
                        s.severity = $severity,
                        s.message = $message,
                        s.file = $file,
                        s.start_line = $start_line,
                        s.end_line = $end_line,
                        s.has_taint_flow = $has_flow
                """, key=issue_key, rule_id=issue.rule_id, severity=issue.severity,
                    message=issue.message, file=rel_path, start_line=issue.start_line,
                    end_line=issue.end_line, has_flow=len(issue.code_flows) > 0)
            except Exception as e:
                logger.error(
                    "Failed to create SecurityIssue node for %s: %s",
                    issue_key, e, exc_info=True
                )
                return False

            # Link to affected entity if found
            if entity_key:
                try:
                    self._neo4j.graph.run("""
                        MATCH (e:Entity {namespace_key: $entity_key})
                        MATCH (s:SecurityIssue {namespace_key: $issue_key})
                        MERGE (e)-[:HAS_VULNERABILITY]->(s)
                    """, entity_key=entity_key, issue_key=issue_key)
                    logger.debug(
                        "Linked vulnerability %s to entity %s",
                        issue.rule_id, entity_key
                    )
                except Exception as e:
                    logger.error(
                        "Failed to create HAS_VULNERABILITY relationship from %s to %s: %s",
                        entity_key, issue_key, e, exc_info=True
                    )
                    # Continue even if relationship creation fails

            # Mark tainted paths
            if issue.code_flows:
                try:
                    self._mark_tainted_paths(issue.code_flows)
                except Exception as e:
                    logger.error(
                        "Failed to mark tainted paths for %s: %s",
                        issue.rule_id, e, exc_info=True
                    )
                    # Continue even if taint marking fails

            return True

        except Exception as e:
            logger.error(
                "Failed to ingest issue %s at %s:%d-%d: %s",
                issue.rule_id, issue.file_path, issue.start_line, issue.end_line,
                e, exc_info=True
            )
            return False

    def _find_entity_by_location(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> Optional[str]:
        """
        Find Entity node that contains the given file location.

        Enhanced to handle multiple entity types:
        - Methods/Functions (with line ranges)
        - Classes (with line ranges)
        - Modules/Files (file-level match)
        - Interfaces, Enums, and other types

        Matches if:
        - Entity.file == file_path
        - Issue line range overlaps with Entity line range (if available)

        Returns:
            namespace_key of matching entity, or None
        """
        try:
            # Strategy 1: Find smallest entity containing the line range
            # This prioritizes methods over classes, classes over modules
            result = self._neo4j.graph.run("""
                MATCH (e:Entity)
                WHERE e.file = $file
                  AND e.start_line IS NOT NULL
                  AND e.end_line IS NOT NULL
                  AND $start_line >= e.start_line
                  AND $end_line <= e.end_line
                RETURN e.namespace_key AS key, e.type AS type, 
                       (e.end_line - e.start_line) AS size
                ORDER BY size ASC, e.type DESC
                LIMIT 1
            """, file=file_path, start_line=start_line, end_line=end_line).data()

            if result:
                logger.debug(
                    "Found entity %s (type: %s) for %s:%d-%d",
                    result[0]["key"], result[0].get("type", "unknown"),
                    file_path, start_line, end_line
                )
                return result[0]["key"]

            # Strategy 2: Find entity by file with line range, even if partial overlap
            # Useful for vulnerabilities at class boundaries
            result = self._neo4j.graph.run("""
                MATCH (e:Entity)
                WHERE e.file = $file
                  AND e.start_line IS NOT NULL
                  AND e.end_line IS NOT NULL
                  AND (
                    ($start_line >= e.start_line AND $start_line <= e.end_line) OR
                    ($end_line >= e.start_line AND $end_line <= e.end_line) OR
                    ($start_line <= e.start_line AND $end_line >= e.end_line)
                  )
                RETURN e.namespace_key AS key, e.type AS type,
                       (e.end_line - e.start_line) AS size
                ORDER BY size ASC, e.type DESC
                LIMIT 1
            """, file=file_path, start_line=start_line, end_line=end_line).data()

            if result:
                logger.debug(
                    "Found entity %s (type: %s) with partial overlap for %s:%d-%d",
                    result[0]["key"], result[0].get("type", "unknown"),
                    file_path, start_line, end_line
                )
                return result[0]["key"]

            # Strategy 3: Fallback to file-level match (class, module, interface, etc.)
            # Prioritize classes over modules
            result = self._neo4j.graph.run("""
                MATCH (e:Entity)
                WHERE e.file = $file
                RETURN e.namespace_key AS key, e.type AS type
                ORDER BY 
                    CASE e.type
                        WHEN 'class' THEN 1
                        WHEN 'interface' THEN 2
                        WHEN 'enum' THEN 3
                        WHEN 'module' THEN 4
                        ELSE 5
                    END
                LIMIT 1
            """, file=file_path).data()

            if result:
                logger.debug(
                    "Found file-level entity %s (type: %s) for %s",
                    result[0]["key"], result[0].get("type", "unknown"), file_path
                )
                return result[0]["key"]

            logger.debug("No entity found for %s:%d-%d", file_path, start_line, end_line)
            return None

        except Exception as e:
            logger.error(
                "Entity lookup failed for %s:%d-%d: %s",
                file_path, start_line, end_line, e, exc_info=True
            )
            return None

    def _mark_tainted_paths(self, flow_steps: list[CodeFlowStep]) -> None:
        """
        Mark relationships along a taint flow path with is_tainted property.

        For each consecutive pair of steps in the flow:
        - Find source and target entities
        - Mark any relationship between them as tainted
        """
        if len(flow_steps) < 2:
            logger.debug("Taint flow has fewer than 2 steps, skipping path marking")
            return

        try:
            marked_count = 0
            for i in range(len(flow_steps) - 1):
                source_step = flow_steps[i]
                target_step = flow_steps[i + 1]

                try:
                    source_path = self._normalize_path(source_step.file_path)
                    target_path = self._normalize_path(target_step.file_path)

                    source_key = self._find_entity_by_location(
                        source_path, source_step.start_line, source_step.end_line
                    )
                    target_key = self._find_entity_by_location(
                        target_path, target_step.start_line, target_step.end_line
                    )

                    if source_key and target_key:
                        # Mark any relationship between these entities as tainted
                        result = self._neo4j.graph.run("""
                            MATCH (a:Entity {namespace_key: $source})-[r]->(b:Entity {namespace_key: $target})
                            SET r.is_tainted = true,
                                r.taint_message = $message
                            RETURN count(r) as marked
                        """, source=source_key, target=target_key, message=target_step.message).data()

                        if result and result[0].get("marked", 0) > 0:
                            marked_count += result[0]["marked"]
                            logger.debug(
                                "Marked tainted path: %s -> %s (%s)",
                                source_key, target_key, target_step.message[:50]
                            )
                        else:
                            logger.debug(
                                "No relationship found between %s and %s for taint marking",
                                source_key, target_key
                            )
                    else:
                        logger.debug(
                            "Could not find entities for taint step %d: source=%s, target=%s",
                            i, source_key, target_key
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to mark taint step %d (%s:%d -> %s:%d): %s",
                        i, source_step.file_path, source_step.start_line,
                        target_step.file_path, target_step.start_line, e
                    )
                    # Continue processing remaining steps

            if marked_count > 0:
                logger.info("Marked %d tainted relationships in flow", marked_count)
            else:
                logger.debug("No relationships marked as tainted in this flow")

        except Exception as e:
            logger.error("Failed to mark tainted paths: %s", e, exc_info=True)

    def _normalize_path(self, file_path: str) -> str:
        """
        Normalize file path to be relative to project root.

        Handles:
        - Absolute paths
        - file:// URIs
        - Windows/Unix path separators
        - URL-encoded paths

        Returns:
            Normalized relative path with forward slashes
        """
        try:
            # Remove file:// prefix if present
            if file_path.startswith("file://"):
                file_path = file_path[7:]

            # Handle URL encoding (e.g., %20 for spaces)
            if "%" in file_path:
                from urllib.parse import unquote
                file_path = unquote(file_path)

            path = Path(file_path)

            # If absolute, make relative to project root
            if path.is_absolute():
                try:
                    path = path.relative_to(self._project_root)
                except ValueError:
                    # Path is outside project root, use as-is
                    logger.debug(
                        "Path %s is outside project root %s, using as-is",
                        file_path, self._project_root
                    )

            # Normalize separators to forward slash
            normalized = str(path).replace("\\", "/")
            
            # Remove leading ./ if present
            if normalized.startswith("./"):
                normalized = normalized[2:]
            
            return normalized

        except Exception as e:
            logger.warning("Failed to normalize path %s: %s, using as-is", file_path, e)
            # Fallback: just normalize separators
            return file_path.replace("\\", "/")
    
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


# ──────────────────────────────────────────────
# Convenience Functions
# ──────────────────────────────────────────────

def run_codeql_analysis(
    neo4j_service,
    project_root: str,
    database_path: str,
    output_path: str = "codeql-results.sarif",
) -> dict:
    """
    Convenience function to run CodeQL analysis and ingest results.

    Args:
        neo4j_service: Neo4jService instance
        project_root: Root directory of project
        database_path: Path to CodeQL database
        output_path: Where to write SARIF output

    Returns:
        Ingestion summary dict
    """
    try:
        bridge = CodeQLBridge(neo4j_service, project_root)

        analysis_result = bridge.run_analysis(database_path, output_path)
        
        if not analysis_result.get("success", False):
            return analysis_result

        return bridge.ingest_sarif(output_path)
    
    except Exception as e:
        logger.error("CodeQL analysis workflow failed: %s", e, exc_info=True)
        return {
            "error": "Analysis workflow failed",
            "details": str(e),
            "category": "workflow_error",
            "stage": "workflow"
        }
