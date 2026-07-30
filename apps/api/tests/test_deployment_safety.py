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
    assert 'new URL("/health", origin)' in loader
    assert 'credentials: "omit"' in loader
    assert "await assertOriginReady(origin)" in loader
    assert "window.setTimeout(connect, retryDelayMs)" in loader
    assert "检测到网关地址正在切换" in loader
    assert "window.location.replace(target.href)" in loader
    assert 'cache: "no-store"' in loader


def test_frontend_boot_fallback_supports_older_safari_and_public_recovery() -> None:
    index = (ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")
    vite = (ROOT / "apps" / "web" / "vite.config.ts").read_text(encoding="utf-8")

    assert "boot-fallback" in index
    assert "liveops-public-boot-retry" in index
    assert "window.location.reload()" in index
    assert "https://chenxl916.github.io/Shujufenxi_1/" in index
    assert "<noscript>" in index
    assert "target: ['es2019', 'safari13']" in vite
    assert "cssTarget: 'safari13'" in vite


def test_sites_gateway_build_preserves_same_origin_auth_and_spa_routes() -> None:
    package = json.loads((ROOT / "apps" / "sites-web" / "package.json").read_text(encoding="utf-8"))
    hosting = json.loads(
        (ROOT / "apps" / "sites-web" / ".openai" / "hosting.json").read_text(encoding="utf-8")
    )
    gateway = (ROOT / "apps" / "sites-web" / "worker" / "gateway.mjs").read_text(encoding="utf-8")
    vite = (ROOT / "apps" / "sites-web" / "vite.config.ts").read_text(encoding="utf-8")

    assert hosting["project_id"].startswith("appgprj_")
    assert hosting["d1"] is None
    assert hosting["r2"] is None
    assert "npm --prefix ../web run build" in package["scripts"]["build"]
    assert "stage-dashboard.mjs" in package["scripts"]["stage:dashboard"]
    assert "npm run stage:dashboard" in package["scripts"]["build:sites"]
    for path in ("/api/", "/auth/", "/health", "/ready"):
        assert path in gateway
    assert "BACKEND_ORIGIN" in gateway
    assert "BACKEND_GATEWAY_TOKEN" in gateway
    assert '"single-page-application"' in vite
    assert "run_worker_first: true" in vite
    assert 'for (const fallbackPath of ["/index.html", "/"])' in gateway
    assert "Set-Cookie" not in gateway
    assert "live_ops_session" not in gateway


def test_cloud_compose_keeps_data_services_private_and_runs_real_workers() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.cloud.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert set(services) == {
        "postgres",
        "redis",
        "api",
        "celery-worker",
        "celery-beat",
        "migrate-data",
        "api-gateway",
    }
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    assert compose["networks"]["backend"]["internal"] is True
    assert services["api-gateway"]["ports"] == ["80:80", "443:443"]
    assert services["celery-worker"]["command"][0] == "celery"
    assert services["celery-beat"]["command"][0] == "celery"
    assert services["migrate-data"]["profiles"] == ["migration"]
    migration_command = " ".join(services["migrate-data"]["command"])
    assert "migrate_sqlite_to_postgres.py" in migration_command
    assert "--manifest /migration/manifest.json" in migration_command
    api_command = " ".join(services["api"]["command"])
    assert "seed_demo" not in api_command
    assert "import_excel_fixture" not in api_command


def test_cloud_gateway_requires_sites_secret_for_non_health_routes() -> None:
    caddy = (ROOT / "infra" / "caddy" / "Caddyfile").read_text(encoding="utf-8")

    assert "@health path /health /ready" in caddy
    assert "X-LiveOps-Gateway-Token {$SITES_GATEWAY_TOKEN}" in caddy
    assert 'respond "Forbidden" 403' in caddy
