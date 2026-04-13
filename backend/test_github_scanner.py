from pathlib import Path
import asyncio

import pytest

from github_scanner import (
    GitHubAuthError,
    GitHubCloneTimeoutError,
    GitHubNotFoundError,
    GitHubScanner,
    _build_clone_url,
    _redact_token,
    validate_repository_format,
)


def _dummy_scanner(tmp_root: Path | None = None) -> GitHubScanner:
    async def fake_local(_paths, _cb):
        return {"nodes_created": 0, "relationships_created": 0}

    return GitHubScanner(local_scan_fn=fake_local, temp_root=tmp_root)


def test_validate_repository_format():
    validate_repository_format("owner/repo")
    with pytest.raises(ValueError):
        validate_repository_format("")
    with pytest.raises(ValueError):
        validate_repository_format("owner")
    with pytest.raises(ValueError):
        validate_repository_format("owner/repo/extra")


def test_classify_auth_and_not_found_errors():
    scanner = _dummy_scanner()
    auth = scanner._classify_clone_error("Authentication failed")  # noqa: SLF001
    not_found = scanner._classify_clone_error("Repository not found")  # noqa: SLF001
    assert isinstance(auth, GitHubAuthError)
    assert isinstance(not_found, GitHubNotFoundError)


def test_build_clone_url_and_redaction():
    url = _build_clone_url("owner/repo", "tok-123")
    assert "tok-123" in url
    assert _redact_token(url, "tok-123") == "https://***@github.com/owner/repo.git"


def test_clone_timeout_classification(monkeypatch):
    async def fake_local(_paths, _cb):
        return {"nodes_created": 0, "relationships_created": 0}

    scanner = GitHubScanner(
        local_scan_fn=fake_local,
        temp_root=Path("."),
        clone_timeout_seconds=1,
    )

    class FakeProc:
        returncode = 0

        async def communicate(self):
            await asyncio.sleep(10)
            return b"", b""

        def terminate(self):
            return None

        def kill(self):
            return None

        async def wait(self):
            return None

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr("github_scanner.tempfile.mkdtemp", lambda **_kwargs: "nonexistent-clone-dir")

    from scanner_orchestrator import GitHubConfig

    async def runner():
        with pytest.raises(GitHubCloneTimeoutError):
            await scanner.scan_repository(GitHubConfig(repository="owner/repo"))

    asyncio.run(runner())
