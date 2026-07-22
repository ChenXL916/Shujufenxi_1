from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx

from app.integrations.feishu.client import FeishuError


class FeishuBotClient:
    def __init__(
        self,
        webhook_url: str,
        secret: str = "",
        *,
        http_client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not webhook_url.startswith("https://") and not webhook_url.startswith("http://"):
            raise ValueError("机器人 Webhook URL 无效")
        self.webhook_url = webhook_url
        self.secret = secret
        self.http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=10, write=10, pool=5)
        )
        self.max_attempts = max_attempts
        self.sleep = sleep

    @staticmethod
    def signature(timestamp: int, secret: str) -> str:
        string_to_sign = f"{timestamp}\n{secret}".encode()
        digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    @staticmethod
    def build_card(
        title: str,
        lines: list[str],
        links: dict[str, str],
        *,
        template: str = "red",
    ) -> dict[str, Any]:
        elements: list[dict[str, Any]] = [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}
        ]
        if links:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": label},
                            "url": url,
                            "type": "primary" if index == 0 else "default",
                        }
                        for index, (label, url) in enumerate(links.items())
                    ],
                }
            )
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "template": template,
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": elements,
            },
        }

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        if self.secret:
            timestamp = int(time.time())
            body.update(
                {"timestamp": str(timestamp), "sign": self.signature(timestamp, self.secret)}
            )
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await self.http.post(self.webhook_url, json=body)
                data = cast(dict[str, Any], response.json())
                if response.status_code < 400 and data.get("code", data.get("StatusCode", 0)) == 0:
                    return data
                last_error = FeishuError(
                    f"飞书机器人返回失败，HTTP {response.status_code}, code={data.get('code')}"
                )
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
            if attempt + 1 < self.max_attempts:
                await self.sleep(min(0.25 * (2**attempt), 2.0))
        raise FeishuError("飞书机器人推送在有限重试后失败") from last_error

    async def close(self) -> None:
        await self.http.aclose()


class FeishuAppBotClient:
    """Send cards as the configured Feishu application bot to a group chat."""

    base_url = "https://open.feishu.cn/open-apis"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        chat_id: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not app_id or not app_secret:
            raise ValueError("飞书应用凭据不能为空")
        if not chat_id.startswith("oc_"):
            raise ValueError("飞书群 chat_id 无效")
        self.app_id = app_id
        self._app_secret = app_secret
        self.chat_id = chat_id
        self.http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=10, write=10, pool=5)
        )
        self.max_attempts = max(1, max_attempts)
        self.sleep = sleep

    async def send(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        token_payload = await self._post_json(
            "/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self._app_secret},
        )
        token = token_payload.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuError("飞书应用令牌响应缺少 tenant_access_token")
        msg_type = payload.get("msg_type")
        content = payload.get("card") if msg_type == "interactive" else payload.get("content")
        if not isinstance(msg_type, str) or not isinstance(content, dict):
            raise ValueError("飞书应用机器人消息结构无效")
        body: dict[str, Any] = {
            "receive_id": self.chat_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
        }
        if idempotency_key:
            body["uuid"] = idempotency_key[:50]
        return await self._post_json(
            "/im/v1/messages",
            body,
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            retryable_codes={230049},
        )

    async def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        retryable_codes: set[int] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            response: httpx.Response | None = None
            try:
                response = await self.http.post(
                    f"{self.base_url}{path}", params=params, headers=headers, json=body
                )
                data = cast(dict[str, Any], response.json())
                code = data.get("code", 0)
                if response.status_code < 400 and code in {0, None}:
                    return data
                retryable = (
                    response.status_code == 429
                    or response.status_code >= 500
                    or (isinstance(code, int) and code in (retryable_codes or set()))
                )
                error = FeishuError(
                    f"飞书应用机器人返回失败，HTTP {response.status_code}, code={code}"
                )
                if not retryable:
                    raise error
                last_error = error
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
            if attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After") if response is not None else None
                delay = float(retry_after) if retry_after else min(0.25 * (2**attempt), 2.0)
                await self.sleep(delay)
        raise FeishuError("飞书应用机器人推送在有限重试后失败") from last_error

    async def close(self) -> None:
        await self.http.aclose()
