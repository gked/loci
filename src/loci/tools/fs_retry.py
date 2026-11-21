"""
Writes to a file another program has open, on Windows.

Windows refuses to open for writing, rename over, or delete a file that another
process holds open without sharing (an editor, a sync client, an antivirus scan,
an agent reading a skill): `PermissionError`, "Access is denied" or "being used
by another process". On macOS and Linux that never happens, so a
`PermissionError` there is a real refusal and is raised at once.

The hold is normally over in milliseconds, so on Windows these helpers retry for
about a second before giving the original error. What the retry costs where it
does not help: a file that stays locked delays its error by about a second
(0.01 s x 1+2+...+14). An open that fails truncates nothing, so retrying a
write is safe.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")

ATTEMPTS = 15
PAUSE_SECONDS = 0.01


def retry_busy(action: Callable[[], T]) -> T:
    """Run `action`, retrying on Windows while the file is in use."""
    for attempt in range(ATTEMPTS):
        try:
            return action()
        except PermissionError:
            if sys.platform != "win32" or attempt == ATTEMPTS - 1:
                raise
            time.sleep(PAUSE_SECONDS * (attempt + 1))
    raise AssertionError("unreachable")     # the last attempt returns or raises


def write_utf8(path: Path, text: str) -> None:
    """`path.write_text` as the vault writes notes: UTF-8, LF line endings."""
    retry_busy(lambda: Path(path).write_text(text, encoding="utf-8", newline="\n"))


def write_bytes(path: Path, data: bytes) -> None:
    retry_busy(lambda: Path(path).write_bytes(data))


def unlink(path: Path) -> None:
    retry_busy(lambda: Path(path).unlink(missing_ok=True))


def replace(src: str | Path, dst: str | Path) -> None:
    retry_busy(lambda: os.replace(src, dst))
