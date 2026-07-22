from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.secrets import SecretBox
from app.models.entities import SystemSetting

RUNTIME_KEYS = {
    "live_sync_interval_minutes",
    "schedule_sync_interval_minutes",
    "alert_delay_minutes",
    "feishu_app_id",
    "feishu_app_secret",
    "feishu_bot_webhook_url",
    "feishu_bot_secret",
    "feishu_bot_chat_id",
}


def load_runtime_settings(session: Session) -> Settings:
    base = get_settings()
    box = SecretBox(base)
    updates: dict[str, Any] = {}
    for item in session.scalars(select(SystemSetting).where(SystemSetting.key.in_(RUNTIME_KEYS))):
        value = item.value.get("value")
        if item.encrypted and isinstance(value, str):
            value = box.decrypt(value)
        if value is not None:
            updates[item.key] = value
    return base.model_copy(update=updates)
