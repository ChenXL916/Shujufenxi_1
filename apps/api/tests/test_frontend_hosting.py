from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def frontend_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>live dashboard</title>",
        encoding="utf-8",
    )
    (tmp_path / "assets" / "app.js").write_text("window.liveDashboard = true", encoding="utf-8")
    monkeypatch.setattr("app.main.WEB_DIST", tmp_path)
    return tmp_path


def test_frontend_serves_assets_and_spa_routes(frontend_dist: Path) -> None:
    client = TestClient(app)

    spa = client.get("/overview?start=2026-07-27")
    asset = client.get("/assets/app.js")

    assert spa.status_code == 200
    assert "live dashboard" in spa.text
    assert spa.headers["cache-control"] == "no-store"
    assert asset.status_code == 200
    assert asset.text == "window.liveDashboard = true"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_frontend_fallback_does_not_mask_unknown_api_routes(frontend_dist: Path) -> None:
    response = TestClient(app).get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_frontend_returns_clear_error_when_build_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.WEB_DIST", tmp_path)

    response = TestClient(app).get("/overview")

    assert response.status_code == 503
    assert response.json() == {"detail": "Frontend build is unavailable"}
