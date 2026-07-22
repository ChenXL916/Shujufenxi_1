from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T")

RENEW_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class DistributedLease:
    def __init__(
        self,
        *,
        name: str,
        client: Any,
        key: str,
        token: str,
        lease_lost: threading.Event,
    ) -> None:
        self.name = name
        self._client = client
        self._key = key
        self._token = token
        self._lease_lost = lease_lost

    def assert_owned(self) -> None:
        if self._lease_lost.is_set() or self._client.get(self._key) != self._token:
            self._lease_lost.set()
            raise redis.RedisError(f"distributed lock lease lost: {self.name}")


def lock_key(name: str) -> str:
    return f"live-ops:{get_settings().app_env}:lock:{name}"


def _renew_lock_lease(
    client: Any,
    key: str,
    token: str,
    ttl_seconds: int,
    stop: threading.Event,
    lease_lost: threading.Event,
) -> None:
    interval = max(ttl_seconds / 3, 0.1)
    while not stop.wait(interval):
        try:
            renewed = client.eval(RENEW_LOCK_SCRIPT, 1, key, token, ttl_seconds)
        except redis.RedisError:
            logger.exception("Redis lock lease renewal failed for %s", key)
            lease_lost.set()
            return
        if not renewed:
            logger.error("Redis lock lease ownership was lost for %s", key)
            lease_lost.set()
            return


@contextmanager
def distributed_lock(name: str, ttl_seconds: int = 240) -> Iterator[DistributedLease | None]:
    """Acquire a fail-closed Redis lease for a shared business resource."""
    client = redis.Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    key = lock_key(name)
    token = uuid.uuid4().hex
    acquired = False
    stop = threading.Event()
    lease_lost = threading.Event()
    renewer: threading.Thread | None = None
    lease: DistributedLease | None = None
    try:
        acquired = bool(client.set(key, token, nx=True, ex=ttl_seconds))
        if acquired:
            lease = DistributedLease(
                name=name,
                client=client,
                key=key,
                token=token,
                lease_lost=lease_lost,
            )
            renewer = threading.Thread(
                target=_renew_lock_lease,
                args=(client, key, token, ttl_seconds, stop, lease_lost),
                name=f"redis-lock-renew-{name}",
                daemon=True,
            )
            renewer.start()
        yield lease
        if lease is not None:
            lease.assert_owned()
    except redis.RedisError:
        raise
    finally:
        stop.set()
        if renewer is not None:
            renewer.join(timeout=1)
        if acquired:
            try:
                client.eval(RELEASE_LOCK_SCRIPT, 1, key, token)
            except redis.RedisError:
                logger.exception("Redis lock release failed for %s", key)
        try:
            client.close()
        except redis.RedisError:
            logger.exception("Redis lock client close failed for %s", key)


def locked_job(  # noqa: UP047 - keep Python 3.11 tooling compatibility
    name: str, function: Callable[[], T]
) -> T | dict[str, str]:
    with distributed_lock(name) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "lock-held"}
        return function()
