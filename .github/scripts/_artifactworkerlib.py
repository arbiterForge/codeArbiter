"""Bounded cleanup for CI-owned worker directories, never a retry of test work."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import tempfile
import time


def cleanup_worker(owner: tempfile.TemporaryDirectory) -> None:
    """Retry only transient Windows sharing errors; other or persistent errors fail.

    Match the existing native farm fixture's two-second/41-attempt boundary.
    The directory owner retains cleanup authority; no caller-supplied path is
    removed, no test is re-executed and no cleanup error is ignored.
    """
    deadline = time.monotonic() + 2.0
    for attempt in range(41):
        try:
            owner.cleanup()
            return
        except PermissionError as error:
            remaining = deadline - time.monotonic()
            if getattr(error, "winerror", None) != 32 or remaining <= 0 or attempt == 40:
                raise
            time.sleep(min(0.05, remaining))


@contextmanager
def worker_directory(*, prefix: str) -> Iterator[str]:
    """Yield one private worker root and require its bounded cleanup on every exit."""
    owner = tempfile.TemporaryDirectory(prefix=prefix)
    try:
        yield owner.name
    finally:
        cleanup_worker(owner)
