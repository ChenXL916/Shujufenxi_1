from __future__ import annotations

import asyncio
import contextlib
import os
import site
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
VENV_SITE_PACKAGES = ROOT / "apps" / "api" / ".venv" / "Lib" / "site-packages"
site.addsitedir(str(VENV_SITE_PACKAGES))

from dotenv import load_dotenv  # noqa: E402


def _try_acquire_lock(lock_path: Path) -> BinaryIO | None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    if lock_path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _release_lock(handle: BinaryIO) -> None:
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def main() -> int:
    env_file = ROOT / ".env.tunnel"
    if not env_file.is_file():
        raise FileNotFoundError(f"Missing realtime sync environment file: {env_file}")
    load_dotenv(env_file, override=True)
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    log_directory = ROOT / "logs"
    lock = _try_acquire_lock(log_directory / "realtime-sync-service.lock")
    if lock is None:
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stdout_path = log_directory / f"realtime-sync-service-{stamp}.log"
    stderr_path = log_directory / f"realtime-sync-service-{stamp}.err.log"
    try:
        with (
            stdout_path.open("a", encoding="utf-8", buffering=1) as stdout,
            stderr_path.open("a", encoding="utf-8", buffering=1) as stderr,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            from realtime_sync import run_forever

            asyncio.run(run_forever())
    finally:
        _release_lock(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
