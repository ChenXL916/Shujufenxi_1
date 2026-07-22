from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.oauth import FeishuOAuthClient, FeishuOAuthGrant, FeishuTokenBundle
from app.core.config import Settings
from app.core.secrets import SecretBox
from app.db.base import utc_now
from app.models.entities import SystemSetting

SETTING_KEY = "feishu_user_oauth"
EXPIRY_BUFFER = timedelta(minutes=5)


class FeishuReauthorizationRequired(RuntimeError):
    """The stored user grant is absent, invalid, or can no longer be refreshed."""


@dataclass(frozen=True)
class StoredFeishuCredential:
    access_token: str
    refresh_token: str | None
    access_expires_at: datetime
    refresh_expires_at: datetime | None
    scope: str
    owner_open_id: str


class FeishuOAuthStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.box = SecretBox(settings)

    def load(self, session: Session) -> StoredFeishuCredential | None:
        setting = session.get(SystemSetting, SETTING_KEY)
        if setting is None or not setting.encrypted:
            return None
        value = setting.value
        encrypted_access = value.get("access_token")
        if not isinstance(encrypted_access, str):
            return None
        access_token = self.box.decrypt(encrypted_access)
        encrypted_refresh = value.get("refresh_token")
        refresh_token = (
            self.box.decrypt(encrypted_refresh) if isinstance(encrypted_refresh, str) else None
        )
        if not access_token:
            return None
        try:
            access_expires_at = self._parse_datetime(value["access_expires_at"])
            refresh_expires_at = (
                self._parse_datetime(value["refresh_expires_at"])
                if value.get("refresh_expires_at")
                else None
            )
        except (KeyError, TypeError, ValueError):
            return None
        return StoredFeishuCredential(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            scope=str(value.get("scope") or ""),
            owner_open_id=str(value.get("owner_open_id") or ""),
        )

    def save_grant(
        self,
        session: Session,
        grant: FeishuOAuthGrant,
        updated_by: UUID | None,
    ) -> StoredFeishuCredential:
        return self._save(
            session,
            grant.tokens,
            owner_open_id=grant.identity.user_id,
            updated_by=updated_by,
        )

    async def valid_access_token(
        self,
        session: Session,
        *,
        oauth_client: FeishuOAuthClient | None = None,
    ) -> str:
        credential = self.load(session)
        if credential is None:
            raise FeishuReauthorizationRequired("尚未完成飞书用户授权")
        now = utc_now()
        if credential.access_expires_at > now + EXPIRY_BUFFER:
            return credential.access_token
        if not credential.refresh_token:
            raise FeishuReauthorizationRequired("用户令牌已过期且没有 refresh_token")
        if credential.refresh_expires_at and credential.refresh_expires_at <= now:
            raise FeishuReauthorizationRequired("飞书长期授权已过期，请重新登录授权")
        client = oauth_client or FeishuOAuthClient(self.settings)
        should_close = oauth_client is None
        try:
            bundle = await client.refresh_tokens(credential.refresh_token)
        except Exception as exc:
            raise FeishuReauthorizationRequired("飞书长期授权刷新失败，请重新登录授权") from exc
        finally:
            if should_close:
                await client.close()
        updated = self._save(
            session,
            bundle,
            owner_open_id=credential.owner_open_id,
            updated_by=None,
        )
        return updated.access_token

    def _save(
        self,
        session: Session,
        tokens: FeishuTokenBundle,
        *,
        owner_open_id: str,
        updated_by: UUID | None,
    ) -> StoredFeishuCredential:
        if not tokens.refresh_token:
            raise FeishuReauthorizationRequired(
                "飞书未返回 refresh_token，请在权限管理开通 offline_access 后重新授权"
            )
        now = utc_now()
        access_expires_at = now + timedelta(seconds=tokens.expires_in)
        refresh_expires_at = (
            now + timedelta(seconds=tokens.refresh_token_expires_in)
            if tokens.refresh_token_expires_in is not None
            else None
        )
        value = {
            "access_token": self.box.encrypt(tokens.access_token),
            "refresh_token": self.box.encrypt(tokens.refresh_token),
            "access_expires_at": access_expires_at.isoformat(),
            "refresh_expires_at": refresh_expires_at.isoformat() if refresh_expires_at else None,
            "scope": tokens.scope,
            "owner_open_id": owner_open_id,
        }
        setting = session.get(SystemSetting, SETTING_KEY)
        if setting is None:
            setting = SystemSetting(
                key=SETTING_KEY,
                value=value,
                encrypted=True,
                updated_by=updated_by,
            )
            session.add(setting)
        else:
            setting.value = value
            setting.encrypted = True
            setting.updated_by = updated_by or setting.updated_by
        session.commit()
        return StoredFeishuCredential(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            scope=tokens.scope,
            owner_open_id=owner_open_id,
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
