import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_production_compose_never_loads_demo_or_fixture_data() -> None:
    production = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    command = production["services"]["api"]["command"]
    command_text = " ".join(command) if isinstance(command, list) else str(command)

    assert "alembic upgrade head" in command_text
    assert "uvicorn app.main:app" in command_text
    assert "seed_demo" not in command_text
    assert "import_excel_fixture" not in command_text


def test_all_nginx_entrypoints_set_security_headers_on_every_response() -> None:
    required_headers = {
        "Content-Security-Policy",
        "Permissions-Policy",
        "Referrer-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
    }
    configs = [ROOT / "apps" / "web" / "nginx.conf", ROOT / "infra" / "nginx" / "default.conf"]

    for config in configs:
        content = config.read_text(encoding="utf-8")
        for header in required_headers:
            assert f"add_header {header}" in content, f"{config} 缺少 {header}"
        assert content.count(" always;") >= len(required_headers)


def test_compose_healthcheck_uses_readiness_endpoint() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    healthcheck = " ".join(compose["services"]["api"]["healthcheck"]["test"])

    assert "/ready" in healthcheck
    assert "/health" not in healthcheck


def test_production_compose_requires_authentication_configuration() -> None:
    production = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    required = {
        "APP_BASE_URL",
        "API_BASE_URL",
        "CORS_ORIGINS",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_REDIRECT_URI",
        "FIELD_ENCRYPTION_KEY",
        "JWT_SECRET",
    }

    for service_name in ("api", "celery-worker", "celery-beat"):
        environment = production["services"][service_name]["environment"]
        assert required <= set(environment), f"{service_name} 缺少生产认证配置"


def test_netlify_builds_the_vite_app_from_the_monorepo() -> None:
    config = tomllib.loads((ROOT / "netlify.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8"))

    assert config["build"] == {
        "base": "apps/web",
        "command": "npm run build",
        "publish": "dist",
        "environment": {"NODE_VERSION": "22"},
    }
    assert "write-netlify-redirects.mjs" in package["scripts"]["build"]


def test_netlify_redirects_proxy_backend_before_spa_fallback(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    output = tmp_path / "_redirects"
    env = {
        **os.environ,
        "NETLIFY_BACKEND_ORIGIN": "https://api.example.com/",
        "NETLIFY_REDIRECTS_OUTPUT": str(output),
    }

    subprocess.run(  # noqa: S603 - executable resolved from the trusted test environment
        [node, "scripts/write-netlify-redirects.mjs"],
        cwd=ROOT / "apps" / "web",
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    rules = output.read_text(encoding="utf-8").splitlines()

    assert rules[:4] == [
        "/api/*  https://api.example.com/api/:splat  200",
        "/auth/*  https://api.example.com/auth/:splat  200",
        "/health  https://api.example.com/health  200",
        "/ready  https://api.example.com/ready  200",
    ]
    assert rules[-1] == "/*  /index.html  200"
