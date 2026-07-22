from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.integrations.feishu.client import FeishuError


@dataclass(frozen=True)
class FeishuIdentity:
    user_id: str
    name: str
    avatar_url: str | None
    email: str | None


@dataclass(frozen=True)
class FeishuTokenBundle:
    access_token: str
    expires_in: int
    refresh_token: str | None
    refresh_token_expires_in: int | None
    scope: str


@dataclass(frozen=True)
class FeishuOAuthGrant:
    identity: FeishuIdentity
    tokens: FeishuTokenBundle


class FeishuOAuthClient:
    base_url = "https://open.feishu.cn/open-apis"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.http = http_client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=5, read=15, write=10, pool=5),
        )

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self.settings.feishu_app_id,
                "response_type": "code",
                "redirect_uri": self.settings.feishu_redirect_uri,
                "scope": "bitable:app:readonly offline_access",
                "state": state,
            }
        )
        return f"https://accounts.feishu.cn/open-apis/authen/v1/authorize?{query}"

    async def exchange_authorization(self, code: str) -> FeishuOAuthGrant:
        response = await self.http.post(
            f"{self.base_url}/authen/v2/oauth/token",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "grant_type": "authorization_code",
                "client_id": self.settings.feishu_app_id,
                "client_secret": self.settings.feishu_app_secret,
                "code": code,
                "redirect_uri": self.settings.feishu_redirect_uri,
            },
        )
        payload = cast(dict[str, Any], response.json())
        if response.status_code >= 400 or payload.get("code", 0) != 0:
            code_value = payload.get("code") or payload.get("error") or response.status_code
            raise FeishuError(f"飞书 OAuth 授权码交换失败 code={code_value}")
        data = cast(dict[str, Any], payload.get("data", payload))
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise FeishuError("飞书 OAuth 响应缺少用户访问令牌")
        user_response = await self.http.get(
            f"{self.base_url}/authen/v1/user_info",
            headers={"Authorization": f"Bearer {token}"},
        )
        user_payload = cast(dict[str, Any], user_response.json())
        if user_response.status_code >= 400 or user_payload.get("code", 0) != 0:
            raise FeishuError("飞书用户身份读取失败")
        user = cast(dict[str, Any], user_payload.get("data", user_payload))
        user_id = user.get("open_id") or user.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise FeishuError("飞书身份响应缺少用户标识")
        refresh_token = data.get("refresh_token")
        return FeishuOAuthGrant(
            identity=FeishuIdentity(
                user_id=user_id,
                name=str(user.get("name") or "飞书用户"),
                avatar_url=(
                    user.get("avatar_url") if isinstance(user.get("avatar_url"), str) else None
                ),
                email=user.get("email") if isinstance(user.get("email"), str) else None,
            ),
            tokens=FeishuTokenBundle(
                access_token=token,
                expires_in=max(60, int(data.get("expires_in", 7200))),
                refresh_token=refresh_token if isinstance(refresh_token, str) else None,
                refresh_token_expires_in=(
                    int(data["refresh_token_expires_in"])
                    if data.get("refresh_token_expires_in") is not None
                    else None
                ),
                scope=str(data.get("scope") or ""),
            ),
        )

    async def exchange_identity(self, code: str) -> FeishuIdentity:
        """Backward-compatible identity-only helper."""
        return (await self.exchange_authorization(code)).identity

    async def refresh_tokens(self, refresh_token: str) -> FeishuTokenBundle:
        response = await self.http.post(
            f"{self.base_url}/authen/v2/oauth/token",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "grant_type": "refresh_token",
                "client_id": self.settings.feishu_app_id,
                "client_secret": self.settings.feishu_app_secret,
                "refresh_token": refresh_token,
            },
        )
        payload = cast(dict[str, Any], response.json())
        if response.status_code >= 400 or payload.get("code", 0) != 0:
            code_value = payload.get("code") or payload.get("error") or response.status_code
            raise FeishuError(f"飞书用户令牌刷新失败 code={code_value}")
        data = cast(dict[str, Any], payload.get("data", payload))
        access_token = data.get("access_token")
        rotated_refresh = data.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise FeishuError("飞书刷新响应缺少 access_token")
        if not isinstance(rotated_refresh, str) or not rotated_refresh:
            raise FeishuError("飞书刷新响应缺少新的 refresh_token，请重新授权 offline_access")
        return FeishuTokenBundle(
            access_token=access_token,
            expires_in=max(60, int(data.get("expires_in", 7200))),
            refresh_token=rotated_refresh,
            refresh_token_expires_in=(
                int(data["refresh_token_expires_in"])
                if data.get("refresh_token_expires_in") is not None
                else None
            ),
            scope=str(data.get("scope") or ""),
        )

    async def close(self) -> None:
        await self.http.aclose()
