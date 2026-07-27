from __future__ import annotations

import base64
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, TextIO

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.tunnel"
LOG_DIRECTORY = ROOT / "logs"
PYTHON = ROOT / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
CLOUDFLARED_CANDIDATES = (
    Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"),
    Path(r"C:\Program Files\cloudflared\cloudflared.exe"),
)
READY_URL = "http://127.0.0.1:8000/ready"
TUNNEL_ORIGIN_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
RUNTIME_REPOSITORY = os.getenv("LIVEOPS_RUNTIME_REPOSITORY", "ChenXL916/Shujufenxi_1")
RUNTIME_BRANCH = os.getenv("LIVEOPS_RUNTIME_BRANCH", "liveops-runtime")
RUNTIME_PATH = "runtime/backend-origin.json"


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


def _log(stream: TextIO, message: str) -> None:
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    stream.write(f"{stamp} {message}\n")
    stream.flush()


def _is_ready(timeout_seconds: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(READY_URL, timeout=timeout_seconds) as response:  # noqa: S310
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _wait_until_ready(process: subprocess.Popen[bytes], timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"API exited before readiness, code={process.returncode}")
        if _is_ready():
            return
        time.sleep(2)
    raise TimeoutError("API readiness timed out")


def _cloudflared_path() -> Path:
    command = shutil.which("cloudflared")
    if command:
        return Path(command)
    for candidate in CLOUDFLARED_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("cloudflared.exe is not installed")


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP


def _start_wsl_keeper(service_log: TextIO) -> subprocess.Popen[bytes] | None:
    wsl = shutil.which("wsl")
    if not wsl:
        _log(service_log, "WSL is not installed; continuing without a dependency keeper")
        return None
    process = subprocess.Popen(  # noqa: S603
        [wsl, "--exec", "/bin/sleep", "infinity"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_creation_flags(),
    )
    time.sleep(2)
    if process.poll() is not None:
        raise RuntimeError(f"WSL dependency keeper exited, code={process.returncode}")
    _log(service_log, "WSL dependency keeper started")
    return process


def _start_api(stdout: BinaryIO, stderr: BinaryIO) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    environment["APP_ENV_FILE"] = str(ENV_FILE)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    command = [
        str(PYTHON),
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        str(ROOT / "apps" / "api"),
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--proxy-headers",
        "--forwarded-allow-ips=*",
    ]
    return subprocess.Popen(  # noqa: S603
        command,
        cwd=ROOT,
        env=environment,
        stdout=stdout,
        stderr=stderr,
        creationflags=_creation_flags(),
    )


def _start_tunnel() -> subprocess.Popen[str]:
    command = [
        str(_cloudflared_path()),
        "tunnel",
        "--no-autoupdate",
        "--protocol",
        "http2",
        "--url",
        "http://127.0.0.1:8000",
    ]
    return subprocess.Popen(  # noqa: S603
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_creation_flags(),
    )


def _copy_tunnel_output(
    process: subprocess.Popen[str],
    destination: TextIO,
    messages: queue.Queue[str],
) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        destination.write(line)
        destination.flush()
        messages.put(line)


def _wait_for_tunnel_origin(
    process: subprocess.Popen[str],
    messages: queue.Queue[str],
    timeout_seconds: int = 90,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"cloudflared exited before publishing an origin, code={process.returncode}"
            )
        try:
            message = messages.get(timeout=1)
        except queue.Empty:
            continue
        match = TUNNEL_ORIGIN_PATTERN.search(message)
        if match:
            return match.group(0).lower()
    raise TimeoutError("Cloudflare Quick Tunnel origin timed out")


def _run_gh(endpoint: str, *, method: str = "GET", payload: dict[str, object] | None = None) -> str:
    gh = shutil.which("gh")
    if not gh:
        raise FileNotFoundError("GitHub CLI is not installed")
    command = [gh, "api", endpoint]
    stdin: str | None = None
    if method != "GET":
        command.extend(["--method", method, "--input", "-"])
        stdin = json.dumps(payload or {}, ensure_ascii=False)
    result = subprocess.run(  # noqa: S603
        command,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        message = (
            result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        )
        raise RuntimeError(f"GitHub runtime registry request failed: {message}")
    return result.stdout


def _ensure_runtime_branch() -> None:
    branch_endpoint = f"repos/{RUNTIME_REPOSITORY}/git/ref/heads/{RUNTIME_BRANCH}"
    try:
        _run_gh(branch_endpoint)
        return
    except RuntimeError:
        default_ref = json.loads(_run_gh(f"repos/{RUNTIME_REPOSITORY}/git/ref/heads/main"))
        _run_gh(
            f"repos/{RUNTIME_REPOSITORY}/git/refs",
            method="POST",
            payload={
                "ref": f"refs/heads/{RUNTIME_BRANCH}",
                "sha": default_ref["object"]["sha"],
            },
        )


def _current_registry_file() -> tuple[str | None, dict[str, object] | None]:
    endpoint = f"repos/{RUNTIME_REPOSITORY}/contents/{RUNTIME_PATH}?ref={RUNTIME_BRANCH}"
    try:
        response = json.loads(_run_gh(endpoint))
    except RuntimeError:
        return None, None
    content = base64.b64decode(response["content"]).decode("utf-8")
    return response["sha"], json.loads(content)


def _publish_origin(origin: str) -> bool:
    _ensure_runtime_branch()
    sha, existing = _current_registry_file()
    if existing and existing.get("origin") == origin:
        return False
    document = {
        "origin": origin,
        "kind": "cloudflare_quick_tunnel",
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    content = base64.b64encode(
        (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ).decode("ascii")
    payload: dict[str, object] = {
        "message": "runtime: update live dashboard gateway origin",
        "content": content,
        "branch": RUNTIME_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    _run_gh(
        f"repos/{RUNTIME_REPOSITORY}/contents/{RUNTIME_PATH}",
        method="PUT",
        payload=payload,
    )
    return True


def _publish_with_retry(origin: str, service_log: TextIO) -> None:
    delay = 5
    while True:
        try:
            changed = _publish_origin(origin)
            action = "published" if changed else "already current"
            _log(service_log, f"gateway origin {action}: {origin}")
            return
        except (
            FileNotFoundError,
            RuntimeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            _log(
                service_log,
                f"gateway origin publication failed; retry in {delay}s: {exc}",
            )
            time.sleep(delay)
            delay = min(delay * 2, 300)


def _terminate(process: subprocess.Popen[object] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run(service_log: TextIO) -> int:
    if not ENV_FILE.is_file():
        raise FileNotFoundError(f"Missing production environment file: {ENV_FILE}")
    if not PYTHON.is_file():
        raise FileNotFoundError(f"Missing project Python runtime: {PYTHON}")

    day = datetime.now().strftime("%Y%m%d")
    api_stdout_path = LOG_DIRECTORY / f"gateway-api-{day}.stdout.log"
    api_stderr_path = LOG_DIRECTORY / f"gateway-api-{day}.stderr.log"
    tunnel_log_path = LOG_DIRECTORY / f"gateway-tunnel-{day}.log"
    api: subprocess.Popen[bytes] | None = None
    tunnel: subprocess.Popen[str] | None = None
    wsl_keeper: subprocess.Popen[bytes] | None = None
    try:
        with (
            api_stdout_path.open("ab", buffering=0) as api_stdout,
            api_stderr_path.open("ab", buffering=0) as api_stderr,
            tunnel_log_path.open("a", encoding="utf-8", buffering=1) as tunnel_log,
        ):
            wsl_keeper = _start_wsl_keeper(service_log)
            api = _start_api(api_stdout, api_stderr)
            _log(service_log, f"API starting from {ROOT}")
            _wait_until_ready(api)
            _log(service_log, "API readiness passed")

            tunnel = _start_tunnel()
            messages: queue.Queue[str] = queue.Queue()
            reader = threading.Thread(
                target=_copy_tunnel_output,
                args=(tunnel, tunnel_log, messages),
                daemon=True,
            )
            reader.start()
            origin = _wait_for_tunnel_origin(tunnel, messages)
            _publish_with_retry(origin, service_log)

            failures = 0
            while True:
                if api.poll() is not None:
                    raise RuntimeError(f"API exited, code={api.returncode}")
                if tunnel.poll() is not None:
                    raise RuntimeError(f"cloudflared exited, code={tunnel.returncode}")
                if wsl_keeper is not None and wsl_keeper.poll() is not None:
                    raise RuntimeError(
                        f"WSL dependency keeper exited, code={wsl_keeper.returncode}"
                    )
                if _is_ready(timeout_seconds=5):
                    failures = 0
                else:
                    failures += 1
                    _log(service_log, f"API readiness failed ({failures}/3)")
                    if failures >= 3:
                        raise RuntimeError("API failed three consecutive readiness checks")
                time.sleep(20)
    finally:
        _terminate(tunnel)
        _terminate(api)
        _terminate(wsl_keeper)


def main() -> int:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    lock = _try_acquire_lock(LOG_DIRECTORY / "gateway-service.lock")
    if lock is None:
        return 0
    day = datetime.now().strftime("%Y%m%d")
    service_log_path = LOG_DIRECTORY / f"gateway-service-{day}.log"
    try:
        with service_log_path.open("a", encoding="utf-8", buffering=1) as service_log:
            try:
                return _run(service_log)
            except Exception as exc:  # noqa: BLE001 - service boundary must log and restart
                _log(service_log, f"gateway service stopped: {type(exc).__name__}: {exc}")
                return 1
    finally:
        _release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
