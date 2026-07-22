from __future__ import annotations

import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]


def require(path: str) -> None:
    if not (ROOT / path).exists():
        raise RuntimeError(f"缺少生产文件：{path}")


def main() -> None:
    required = [
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "apps/api/Dockerfile",
        "apps/web/Dockerfile",
        "infra/nginx/default.conf",
        "infra/scripts/backup.py",
        "docs/DEPLOYMENT.md",
        "docs/OPERATIONS.md",
        "docs/FEISHU_SETUP.md",
    ]
    for path in required:
        require(path)

    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text("utf-8"))
    expected = {
        "postgres",
        "redis",
        "api",
        "celery-worker",
        "celery-beat",
        "web",
        "reverse-proxy",
    }
    if set(compose.get("services", {})) != expected:
        raise RuntimeError("Compose 服务必须严格包含 7 个预期服务")
    api_build = compose["services"]["api"]["build"]
    if api_build.get("context") != "." or api_build.get("dockerfile") != "apps/api/Dockerfile":
        raise RuntimeError("API Docker 构建上下文无法包含 config/fixtures")
    production_compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text("utf-8"))
    production_command = production_compose["services"]["api"].get("command", [])
    command_text = (
        " ".join(production_command)
        if isinstance(production_command, list)
        else str(production_command)
    )
    if "alembic upgrade head" not in command_text or "uvicorn app.main:app" not in command_text:
        raise RuntimeError("生产 API 启动命令必须先迁移再启动服务")
    if "seed_demo" in command_text or "import_excel_fixture" in command_text:
        raise RuntimeError("生产 API 启动命令禁止写入演示或夹具数据")

    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from app.core.config import Settings
    from app.core.paths import project_root
    from app.db.base import Base
    from app.models import entities  # noqa: F401

    try:
        Settings(
            app_env="production",
            dev_auth_bypass=True,
            jwt_secret="change_me",  # noqa: S106
            field_encryption_key="change_me",
        )
    except ValueError:
        pass
    else:
        raise RuntimeError("生产弱密钥/开发登录旁路未被拒绝")
    Settings(
        app_env="production",
        dev_auth_bypass=False,
        app_base_url="https://dashboard.example.com",
        api_base_url="https://api.dashboard.example.com",
        feishu_redirect_uri="https://dashboard.example.com/auth/feishu/callback",
        cors_origins=["https://dashboard.example.com"],
        jwt_secret=secrets.token_urlsafe(32),
        field_encryption_key=secrets.token_urlsafe(32),
        feishu_app_id="cli_production_verification",
        feishu_app_secret=secrets.token_urlsafe(24),
    )
    if project_root() != ROOT:
        raise RuntimeError("项目根目录发现逻辑异常")
    expected_tables = set(Base.metadata.tables)

    with tempfile.TemporaryDirectory() as directory:
        database_url = f"sqlite+pysqlite:///{Path(directory) / 'verify.db'}"
        env = {
            **__import__("os").environ,
            "DATABASE_URL": database_url,
        }
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "apps" / "api",
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        engine = create_engine(database_url)
        migrated_tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
        engine.dispose()
        if migrated_tables != expected_tables:
            missing = sorted(expected_tables - migrated_tables)
            unexpected = sorted(migrated_tables - expected_tables)
            raise RuntimeError(f"迁移表集合与模型不一致：缺少={missing}，多余={unexpected}")

    docker = shutil.which("docker")
    if docker:
        subprocess.run(  # noqa: S603
            [
                docker,
                "compose",
                "-f",
                "docker-compose.yml",
                "-f",
                "docker-compose.prod.yml",
                "config",
                "--quiet",
            ],
            cwd=ROOT,
            check=True,
        )
        docker_status = "通过 docker compose config"
    else:
        docker_status = "Docker CLI 不可用，已完成等价 YAML/路径/安全静态校验"
    print(
        f"生产验证通过：7 服务、{len(expected_tables)} 表、迁移、强密钥策略、"
        "生产无夹具写入、Docker 构建路径均有效。"
    )
    print(docker_status)


if __name__ == "__main__":
    main()
