import pytest
from fastapi.testclient import TestClient
from redis import RedisError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.main import _expected_migration_heads, app


def ready_engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        [migration_head] = _expected_migration_heads()
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
            {"version_num": migration_head},
        )
    return engine


def test_health_and_request_headers() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "live-ops-dashboard"}
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_ready_uses_fixture_mode_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    class AvailableRedis:
        @classmethod
        def from_url(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
            return cls()

        def ping(self) -> bool:
            return True

        def close(self) -> None:
            return None

    engine = ready_engine()
    monkeypatch.setattr("app.main.get_engine", lambda: engine)
    monkeypatch.setattr("app.main.Redis", AvailableRedis)
    monkeypatch.setattr(
        "app.main.settings",
        Settings(app_env="test", feishu_app_id="", feishu_app_secret=""),
    )
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json()["mode"] == "fixture_mock"


def test_ready_fails_when_redis_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnavailableRedis:
        @classmethod
        def from_url(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
            return cls()

        def ping(self) -> bool:
            raise RedisError("redis unavailable")

        def close(self) -> None:
            return None

    engine = ready_engine()
    monkeypatch.setattr("app.main.get_engine", lambda: engine)
    monkeypatch.setattr("app.main.Redis", UnavailableRedis)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["dependencies"] == {"database": "ok", "redis": "down"}


def test_ready_rejects_empty_database(monkeypatch: pytest.MonkeyPatch) -> None:
    class AvailableRedis:
        @classmethod
        def from_url(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
            return cls()

        def ping(self) -> bool:
            return True

        def close(self) -> None:
            return None

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr("app.main.get_engine", lambda: engine)
    monkeypatch.setattr("app.main.Redis", AvailableRedis)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"] == {
        "database": "schema_outdated",
        "redis": "ok",
    }


def test_ready_normalizes_redis_construction_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class InvalidRedis:
        @classmethod
        def from_url(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RedisError("invalid redis url")

    engine = ready_engine()
    monkeypatch.setattr("app.main.get_engine", lambda: engine)
    monkeypatch.setattr("app.main.Redis", InvalidRedis)

    response = TestClient(app, raise_server_exceptions=False).get("/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"] == {"database": "ok", "redis": "down"}


def test_ready_normalizes_redis_close_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class CloseFailureRedis:
        @classmethod
        def from_url(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
            return cls()

        def ping(self) -> bool:
            return True

        def close(self) -> None:
            raise RedisError("redis close failed")

    engine = ready_engine()
    monkeypatch.setattr("app.main.get_engine", lambda: engine)
    monkeypatch.setattr("app.main.Redis", CloseFailureRedis)

    response = TestClient(app, raise_server_exceptions=False).get("/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"] == {"database": "ok", "redis": "down"}
