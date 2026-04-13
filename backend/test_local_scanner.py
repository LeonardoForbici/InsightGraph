from pathlib import Path

from local_scanner import (
    chunked,
    count_supported_files,
    iter_supported_files,
    should_report_progress,
)


def test_iter_supported_files_filters_extensions_and_dirs():
    original_walk = __import__("os").walk
    try:
        def fake_walk(_project_path):
            yield ("repo", ["src", "node_modules"], ["README.md"])
            yield ("repo/src", [], ["a.ts", "b.java", "c.md"])

        __import__("os").walk = fake_walk
        found = {Path(p).name for p in iter_supported_files("repo")}
        assert found == {"a.ts", "b.java"}
    finally:
        __import__("os").walk = original_walk


def test_count_supported_files():
    original_walk = __import__("os").walk
    try:
        def fake_walk(_project_path):
            yield ("repo", [], ["x.tsx", "y.sql", "z.txt"])

        __import__("os").walk = fake_walk
        assert count_supported_files("repo") == 2
    finally:
        __import__("os").walk = original_walk


def test_should_report_progress_every_ten_and_final():
    assert not should_report_progress(1, 25, every=10)
    assert should_report_progress(10, 25, every=10)
    assert should_report_progress(25, 25, every=10)


def test_chunked():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
