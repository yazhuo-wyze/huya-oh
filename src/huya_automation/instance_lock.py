"""Prevent multiple automation processes from controlling one browser."""

from __future__ import annotations

import fcntl
from pathlib import Path
from typing import TextIO


LOCK_FILE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Huya Automation"
    / "automation.lock"
)


class InstanceLockError(RuntimeError):
    """Raised when another automation process already owns the lock."""


def acquire_instance_lock() -> TextIO:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK_FILE.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_file.close()
        raise InstanceLockError(
            "已有一个 huya-open-room 进程正在运行，请勿重复启动。"
        ) from error
    return lock_file
