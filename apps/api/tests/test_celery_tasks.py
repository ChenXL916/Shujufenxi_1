import time

import pytest
from redis import RedisError

from app.core import distributed_lock as lock_module
from app.tasks import jobs
from app.tasks.celery_app import celery_app


def test_all_beat_tasks_are_registered_by_worker_loader() -> None:
    celery_app.loader.import_default_modules()

    beat_task_names = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    missing = beat_task_names.difference(celery_app.tasks)

    assert missing == set()


def test_locked_job_fails_closed_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableRedis:
        def set(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RedisError("redis unavailable")

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        lock_module.redis.Redis,
        "from_url",
        lambda *args, **kwargs: UnavailableRedis(),
    )
    invoked = False

    def operation() -> str:
        nonlocal invoked
        invoked = True
        return "unexpected"

    with pytest.raises(RedisError, match="redis unavailable"):
        jobs.locked_job("fail-closed", operation)

    assert invoked is False


def test_fact_rebuild_tasks_share_resource_lock_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_names: list[str] = []

    def record_lock(name: str, function):  # type: ignore[no-untyped-def]
        lock_names.append(name)
        return function()

    monkeypatch.setattr(jobs, "locked_job", record_lock)
    monkeypatch.setattr(
        jobs,
        "_rebuild_facts",
        lambda: {"status": "completed", "facts": 0},
    )

    assert jobs.build_hourly_facts()["status"] == "completed"
    assert jobs.reconcile_schedule_matches()["status"] == "completed"
    assert lock_names == ["facts-rebuild", "facts-rebuild"]


def test_distributed_lock_renews_lease_and_releases_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_scripts: list[str] = []

    class RenewableRedis:
        token: str | None = None

        def set(self, _key: str, token: str, *args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
            self.token = token
            return True

        def get(self, _key: str) -> str | None:
            return self.token

        def eval(self, script: str, *args, **kwargs) -> int:  # type: ignore[no-untyped-def]
            eval_scripts.append(script)
            return 1

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        lock_module.redis.Redis,
        "from_url",
        lambda *args, **kwargs: RenewableRedis(),
    )

    with lock_module.distributed_lock("renewable", ttl_seconds=1) as acquired:
        assert acquired is not None
        acquired.assert_owned()
        time.sleep(0.45)

    assert any("expire" in script.lower() for script in eval_scripts)
    assert any("del" in script.lower() for script in eval_scripts)


def test_distributed_lock_rejects_replaced_owner_before_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReplacedOwnerRedis:
        def set(self, *args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
            return True

        def get(self, _key: str) -> str:
            return "different-owner"

        def eval(self, *args, **kwargs) -> int:  # type: ignore[no-untyped-def]
            return 0

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        lock_module.redis.Redis,
        "from_url",
        lambda *args, **kwargs: ReplacedOwnerRedis(),
    )

    with (
        pytest.raises(RedisError, match="lease lost"),
        lock_module.distributed_lock("replaced-owner") as acquired,
    ):
        assert acquired is not None
