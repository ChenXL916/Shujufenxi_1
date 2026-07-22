from __future__ import annotations

import hashlib
from typing import Any, cast

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import Settings


class SessionCodec:
    def __init__(self, settings: Settings) -> None:
        secret = settings.jwt_secret
        if not secret and settings.app_env != "production":
            secret = hashlib.sha256(f"{settings.app_name}:development".encode()).hexdigest()
        self.max_age_seconds = settings.session_max_age_days * 24 * 60 * 60
        self.serializer = URLSafeTimedSerializer(secret, salt="live-ops-session-v1")
        self.state_serializer = URLSafeTimedSerializer(secret, salt="live-ops-oauth-state-v1")

    def dumps(self, payload: dict[str, str]) -> str:
        return self.serializer.dumps(payload)

    def loads(self, value: str) -> dict[str, str] | None:
        if not value:
            return None
        try:
            return cast(dict[str, str], self.serializer.loads(value, max_age=self.max_age_seconds))
        except (BadSignature, SignatureExpired):
            return None

    def dumps_state(self, state: str) -> str:
        return self.state_serializer.dumps({"state": state})

    def loads_state(self, value: str) -> str | None:
        try:
            payload = cast(
                dict[str, Any],
                self.state_serializer.loads(value, max_age=600),
            )
            state = payload.get("state")
            return state if isinstance(state, str) else None
        except (BadSignature, SignatureExpired):
            return None
