from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import inspect as sql_inspect
from sqlalchemy import text as sql_text

from app.admin.permission_router import router as permission_admin_router
from app.admin.router import router as admin_router
from app.api.anchor_trend_router import router as anchor_trend_router
from app.api.hourly_comparison_router import router as hourly_comparison_router
from app.api.router import router as api_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.db.session import get_engine

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(message)s")
logger = logging.getLogger("live_ops.request")
API_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DATABASE_TABLES = frozenset(
    {"alembic_version", "rooms", "hourly_facts", "sync_runs", "users"}
)


def _expected_migration_heads() -> frozenset[str]:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def _database_dependency_status() -> str:
    try:
        expected_heads = _expected_migration_heads()
        with get_engine().connect() as connection:
            connection.execute(sql_text("SELECT 1"))
            tables = frozenset(sql_inspect(connection).get_table_names())
            current_heads = frozenset(MigrationContext.configure(connection).get_current_heads())
        if not REQUIRED_DATABASE_TABLES.issubset(tables) or current_heads != expected_heads:
            logger.warning("Database schema is not at the application migration head")
            return "schema_outdated"
        return "ok"
    except Exception as exc:
        logger.warning("Database readiness probe failed: %s", type(exc).__name__)
        return "down"


def _redis_dependency_status() -> str:
    redis_client: Redis | None = None
    status = "down"
    try:
        redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
        status = "ok" if redis_client.ping() else "down"
    except Exception as exc:
        logger.warning("Redis readiness probe failed: %s", type(exc).__name__)
    finally:
        if redis_client is not None:
            try:
                redis_client.close()
            except Exception as exc:
                logger.warning("Redis readiness cleanup failed: %s", type(exc).__name__)
                status = "down"
    return status


app = FastAPI(
    title="多直播间小时数据驾驶舱 API",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token"],
)
app.include_router(api_router)
app.include_router(hourly_comparison_router)
app.include_router(anchor_trend_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(permission_admin_router)


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
            ensure_ascii=False,
        )
    )
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready", tags=["health"])
def ready() -> Response:
    dependencies = {
        "database": _database_dependency_status(),
        "redis": _redis_dependency_status(),
    }
    healthy = all(status == "ok" for status in dependencies.values())
    payload = {
        "status": "ready" if healthy else "not_ready",
        "mode": "feishu" if settings.feishu_credentials_configured else "fixture_mock",
        "bot_configured": settings.feishu_bot_configured,
        "dependencies": dependencies,
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)
