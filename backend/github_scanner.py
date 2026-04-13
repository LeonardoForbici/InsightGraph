"""
GitHubScanner - clone and scan GitHub repositories.

This module provides GitHubScanner, responsible for:
- Validating repository format (owner/repo)
- Cloning a repository into a temporary directory (optionally shallow)
- Delegating scanning to a provided local scan coroutine
- Cleaning up temporary directories on success, error, or cancellation

Requirements: 2.1 - 2.10
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from scanner_orchestrator import GitHubConfig, ScanProgress

logger = logging.getLogger(__name__)


class GitHubScannerError(RuntimeError):
    """Base error for GitHub scanning failures."""


class GitHubAuthError(GitHubScannerError):
    """Authentication/authorization error."""


class GitHubNotFoundError(GitHubScannerError):
    """Repository not found error."""


class GitHubCloneTimeoutError(GitHubScannerError):
    """Clone timeout error."""


_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_repository_format(repository: str) -> None:
    if not repository or not repository.strip():
        raise ValueError("GitHub config requires repository")
    repo = repository.strip()
    if not _REPO_RE.match(repo):
        raise ValueError("Invalid repository format. Expected: owner/repo")


def _build_clone_url(repository: str, token: Optional[str]) -> str:
    # NOTE: Never log this URL if it contains token.
    repo = repository.strip()
    if token:
        # GitHub supports token in the URL for HTTPS authentication.
        # Keep it simple; downstream logs must redact.
        return f"https://{token}@github.com/{repo}.git"
    return f"https://github.com/{repo}.git"


def _redact_token(text: str, token: Optional[str]) -> str:
    if not token:
        return text
    return text.replace(token, "***")


@dataclass(frozen=True)
class CloneResult:
    path: Path
    repo_url_redacted: str


class GitHubScanner:
    def __init__(
        self,
        *,
        local_scan_fn: Callable[[list[str], Optional[Callable[[ScanProgress], None]]], Awaitable[dict]],
        clone_timeout_seconds: int = 300,
        temp_root: Optional[Path] = None,
    ) -> None:
        self._local_scan_fn = local_scan_fn
        self._clone_timeout_seconds = int(max(1, clone_timeout_seconds))
        self._temp_root = temp_root

    async def scan_repository(
        self,
        config: GitHubConfig,
        progress_callback: Optional[Callable[[ScanProgress], None]] = None,
    ) -> dict:
        validate_repository_format(config.repository)

        clone_dir: Optional[Path] = None
        try:
            clone = await self._clone_repository(config)
            clone_dir = clone.path
            logger.info("GitHub clone complete: %s", clone.repo_url_redacted)
            return await self._local_scan_fn([str(clone_dir)], progress_callback)
        finally:
            if clone_dir:
                self._cleanup_clone_dir(clone_dir)

    async def _clone_repository(self, config: GitHubConfig) -> CloneResult:
        repo_url = _build_clone_url(config.repository, config.token)
        redacted = _redact_token(repo_url, config.token)

        root = str(self._temp_root) if self._temp_root else None
        unique = uuid.uuid4().hex[:10]
        clone_dir = Path(
            tempfile.mkdtemp(prefix=f"insightgraph-gh-{unique}-", dir=root)
        )

        cmd = ["git", "clone", "--single-branch", "--branch", config.branch]
        if config.shallow_clone:
            cmd += ["--depth", "1"]
        cmd += [repo_url, str(clone_dir)]

        logger.info("Cloning GitHub repository: %s (branch=%s, shallow=%s)", config.repository, config.branch, config.shallow_clone)

        proc: Optional[asyncio.subprocess.Process] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_git_env(),
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=self._clone_timeout_seconds
                )
            except asyncio.TimeoutError as exc:
                await self._terminate_process(proc)
                raise GitHubCloneTimeoutError(
                    f"Git clone timed out after {self._clone_timeout_seconds} seconds"
                ) from exc

            stdout = (stdout_b or b"").decode("utf-8", errors="ignore")
            stderr = (stderr_b or b"").decode("utf-8", errors="ignore")

            if proc.returncode != 0:
                msg = _redact_token((stderr or stdout or "").strip(), config.token)
                raise self._classify_clone_error(msg)

            return CloneResult(path=clone_dir, repo_url_redacted=redacted)

        except asyncio.CancelledError:
            if proc:
                await self._terminate_process(proc)
            raise
        except Exception:
            self._cleanup_clone_dir(clone_dir)
            raise

    def _cleanup_clone_dir(self, clone_dir: Path) -> None:
        try:
            # Safety: never delete root/drive.
            resolved = clone_dir.resolve()
            if resolved.exists() and resolved.is_dir() and len(resolved.parts) > 2:
                shutil.rmtree(resolved, ignore_errors=True)
        except Exception as exc:
            logger.debug("Failed to cleanup clone dir %s: %s", clone_dir, exc)

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                pass

    def _classify_clone_error(self, message: str) -> GitHubScannerError:
        lower = message.lower()
        if "authentication failed" in lower or "access denied" in lower or "403" in lower or "permission" in lower:
            return GitHubAuthError(f"GitHub authentication failed: {message}")
        if "repository not found" in lower or "not found" in lower or "404" in lower:
            return GitHubNotFoundError(f"GitHub repository not found: {message}")
        if "could not resolve host" in lower:
            return GitHubScannerError(f"Network/DNS error during git clone: {message}")
        if "no space left on device" in lower:
            return GitHubScannerError(f"Disk space error during git clone: {message}")
        return GitHubScannerError(f"Git clone failed: {message}")

    def _build_git_env(self) -> dict:
        env = os.environ.copy()
        # Reduce prompts/hangs.
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        return env

