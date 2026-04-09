"""
Git Service for temporal navigation and commit history analysis.

This module provides functionality to interact with Git repositories,
fetch commit history, parse metadata, and support timeline navigation.
"""

import subprocess
import logging
import tempfile
import shutil
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Literal
from pathlib import Path

logger = logging.getLogger(__name__)


def _remove_readonly(func, path, excinfo):
    """
    Error handler for Windows readonly files.
    Used with shutil.rmtree to force deletion of readonly files.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


@dataclass
class CommitStats:
    """Statistics for a commit."""
    additions: int
    deletions: int


@dataclass
class GitCommit:
    """Represents a Git commit with metadata."""
    hash: str
    author: str
    date: datetime
    message: str
    files_modified: List[str]
    stats: CommitStats


@dataclass
class CommitDiff:
    """Represents the diff between two commits."""
    added: List[str]      # Files added
    modified: List[str]   # Files modified
    removed: List[str]    # Files removed


class GitService:
    """
    Service for interacting with Git repositories.
    
    Provides methods to fetch commit history, parse metadata,
    and support temporal navigation through code evolution.
    
    Optimizations:
        - Lazy loading for commit history (pagination)
        - Shallow clones for faster checkout
        - Commit caching for recently visited commits
    """
    
    def __init__(self, repo_path: str = ".", repo_url: str = None):
        """
        Initialize GitService.
        
        Args:
            repo_path: Path to the Git repository (default: current directory)
            repo_url: Optional GitHub repository URL for remote repos
        """
        self.repo_path = Path(repo_path).resolve()
        self.repo_url = repo_url
        self._validate_git_repo()
        self._original_branch: Optional[str] = None
        self._temp_dir: Optional[Path] = None
        
        # Optimization: Commit cache
        self._commit_cache: dict[str, GitCommit] = {}
        self._commit_cache_max_size = 50
    
    def clone_remote_repo(self, repo_url: str, target_path: Path, use_shallow_clone: bool = True) -> None:
        """
        Clone a remote repository to a target path.
        
        Args:
            repo_url: GitHub repository URL
            target_path: Target directory for the clone
            use_shallow_clone: Use shallow clone for faster checkout (default: True)
        
        Raises:
            RuntimeError: If clone operation fails
        """
        try:
            clone_cmd = ["git", "clone"]
            
            if use_shallow_clone:
                clone_cmd.extend(["--depth", "1", "--single-branch"])
            
            clone_cmd.extend([repo_url, str(target_path)])
            
            result = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=True
            )
            logger.info(f"Successfully cloned {repo_url} to {target_path}")
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"Clone operation timed out for {repo_url}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to clone repository: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _validate_git_repo(self) -> None:
        """Validate that the path is a Git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Git repository validated at {self.repo_path}")
        except subprocess.CalledProcessError:
            raise ValueError(f"Not a Git repository: {self.repo_path}")
    
    def get_commit_history(
        self,
        max_commits: int = 100,
        branch: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> List[GitCommit]:
        """
        Fetch commit history from the Git repository.
        
        Optimizations:
            - Lazy loading with pagination
            - Commit caching for recently fetched commits
        
        Args:
            max_commits: Maximum number of commits to fetch (default: 100)
            branch: Branch name to fetch commits from (default: current branch)
            page: Page number for pagination (default: 1)
            page_size: Number of commits per page (default: 20)
        
        Returns:
            List of GitCommit objects in chronological order (oldest first)
        
        Raises:
            RuntimeError: If git command fails
        
        Requirements:
            - 15.3: Optimize with lazy loading and pagination
        """
        try:
            # Calculate skip and limit for pagination
            skip = (page - 1) * page_size
            limit = min(page_size, max_commits - skip)
            
            if limit <= 0:
                return []
            
            # Build git log command
            # Format: hash|author|date|message
            git_cmd = [
                "git", "log",
                f"--skip={skip}",
                f"-{limit}",
                "--pretty=format:%H|%an|%ai|%s",
                "--numstat"
            ]
            
            if branch:
                git_cmd.append(branch)
            
            # Execute git log
            result = subprocess.run(
                git_cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse output
            commits = self._parse_git_log(result.stdout)
            
            # Cache commits
            for commit in commits:
                if len(self._commit_cache) >= self._commit_cache_max_size:
                    # Remove oldest entry
                    self._commit_cache.pop(next(iter(self._commit_cache)))
                self._commit_cache[commit.hash] = commit
            
            # Return in chronological order (oldest first)
            commits.reverse()
            
            logger.info(f"Fetched {len(commits)} commits (page {page})")
            return commits
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to fetch commit history: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def get_cached_commit(self, commit_hash: str) -> Optional[GitCommit]:
        """
        Get commit from cache if available.
        
        Args:
            commit_hash: Commit hash to retrieve
        
        Returns:
            Cached commit or None
        """
        return self._commit_cache.get(commit_hash)
    
    def _parse_git_log(self, log_output: str) -> List[GitCommit]:
        """
        Parse git log output into GitCommit objects.
        
        Args:
            log_output: Raw output from git log command
        
        Returns:
            List of parsed GitCommit objects
        """
        commits = []
        lines = log_output.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Check if this is a commit header line
            if '|' in line:
                parts = line.split('|', 3)
                if len(parts) == 4:
                    commit_hash, author, date_str, message = parts
                    
                    # Parse date
                    try:
                        commit_date = datetime.fromisoformat(date_str.strip())
                    except ValueError:
                        logger.warning(f"Failed to parse date: {date_str}")
                        commit_date = datetime.now()
                    
                    # Parse file stats (numstat lines follow)
                    i += 1
                    files_modified = []
                    additions = 0
                    deletions = 0
                    
                    while i < len(lines) and lines[i].strip() and '|' not in lines[i]:
                        stat_line = lines[i].strip()
                        if stat_line:
                            parts = stat_line.split('\t')
                            if len(parts) >= 3:
                                add_str, del_str, filename = parts[0], parts[1], parts[2]
                                
                                # Handle binary files (marked with '-')
                                if add_str != '-':
                                    try:
                                        additions += int(add_str)
                                    except ValueError:
                                        pass
                                
                                if del_str != '-':
                                    try:
                                        deletions += int(del_str)
                                    except ValueError:
                                        pass
                                
                                files_modified.append(filename)
                        i += 1
                    
                    # Create GitCommit object
                    commit = GitCommit(
                        hash=commit_hash.strip(),
                        author=author.strip(),
                        date=commit_date,
                        message=message.strip(),
                        files_modified=files_modified,
                        stats=CommitStats(
                            additions=additions,
                            deletions=deletions
                        )
                    )
                    commits.append(commit)
                    continue
            
            i += 1
        
        return commits

    def _get_current_branch(self) -> str:
        """
        Get the current branch name.
        
        Returns:
            Current branch name
        
        Raises:
            RuntimeError: If unable to determine current branch
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            branch = result.stdout.strip()
            logger.info(f"Current branch: {branch}")
            return branch
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to get current branch: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _is_valid_commit(self, commit_hash: str) -> bool:
        """
        Validate that a commit hash exists in the repository.
        
        Args:
            commit_hash: Git commit hash to validate
        
        Returns:
            True if commit exists, False otherwise
        """
        try:
            subprocess.run(
                ["git", "cat-file", "-e", f"{commit_hash}^{{commit}}"],
                cwd=self.repo_path,
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def checkout_commit(self, commit_hash: str, use_shallow_clone: bool = True) -> Path:
        """
        Checkout a specific commit to a temporary directory.
        
        This method clones the repository to a temporary directory and checks out
        the specified commit, enabling temporal navigation without affecting the
        main repository.
        
        Optimizations:
            - Uses shallow clone (depth=1) for faster checkout
            - Caches recently visited commits
        
        Args:
            commit_hash: Git commit hash to checkout
            use_shallow_clone: Use shallow clone for faster checkout (default: True)
        
        Returns:
            Path to the temporary directory containing the checked out commit
        
        Raises:
            ValueError: If commit hash is invalid
            RuntimeError: If git operations fail
        
        Requirements:
            - 15.3: Make checkout of commit in temporary directory
            - 15.6: Save original branch for later restoration
            - 15.3: Optimize with shallow clones
        """
        try:
            # Validate commit hash
            if not self._is_valid_commit(commit_hash):
                raise ValueError(f"Invalid commit hash: {commit_hash}")
            
            # Save original branch before checkout
            self._original_branch = self._get_current_branch()
            logger.info(f"Saved original branch: {self._original_branch}")
            
            # Create temporary directory
            self._temp_dir = Path(tempfile.mkdtemp(prefix="insightgraph_"))
            logger.info(f"Created temporary directory: {self._temp_dir}")
            
            # Clone repository to temp directory with optimization
            logger.info(f"Cloning repository to {self._temp_dir}...")
            
            clone_cmd = ["git", "clone"]
            
            # Optimization: Use shallow clone for faster checkout
            if use_shallow_clone:
                clone_cmd.extend(["--depth", "1", "--single-branch"])
                logger.debug("Using shallow clone for faster checkout")
            
            clone_cmd.extend([str(self.repo_path), str(self._temp_dir)])
            
            clone_result = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=True
            )
            logger.info("Repository cloned successfully")
            
            # Checkout specific commit
            logger.info(f"Checking out commit {commit_hash}...")
            checkout_result = subprocess.run(
                ["git", "-C", str(self._temp_dir), "checkout", commit_hash],
                capture_output=True,
                text=True,
                timeout=60,
                check=True
            )
            logger.info(f"Successfully checked out commit {commit_hash}")
            
            return self._temp_dir
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"Git operation timed out for commit {commit_hash}"
            logger.error(error_msg)
            self._cleanup_temp_dir()
            raise RuntimeError(error_msg)
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Git command failed: {e.stderr}"
            logger.error(error_msg)
            self._cleanup_temp_dir()
            raise RuntimeError(error_msg)
            
        except Exception as e:
            error_msg = f"Unexpected error in checkout_commit: {str(e)}"
            logger.error(error_msg)
            self._cleanup_temp_dir()
            raise RuntimeError(error_msg)
    
    def _cleanup_temp_dir(self) -> None:
        """
        Clean up temporary directory if it exists.
        
        This is an internal helper method for error handling.
        Uses Windows-compatible deletion with readonly file handling.
        """
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir, onerror=_remove_readonly)
                logger.info(f"Cleaned up temporary directory: {self._temp_dir}")
                self._temp_dir = None
            except Exception as e:
                logger.error(f"Failed to cleanup temp directory: {e}")
                # Try alternative cleanup method
                try:
                    import time
                    time.sleep(0.5)  # Give Windows time to release file handles
                    shutil.rmtree(self._temp_dir, ignore_errors=True)
                    logger.info(f"Cleaned up temporary directory with ignore_errors: {self._temp_dir}")
                    self._temp_dir = None
                except Exception as e2:
                    logger.error(f"Alternative cleanup also failed: {e2}")
    
    def get_commit_diff(
        self,
        commit_hash: str,
        parent_hash: Optional[str] = None
    ) -> CommitDiff:
        """
        Get the diff between a commit and its parent (or specified parent).
        
        Uses git diff --name-status to categorize file changes as:
        - Added (A): New files in the commit
        - Modified (M): Files that were changed
        - Removed (D): Files that were deleted
        
        Args:
            commit_hash: The commit to compare
            parent_hash: Optional parent commit hash (default: commit^)
        
        Returns:
            CommitDiff object with categorized file lists
        
        Raises:
            ValueError: If commit hash is invalid
            RuntimeError: If git diff command fails
        
        Requirements:
            - 15.5: Compare commits and categorize changes
        """
        try:
            # Validate commit hash
            if not self._is_valid_commit(commit_hash):
                raise ValueError(f"Invalid commit hash: {commit_hash}")
            
            # Determine parent commit
            if parent_hash is None:
                parent_hash = f"{commit_hash}^"
            elif not self._is_valid_commit(parent_hash):
                raise ValueError(f"Invalid parent commit hash: {parent_hash}")
            
            # Execute git diff --name-status
            result = subprocess.run(
                ["git", "diff", "--name-status", parent_hash, commit_hash],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse diff output
            added = []
            modified = []
            removed = []
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('\t', 1)
                if len(parts) < 2:
                    continue
                
                status, filename = parts[0], parts[1]
                
                # Categorize based on status code
                if status.startswith('A'):
                    added.append(filename)
                elif status.startswith('M'):
                    modified.append(filename)
                elif status.startswith('D'):
                    removed.append(filename)
                elif status.startswith('R'):
                    # Renamed files: treat as modified
                    # Format: R100\told_name\tnew_name
                    if '\t' in filename:
                        old_name, new_name = filename.split('\t', 1)
                        removed.append(old_name)
                        added.append(new_name)
                    else:
                        modified.append(filename)
                elif status.startswith('C'):
                    # Copied files: treat as added
                    if '\t' in filename:
                        _, new_name = filename.split('\t', 1)
                        added.append(new_name)
                    else:
                        added.append(filename)
            
            diff = CommitDiff(
                added=added,
                modified=modified,
                removed=removed
            )
            
            logger.info(
                f"Diff for {commit_hash}: "
                f"{len(added)} added, {len(modified)} modified, {len(removed)} removed"
            )
            
            return diff
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to get commit diff: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def restore_original_branch(self) -> None:
        """
        Restore the original branch and cleanup temporary directory.
        
        This method should be called after temporal navigation is complete
        to return to the original state and free up resources.
        
        Uses Windows-compatible deletion with readonly file handling.
        
        Raises:
            RuntimeError: If restoration fails critically (non-cleanup errors)
        
        Requirements:
            - 15.6: Restore original branch after temporal navigation
            - 15.6: Cleanup temporary directory
        """
        cleanup_error = None
        
        try:
            # Cleanup temporary directory if it exists
            if self._temp_dir and self._temp_dir.exists():
                logger.info(f"Cleaning up temporary directory: {self._temp_dir}")
                try:
                    shutil.rmtree(self._temp_dir, onerror=_remove_readonly)
                    logger.info("Temporary directory cleaned up successfully")
                except Exception as e:
                    logger.warning(f"Primary cleanup failed: {e}, trying alternative method")
                    # Try alternative cleanup with ignore_errors
                    try:
                        import time
                        time.sleep(0.5)  # Give Windows time to release file handles
                        shutil.rmtree(self._temp_dir, ignore_errors=True)
                        logger.info("Temporary directory cleaned up with ignore_errors")
                    except Exception as e2:
                        cleanup_error = e2
                        logger.error(f"Alternative cleanup also failed: {e2}")
                
                self._temp_dir = None
            
            # Note: We don't actually checkout the original branch in the main repo
            # because checkout_commit() works in a temporary directory.
            # The main repository remains untouched.
            
            if self._original_branch:
                logger.info(f"Original branch was: {self._original_branch}")
                self._original_branch = None
            
            # Only raise if cleanup failed AND it's a critical error
            # (Windows file permission errors are non-critical, files will be cleaned up later)
            if cleanup_error and not isinstance(cleanup_error, (PermissionError, OSError)):
                raise cleanup_error
                
        except Exception as e:
            # Only raise for non-cleanup errors
            if not isinstance(e, (PermissionError, OSError)):
                error_msg = f"Failed to restore original state: {str(e)}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                logger.warning(f"Cleanup warning (non-critical): {e}")
