from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import cast

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings


@dataclass
class _Attempt:
    failures: int
    expires_at: float


class LoginAttemptLimiter:
    max_failures = 5
    window_seconds = 5 * 60

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts: dict[str, _Attempt] = {}

    @staticmethod
    def _key(ip_address: str, username: str) -> str:
        digest = hashlib.sha256(f"{ip_address}\0{username}".encode()).hexdigest()
        return f"live-ops:password-login:{digest}"

    def _redis(self, settings: Settings) -> Redis:
        return Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )

    def is_blocked(self, settings: Settings, ip_address: str, username: str) -> bool:
        key = self._key(ip_address, username)
        client: Redis | None = None
        try:
            client = self._redis(settings)
            value = cast(bytes | str | int | None, client.get(key))
            self._memory_clear(key)
            return bool(value is not None and int(value) >= self.max_failures)
        except (RedisError, ValueError):
            return self._memory_is_blocked(key)
        finally:
            if client is not None:
                client.close()

    def record_failure(self, settings: Settings, ip_address: str, username: str) -> None:
        key = self._key(ip_address, username)
        client: Redis | None = None
        try:
            client = self._redis(settings)
            pipeline = client.pipeline(transaction=True)
            pipeline.incr(key)
            pipeline.expire(key, self.window_seconds)
            pipeline.execute()
            self._memory_clear(key)
        except RedisError:
            self._memory_record_failure(key)
        finally:
            if client is not None:
                client.close()

    def clear(self, settings: Settings, ip_address: str, username: str) -> None:
        key = self._key(ip_address, username)
        client: Redis | None = None
        try:
            client = self._redis(settings)
            client.delete(key)
        except RedisError:
            self._memory_clear(key)
        finally:
            self._memory_clear(key)
            if client is not None:
                client.close()

    def reset_for_testing(self) -> None:
        with self._lock:
            self._attempts.clear()

    def _memory_is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempt = self._attempts.get(key)
            if attempt is None:
                return False
            if attempt.expires_at <= now:
                self._attempts.pop(key, None)
                return False
            return attempt.failures >= self.max_failures

    def _memory_record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            attempt = self._attempts.get(key)
            failures = 1 if attempt is None or attempt.expires_at <= now else attempt.failures + 1
            self._attempts[key] = _Attempt(failures, now + self.window_seconds)

    def _memory_clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()
