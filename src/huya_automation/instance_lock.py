"""Prevent multiple automation processes from controlling one browser."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class InstanceLockError(RuntimeError):
    """Raised when another automation process already owns the lock."""


def default_lock_file(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    account_id: str | None = None,
    supervisor: bool = False,
) -> Path:
    system = platform_name or platform.system()
    environment = os.environ if environ is None else environ
    if system == "Darwin":
        root = (
            Path.home()
            / "Library"
            / "Application Support"
            / "Huya Automation"
        )
    elif system == "Windows":
        local_app_data = environment.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = str(Path.home() / "AppData" / "Local")
        root = Path(local_app_data) / "Huya Automation"
    else:
        raise InstanceLockError(
            f"不支持的操作系统：{system}。目前仅支持 macOS 和 Windows。"
        )
    if supervisor:
        return root / "supervisor.lock"
    if account_id is None:
        return root / "automation.lock"
    return root / "locks" / f"{account_id}.lock"


def lock_file_handle(lock_file: TextIO) -> None:
    if os.name == "nt":
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write("\0")
            lock_file.flush()
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)


def acquire_instance_lock(
    lock_path: Path | None = None,
    *,
    account_id: str | None = None,
    supervisor: bool = False,
) -> TextIO:
    path = lock_path or default_lock_file(
        account_id=account_id,
        supervisor=supervisor,
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = path.open("a+", encoding="utf-8")
    except OSError as error:
        raise InstanceLockError(f"无法创建进程锁文件 {path}：{error}") from error
    try:
        lock_file_handle(lock_file)
    except (BlockingIOError, OSError) as error:
        lock_file.close()
        raise InstanceLockError(
            "已有一个 huya-open-room 进程正在运行，请勿重复启动。"
        ) from error
    return lock_file
