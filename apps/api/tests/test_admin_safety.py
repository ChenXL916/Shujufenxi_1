import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.admin import router as admin_router
from app.auth.dependencies import AccessScope
from app.core import runtime_settings as runtime_settings_module
from app.core.config import Settings
from app.db.base import Base
from app.models.entities import SystemSetting


def test_admin_settings_expose_only_secret_configuration_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        app_env="test",
        feishu_app_id="cli_sensitive_value",
        feishu_app_secret="secret_sensitive_value",  # noqa: S106
        feishu_bot_webhook_url="https://example.test/sensitive-hook",
        feishu_bot_secret="bot_sensitive_value",  # noqa: S106
        feishu_bot_chat_id="oc_sensitive_value",
    )
    monkeypatch.setattr(admin_router, "load_runtime_settings", lambda _session: settings)

    with Session(engine) as session:
        payload = admin_router.system_settings(
            session,
            AccessScope(user_id=uuid4(), role="admin", room_ids=None, can_export=True),
        )

    assert payload["feishu_app_configured"] is True
    assert payload["feishu_bot_configured"] is True
    assert payload["feishu_bot_webhook_configured"] is True
    assert payload["feishu_bot_chat_configured"] is True
    assert not {
        "feishu_bot_webhook_url",
        "feishu_bot_secret",
        "feishu_bot_chat_id",
        "feishu_app_id",
        "feishu_app_secret",
    }.intersection(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "sensitive" not in serialized


def test_admin_can_store_official_webhook_without_exposing_or_accidentally_clearing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(app_env="test", field_encryption_key="test-encryption-key")
    monkeypatch.setattr(admin_router, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_settings_module, "get_settings", lambda: settings)
    access = AccessScope(user_id=uuid4(), role="admin", room_ids=None, can_export=True)
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/v1/admin/settings",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/unit-test-token"

    with Session(engine) as session:
        response = admin_router.update_settings(
            admin_router.SettingsPatch(
                feishu_app_id="cli_unit_test_app_id",
                feishu_app_secret="unit-test-app-secret",  # noqa: S106
                feishu_bot_webhook_url=webhook,
                feishu_bot_secret="unit-test-secret",  # noqa: S106
            ),
            request,
            session,
            access,
        )
        stored = session.get(SystemSetting, "feishu_bot_webhook_url")
        assert stored is not None
        assert stored.encrypted is True
        assert webhook not in json.dumps(stored.value)
        assert response["feishu_bot_webhook_configured"] is True
        assert response["feishu_app_configured"] is True
        assert webhook not in json.dumps(response)
        assert "unit-test-app-secret" not in json.dumps(response)

        admin_router.update_settings(
            admin_router.SettingsPatch(
                live_sync_interval_minutes=3,
                feishu_app_id="",
                feishu_app_secret="   ",  # noqa: S106
                feishu_bot_webhook_url="   ",
                feishu_bot_secret="",
            ),
            request,
            session,
            access,
        )
        loaded = runtime_settings_module.load_runtime_settings(session)
        assert loaded.live_sync_interval_minutes == 3
        assert loaded.feishu_app_id == "cli_unit_test_app_id"
        assert loaded.feishu_app_secret == "unit-test-app-secret"  # noqa: S105
        assert loaded.feishu_bot_webhook_url == webhook
        assert loaded.feishu_bot_secret == "unit-test-secret"  # noqa: S105


def test_admin_rejects_non_feishu_webhook_urls() -> None:
    with pytest.raises(ValidationError, match="仅支持飞书官方群机器人"):
        admin_router.SettingsPatch(
            feishu_bot_webhook_url="https://example.test/open-apis/bot/v2/hook/not-feishu"
        )
