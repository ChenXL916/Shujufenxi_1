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
        "apps/sites-web/.openai/hosting.json",
        "apps/sites-web/worker/gateway.mjs",
        "apps/sites-web/scripts/stage-dashboard.mjs",
        ".env.cloud.example",
        "docker-compose.cloud.yml",
        "infra/caddy/Caddyfile",
        "infra/scripts/deploy_cloud_backend.sh",
        "infra/scripts/verify_cloud_backend.py",
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

    cloud_compose = yaml.safe_load((ROOT / "docker-compose.cloud.yml").read_text("utf-8"))
    cloud_services = cloud_compose.get("services", {})
    expected_cloud_services = {
        "postgres",
        "redis",
        "api",
        "celery-worker",
        "celery-beat",
        "migrate-data",
        "api-gateway",
    }
    if set(cloud_services) != expected_cloud_services:
        raise RuntimeError("云端 Compose 服务集合不完整")
    if "ports" in cloud_services["postgres"] or "ports" in cloud_services["redis"]:
        raise RuntimeError("云端 PostgreSQL/Redis 禁止暴露公网端口")
    if not cloud_compose.get("networks", {}).get("backend", {}).get("internal"):
        raise RuntimeError("云端数据库网络必须是 internal")
    cloud_api_command = " ".join(cloud_services["api"].get("command", []))
    if "seed_demo" in cloud_api_command or "import_excel_fixture" in cloud_api_command:
        raise RuntimeError("云端 API 启动禁止写入演示或 fixture 数据")
    migration_command = " ".join(cloud_services["migrate-data"].get("command", []))
    if (
        "migrate_sqlite_to_postgres.py" not in migration_command
        or "--manifest" not in migration_command
    ):
        raise RuntimeError("云端迁移服务必须生成可核验迁移清单")

    hosting = yaml.safe_load(
        (ROOT / "apps" / "sites-web" / ".openai" / "hosting.json").read_text("utf-8")
    )
    if not str(hosting.get("project_id", "")).startswith("appgprj_"):
        raise RuntimeError("Sites 项目 ID 未持久化")
    gateway = (ROOT / "apps" / "sites-web" / "worker" / "gateway.mjs").read_text("utf-8")
    for marker in ("BACKEND_ORIGIN", "BACKEND_GATEWAY_TOKEN"):
        if marker not in gateway:
            raise RuntimeError(f"Sites 同源网关缺少生产能力：{marker}")
    vite = (ROOT / "apps" / "sites-web" / "vite.config.ts").read_text("utf-8")
    for marker in ('"single-page-application"', "run_worker_first: true"):
        if marker not in vite:
            raise RuntimeError(f"Sites SPA 生产回退配置缺失：{marker}")

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
