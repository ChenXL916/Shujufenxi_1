from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.integrations.feishu.client import FeishuBitableClient, FeishuPermissionError

pytestmark = pytest.mark.integration


def client_for(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> FeishuBitableClient:
    kwargs: dict[str, object] = {
        "http_client": httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=FeishuBitableClient.base_url
        )
    }
    if sleep is not None:
        kwargs["sleep"] = sleep
    return FeishuBitableClient("app-id", "app-secret", **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_token_is_cached_and_records_are_paginated() -> None:
    calls = {"token": 0, "records": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            calls["token"] += 1
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "tenant", "expire": 7200}
            )
        calls["records"] += 1
        if request.url.params.get("page_token") is None:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"items": [{"record_id": "1"}], "has_more": True, "page_token": "next"},
                },
            )
        return httpx.Response(
            200,
            json={"code": 0, "data": {"items": [{"record_id": "2"}], "has_more": False}},
        )

    client = client_for(handler)
    records = await client.list_records("app-token", "table-id")
    await client.get_tenant_access_token()
    await client.close()

    assert [record["record_id"] for record in records] == ["1", "2"]
    assert calls == {"token": 1, "records": 2}


@pytest.mark.asyncio
async def test_429_and_5xx_are_retried_with_finite_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    async def no_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "tenant", "expire": 7200}
            )
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        if attempts == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})

    client = client_for(handler, sleep=no_sleep)
    assert await client.list_records("app-token", "table-id") == []
    await client.close()

    assert attempts == 3
    assert delays == [0.0, 0.5]


@pytest.mark.asyncio
async def test_permission_failure_is_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "tenant", "expire": 7200}
            )
        return httpx.Response(403)

    client = client_for(handler)
    with pytest.raises(FeishuPermissionError, match="权限不足"):
        await client.list_fields("app-token", "table-id")
    await client.close()


@pytest.mark.asyncio
async def test_user_access_token_skips_tenant_token_exchange() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer user-access"
        return httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=FeishuBitableClient.base_url
    )
    client = FeishuBitableClient(
        "app-id",
        "app-secret",
        access_token="user-access",  # noqa: S106
        http_client=http,
    )
    assert client.uses_user_access_token is True
    assert await client.list_records("app-token", "table-id") == []
    await client.close()
    assert paths == ["/open-apis/bitable/v1/apps/app-token/tables/table-id/records"]
