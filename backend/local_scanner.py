"""
Utilities for local scanner file discovery and progress reporting.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator, Sequence, TypeVar

SKIP_DIRS_DEFAULT: set[str] = {
    "node_modules",
    ".git",
    "__pycache__",
    ".gradle",
    "build",
    "dist",
    ".idea",
    ".vscode",
    "target",
    "bin",
    ".next",
    "venv",
    "env",
}

SUPPORTED_EXTENSIONS_DEFAULT: set[str] = {
    ".java",
    ".ts",
    ".tsx",
    ".sql",
    ".prc",
    ".fnc",
    ".pkg",
}


def iter_supported_files(
    project_path: str,
    *,
    skip_dirs: set[str] | None = None,
    supported_extensions: set[str] | None = None,
) -> Iterator[str]:
    skip = skip_dirs or SKIP_DIRS_DEFAULT
    supported = supported_extensions or SUPPORTED_EXTENSIONS_DEFAULT

    for root_dir, dirs, files in os.walk(project_path):
        dirs[:] = [dirname for dirname in dirs if dirname not in skip]
        for file_name in files:
            ext = Path(file_name).suffix.lower()
            if ext in supported:
                yield os.path.join(root_dir, file_name)


def count_supported_files(
    project_path: str,
    *,
    skip_dirs: set[str] | None = None,
    supported_extensions: set[str] | None = None,
) -> int:
    return sum(
        1
        for _ in iter_supported_files(
            project_path,
            skip_dirs=skip_dirs,
            supported_extensions=supported_extensions,
        )
    )


def should_report_progress(scanned_files: int, total_files: int, *, every: int = 10) -> bool:
    if scanned_files <= 0:
        return False
    if total_files > 0 and scanned_files == total_files:
        return True
    return scanned_files % max(1, every) == 0


T = TypeVar("T")


def chunked(items: Sequence[T] | Iterable[T], chunk_size: int) -> Iterator[list[T]]:
    size = max(1, int(chunk_size))
    bucket: list[T] = []
    for item in items:
        bucket.append(item)
        if len(bucket) >= size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket
