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

    build = config["build"]
    assert {key: build[key] for key in ("base", "command", "publish")} == {
        "base": "apps/web",
        "command": "npm run build",
        "publish": "dist",
    }
    assert build["environment"]["NODE_VERSION"] == "22"
    assert "NETLIFY_BACKEND_ORIGIN" not in build["environment"]
    edge_paths = {
        item["path"] for item in config["edge_functions"] if item["function"] == "backend-proxy"
    }
    assert edge_paths == {"/api/*", "/auth/*", "/health", "/ready"}
    assert "write-netlify-redirects.mjs" in package["scripts"]["build"]


def test_netlify_redirects_keep_spa_fallback_after_edge_gateway(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    output = tmp_path / "_redirects"
    env = {
        **os.environ,
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

    assert "backend-proxy edge function" in rules[0]
    assert rules[-1] == "/*  /index.html  200"


def test_netlify_edge_gateway_uses_validated_runtime_origin(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    proxy = (ROOT / "apps" / "web" / "netlify" / "edge-functions" / "backend-proxy.mjs").as_uri()
    script = f"""
import proxy, {{ resetOriginCacheForTests }} from {json.dumps(proxy)};
resetOriginCacheForTests();
const calls = [];
globalThis.fetch = async (input, init = {{}}) => {{
  const url = String(input);
  calls.push({{ url, method: init.method ?? 'GET' }});
  if (url.includes('raw.githubusercontent.com')) {{
    return Response.json({{ origin: 'https://valid-runtime.trycloudflare.com' }});
  }}
  return Response.json(
    {{ ok: true }},
    {{ status: 200, headers: {{ 'set-cookie': 'session=test' }} }},
  );
}};
const response = await proxy(new Request('https://jskzsjfx.netlify.app/api/v1/ping?x=1'));
console.log(JSON.stringify({{ status: response.status, calls }}));
"""
    result = subprocess.run(  # noqa: S603 - executable resolved from the trusted test environment
        [node, "--input-type=module", "--eval", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["status"] == 200
    assert payload["calls"][1] == {
        "url": "https://valid-runtime.trycloudflare.com/api/v1/ping?x=1",
        "method": "GET",
    }


def test_github_pages_loader_uses_the_validated_runtime_origin() -> None:
    loader = (ROOT / "infra" / "github-pages" / "index.html").read_text(encoding="utf-8")

    assert (
        "raw.githubusercontent.com/ChenXL916/Shujufenxi_1/"
        "liveops-runtime/runtime/backend-origin.json" in loader
    )
    assert 'origin.protocol !== "https:"' in loader
    assert '.endsWith(".trycloudflare.com")' in loader
    assert "window.location.replace(target.href)" in loader
    assert 'cache: "no-store"' in loader
