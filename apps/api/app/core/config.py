from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_public_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and bool(hostname)
        and hostname != "localhost"
        and not hostname.endswith(".localhost")
        and hostname not in {"127.0.0.1", "::1"}
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "live-ops-dashboard"
    app_base_url: str = "http://localhost:8080"
    api_base_url: str = "http://localhost:8000"
    timezone: str = "Asia/Shanghai"
    database_url: str = "sqlite+pysqlite:///./live_ops.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = ""
    field_encryption_key: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_redirect_uri: str = "http://localhost:8080/auth/feishu/callback"
    feishu_live_app_token: str = ""
    feishu_live_table_id: str = ""
    feishu_live_view_id: str = ""
    feishu_schedule_app_token: str = ""
    feishu_schedule_table_id: str = ""
    feishu_schedule_view_id: str = ""
    feishu_schedule_year: int | None = None
    feishu_bot_webhook_url: str = ""
    feishu_bot_secret: str = ""
    feishu_bot_chat_id: str = ""
    feishu_auto_provision_enabled: bool = False
    feishu_auto_provision_role: str = "live_manager"

    live_sync_interval_minutes: int = 5
    schedule_sync_interval_minutes: int = 30
    data_submission_deadline_hour: int = Field(default=8, ge=0, le=23)
    alert_delay_minutes: int = 15
    alert_retry_limit: int = 3

    dev_auth_bypass: bool = False
    dev_admin_email: str = "dev@example.com"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def enforce_production_security(self) -> Settings:
        if self.feishu_auto_provision_enabled and self.feishu_auto_provision_role == "developer":
            raise ValueError("飞书自动开户不能授予 developer 角色")
        if self.app_env == "production":
            if self.dev_auth_bypass:
                raise ValueError("生产环境必须关闭 DEV_AUTH_BYPASS")
            if len(self.jwt_secret.strip()) < 32:
                raise ValueError("生产环境 JWT_SECRET 至少需要 32 个字符")
            if len(self.field_encryption_key.strip()) < 32:
                raise ValueError("生产环境 FIELD_ENCRYPTION_KEY 至少需要 32 个字符")
            if self.jwt_secret == self.field_encryption_key:
                raise ValueError("JWT_SECRET 与 FIELD_ENCRYPTION_KEY 必须使用不同密钥")
            if not self.feishu_app_id.strip():
                raise ValueError("生产环境必须配置 FEISHU_APP_ID")
            if not self.feishu_app_secret.strip():
                raise ValueError("生产环境必须配置 FEISHU_APP_SECRET")
            public_urls = {
                "APP_BASE_URL": self.app_base_url,
                "API_BASE_URL": self.api_base_url,
                "FEISHU_REDIRECT_URI": self.feishu_redirect_uri,
            }
            for name, value in public_urls.items():
                if not _is_public_https_url(value):
                    raise ValueError(f"生产环境 {name} 必须是非 localhost 的 HTTPS URL")
            if not self.cors_origins or any(
                not _is_public_https_url(origin) for origin in self.cors_origins
            ):
                raise ValueError("生产环境 CORS_ORIGINS 必须全部是非 localhost 的 HTTPS URL")
        return self

    @property
    def feishu_credentials_configured(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret)

    @property
    def feishu_webhook_bot_configured(self) -> bool:
        return bool(self.feishu_bot_webhook_url)

    @property
    def feishu_app_bot_configured(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret and self.feishu_bot_chat_id)

    @property
    def feishu_bot_configured(self) -> bool:
        return self.feishu_webhook_bot_configured or self.feishu_app_bot_configured


@lru_cache
def get_settings() -> Settings:
    selected_env_file = os.getenv("APP_ENV_FILE")
    env_file = (".env", selected_env_file) if selected_env_file else ".env"
    return Settings(_env_file=env_file)
