from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class FeishuError(RuntimeError):
    """Base error that never contains credentials."""


class FeishuPermissionError(FeishuError):
    """Raised for non-retryable Feishu authorization failures."""


class TokenCache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class MemoryTokenCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[str, float]] = {}

    async def get(self, key: str) -> str | None:
        value = self._items.get(key)
        if value is None or value[1] <= time.monotonic():
            return None
        return value[0]

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._items[key] = (value, time.monotonic() + ttl_seconds)


class RedisTokenCache:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def get(self, key: str) -> str | None:
        value = await self.redis.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self.redis.set(key, value, ex=ttl_seconds)


@dataclass(frozen=True)
class FeishuHealth:
    ok: bool
    tables: int
    fields: int
    latency_ms: int


class FeishuBitableClient:
    base_url = "https://open.feishu.cn/open-apis"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        cache: TokenCache | None = None,
        access_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        max_attempts: int = 4,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not app_id or not app_secret:
            raise ValueError("Feishu app_id 与 app_secret 均不能为空")
        self.app_id = app_id
        self._app_secret = app_secret
        self._access_token = access_token
        self.cache = cache or MemoryTokenCache()
        self.http = http_client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=5, read=15, write=10, pool=5),
        )
        self.max_attempts = max_attempts
        self.sleep = sleep

    @property
    def uses_user_access_token(self) -> bool:
        return self._access_token is not None

    async def close(self) -> None:
        await self.http.aclose()

    async def get_tenant_access_token(self) -> str:
        cache_key = f"feishu:tenant-token:{self.app_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        response = await self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self._app_secret},
            authenticated=False,
        )
        payload = self._payload(response)
        token = payload.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuError("飞书令牌响应缺少 tenant_access_token")
        expire = int(payload.get("expire", 7200))
        await self.cache.set(cache_key, token, max(60, expire - 300))
        return token

    async def list_tables(self, app_token: str) -> list[dict[str, Any]]:
        payload = await self._authorized_json(
            "GET", f"/bitable/v1/apps/{app_token}/tables", params={"page_size": 100}
        )
        return self._items(payload)

    async def list_fields(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, str | int] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            payload = await self._authorized_json(
                "GET",
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                params=params,
            )
            data = self._data(payload)
            items.extend(self._items(payload))
            if not data.get("has_more"):
                return items
            page_token = cast(str | None, data.get("page_token"))

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        view_id: str | None = None,
        page_token: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        current_token = page_token
        while True:
            params: dict[str, str | int] = {"page_size": 500}
            if view_id:
                params["view_id"] = view_id
            if current_token:
                params["page_token"] = current_token
            payload = await self._authorized_json(
                "GET",
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )
            data = self._data(payload)
            page_items = self._items(payload)
            items.extend(page_items)
            logger.info(
                "feishu_records_page",
                extra={"record_count": len(page_items), "has_more": bool(data.get("has_more"))},
            )
            if not data.get("has_more"):
                return items
            current_token = cast(str | None, data.get("page_token"))

    async def health_check_source(self, app_token: str, table_id: str) -> FeishuHealth:
        started = time.perf_counter()
        tables = await self.list_tables(app_token)
        fields = await self.list_fields(app_token, table_id)
        return FeishuHealth(
            ok=True,
            tables=len(tables),
            fields=len(fields),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    async def _authorized_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token or await self.get_tenant_access_token()
        response = await self._request(
            method,
            path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            authenticated=True,
        )
        return self._payload(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool,
        params: dict[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
        json: dict[str, str] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            started = time.perf_counter()
            try:
                response = await self.http.request(
                    method, path, params=params, headers=headers, json=json
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                response = None
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            status = response.status_code if response is not None else 0
            logger.info(
                "feishu_request",
                extra={
                    "path": path,
                    "status": status,
                    "latency_ms": elapsed_ms,
                    "request_id": response.headers.get("x-tt-logid", "")
                    if response is not None
                    else "",
                    "attempt": attempt + 1,
                },
            )
            if response is not None:
                if response.status_code in {401, 403} and authenticated:
                    raise FeishuPermissionError("飞书数据源权限不足，请检查应用权限与 Base 授权")
                if response.status_code < 400:
                    return response
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise FeishuError(f"飞书请求失败，HTTP {response.status_code}")
                last_error = FeishuError(f"飞书临时错误，HTTP {response.status_code}")
            if attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After") if response is not None else None
                delay = float(retry_after) if retry_after else min(0.25 * (2**attempt), 4.0)
                await self.sleep(delay)
        raise FeishuError("飞书请求在有限重试后仍失败") from last_error

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        payload = cast(dict[str, Any], response.json())
        code = payload.get("code", 0)
        if code not in {0, None}:
            raise FeishuError(f"飞书业务错误 code={code}")
        return payload

    @staticmethod
    def _data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data", {})
        return cast(dict[str, Any], data) if isinstance(data, dict) else {}

    @classmethod
    def _items(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = cls._data(payload).get("items", [])
        if not isinstance(items, list):
            return []
        return [cast(dict[str, Any], item) for item in items if isinstance(item, dict)]
