from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class SecretBox:
    def __init__(self, settings: Settings) -> None:
        material = settings.field_encryption_key
        if not material and settings.app_env != "production":
            material = f"{settings.app_name}:development-encryption"
        key = base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())
        self.fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str | None:
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            return None


def mask_secret(value: str) -> str:
    if not value:
        return "未配置"
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}…{value[-4:]}"
