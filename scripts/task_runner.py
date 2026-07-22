from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"


def run(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    command = list(args)
    print(f"[task] {cwd}> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603


def python_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(API)
    env["PYTHONUTF8"] = "1"
    env.setdefault("APP_ENV", "test")
    env.setdefault("DATABASE_URL", "sqlite+pysqlite:///./live_ops_test.db")
    return env


def npm() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def docker() -> str:
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("Docker CLI 未安装；请安装 Docker Desktop/Engine 后重试该目标。")
    return executable


def task_dev() -> None:
    run(docker(), "compose", "up", "--build")


def task_stop() -> None:
    run(docker(), "compose", "down")


def task_logs() -> None:
    run(docker(), "compose", "logs", "-f", "--tail=200")


def task_migrate() -> None:
    run(sys.executable, "-m", "alembic", "upgrade", "head", cwd=API, env=python_env())


def task_seed() -> None:
    run(sys.executable, str(ROOT / "scripts" / "seed_demo.py"), env=python_env())


def task_sync_fixture() -> None:
    run(sys.executable, str(ROOT / "scripts" / "import_excel_fixture.py"), env=python_env())


def task_sync_feishu() -> None:
    run(sys.executable, str(ROOT / "scripts" / "sync_feishu.py"), env=python_env())


def task_test_unit() -> None:
    run(sys.executable, "-m", "pytest", "-m", "not integration", cwd=API, env=python_env())
    run(npm(), "run", "test:unit", cwd=WEB)


def task_test_integration() -> None:
    run(sys.executable, "-m", "pytest", "-m", "integration", cwd=API, env=python_env())


def task_test_e2e() -> None:
    run(npm(), "run", "test:e2e", cwd=WEB)


def task_test() -> None:
    run(sys.executable, "-m", "pytest", cwd=API, env=python_env())
    run(npm(), "run", "test:unit", cwd=WEB)


def task_lint() -> None:
    run(
        sys.executable,
        "-m",
        "ruff",
        "check",
        "app",
        "tests",
        str(ROOT / "scripts"),
        str(ROOT / "infra" / "scripts"),
        cwd=API,
    )
    run(npm(), "run", "lint", cwd=WEB)


def task_typecheck() -> None:
    run(sys.executable, "-m", "mypy", "app", cwd=API)
    run(npm(), "run", "typecheck", cwd=WEB)


def task_format() -> None:
    run(
        sys.executable,
        "-m",
        "ruff",
        "format",
        "app",
        "tests",
        str(ROOT / "scripts"),
        str(ROOT / "infra" / "scripts"),
        cwd=API,
    )
    task_lint()
    run(npm(), "run", "format", cwd=WEB)


def task_check() -> None:
    run(
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        "app",
        "tests",
        str(ROOT / "scripts"),
        str(ROOT / "infra" / "scripts"),
        cwd=API,
    )
    task_lint()
    task_typecheck()
    run(
        sys.executable,
        "-m",
        "pytest",
        "--cov=app.domain",
        "--cov=app.services",
        "--cov-fail-under=85",
        cwd=API,
        env=python_env(),
    )
    run(npm(), "run", "format:check", cwd=WEB)
    run(npm(), "run", "test:unit", cwd=WEB)
    task_build()
    run(npm(), "run", "test:e2e", cwd=WEB)


def task_build() -> None:
    run(npm(), "run", "build", cwd=WEB)
    run(sys.executable, "-m", "compileall", "-q", "app", cwd=API)


def task_backup() -> None:
    run(sys.executable, str(ROOT / "infra" / "scripts" / "backup.py"))


def task_verify_production() -> None:
    run(sys.executable, str(ROOT / "scripts" / "verify_production.py"), env=python_env())


TASKS = {
    "dev": task_dev,
    "stop": task_stop,
    "logs": task_logs,
    "migrate": task_migrate,
    "seed": task_seed,
    "sync-fixture": task_sync_fixture,
    "sync-feishu": task_sync_feishu,
    "test": task_test,
    "test-unit": task_test_unit,
    "test-integration": task_test_integration,
    "test-e2e": task_test_e2e,
    "lint": task_lint,
    "typecheck": task_typecheck,
    "format": task_format,
    "check": task_check,
    "build": task_build,
    "backup": task_backup,
    "verify-production": task_verify_production,
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        print("用法: make <" + "|".join(TASKS) + ">", file=sys.stderr)
        return 2
    try:
        TASKS[sys.argv[1]]()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[task] 失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
