from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings, get_settings

VALID_PRODUCTION = {
    "app_env": "production",
    "app_base_url": "https://dashboard.example.com",
    "api_base_url": "https://dashboard.example.com/api",
    "cors_origins": ["https://dashboard.example.com"],
    "jwt_secret": "session-signing-secret-with-32-chars-minimum",
    "field_encryption_key": "field-encryption-secret-with-32-chars-minimum",
    "feishu_app_id": "cli_production",
    "feishu_app_secret": "production-app-secret",
    "feishu_redirect_uri": "https://dashboard.example.com/auth/feishu/callback",
}


def test_development_auth_bypass_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.dev_auth_bypass is False


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jwt_secret": "x"}, "JWT_SECRET"),
        ({"field_encryption_key": "x"}, "FIELD_ENCRYPTION_KEY"),
        (
            {"field_encryption_key": VALID_PRODUCTION["jwt_secret"]},
            "必须使用不同密钥",
        ),
        ({"feishu_app_id": ""}, "FEISHU_APP_ID"),
        ({"feishu_app_secret": ""}, "FEISHU_APP_SECRET"),
        ({"app_base_url": "http://localhost:8080"}, "APP_BASE_URL"),
        ({"api_base_url": "http://api:8000"}, "API_BASE_URL"),
        (
            {"feishu_redirect_uri": "http://localhost:8080/auth/feishu/callback"},
            "FEISHU_REDIRECT_URI",
        ),
        ({"cors_origins": ["http://localhost:5173"]}, "CORS_ORIGINS"),
    ],
)
def test_production_configuration_fails_fast(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Settings(_env_file=None, **(VALID_PRODUCTION | overrides))


def test_complete_production_configuration_is_accepted() -> None:
    settings = Settings(_env_file=None, **VALID_PRODUCTION)

    assert settings.feishu_credentials_configured is True


def test_auto_provision_never_grants_developer_role() -> None:
    with pytest.raises(ValueError, match="不能授予 developer"):
        Settings(
            _env_file=None,
            feishu_auto_provision_enabled=True,
            feishu_auto_provision_role="developer",
        )


def test_get_settings_merges_base_and_selected_environment_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_env = tmp_path / ".env"
    tunnel_env = tmp_path / ".env.tunnel"
    base_env.write_text("FEISHU_APP_ID=cli_from_base\nAPP_NAME=base-name\n", encoding="utf-8")
    tunnel_env.write_text("APP_NAME=tunnel-name\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV_FILE", str(tunnel_env))
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.feishu_app_id == "cli_from_base"
    assert settings.app_name == "tunnel-name"
