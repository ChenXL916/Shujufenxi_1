from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.integrations.feishu.client import FeishuError
from app.integrations.feishu.oauth_store import FeishuReauthorizationRequired
from app.services.feishu_sync_service import sync_configured_sources

logger = logging.getLogger(__name__)
ACTIVE_STATUSES = frozenset({"queued", "running"})
STALE_AFTER = timedelta(minutes=15)


@dataclass
class ManualSyncJob:
    job_id: str
    status: str
    requested_at: datetime
    requested_by: str | None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: dict[str, Any] | None = None

    def public_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "requested_at": self.requested_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "result": self.result,
        }


class ManualSyncRegistry:
    """Process-local state for one manual sync on the single-worker API runtime."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, ManualSyncJob] = {}
        self._active_job_id: str | None = None

    def start(self, requested_by: str | None) -> tuple[dict[str, Any], bool]:
        now = datetime.now(UTC)
        with self._lock:
            active = self._jobs.get(self._active_job_id or "")
            if active and active.status in ACTIVE_STATUSES:
                if now - active.requested_at <= STALE_AFTER:
                    return active.public_payload(), False
                active.status = "failed"
                active.finished_at = now
                active.error = "上一次同步任务已超时，请重新同步"
            job = ManualSyncJob(
                job_id=str(uuid.uuid4()),
                status="queued",
                requested_at=now,
                requested_by=requested_by,
            )
            self._jobs[job.job_id] = job
            self._active_job_id = job.job_id
            self._prune()
            return job.public_payload(), True

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.started_at = datetime.now(UTC)

    def mark_completed(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            job.result = _public_result(result)
            job.error = None
            if self._active_job_id == job_id:
                self._active_job_id = None

    def mark_skipped(self, job_id: str, result: dict[str, Any]) -> None:
        reason = str(result.get("reason") or "同步任务被跳过")
        messages = {
            "lock-held": "已有同步任务正在运行，请稍后查看结果",
            "facts-lock-held": "数据汇总正在运行，请稍后重试",
        }
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "skipped"
            job.finished_at = datetime.now(UTC)
            job.result = _public_result(result)
            job.error = messages.get(reason, reason)
            if self._active_job_id == job_id:
                self._active_job_id = None

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.error = error
            if self._active_job_id == job_id:
                self._active_job_id = None

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.public_payload() if job else None

    def reset_for_testing(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._active_job_id = None

    def _prune(self) -> None:
        if len(self._jobs) <= 20:
            return
        completed = sorted(
            (job for job in self._jobs.values() if job.status not in ACTIVE_STATUSES),
            key=lambda item: item.requested_at,
        )
        for job in completed[: len(self._jobs) - 20]:
            self._jobs.pop(job.job_id, None)


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    sources = result.get("sources")
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "auth_mode": result.get("auth_mode"),
        "sources_synced": len(sources) if isinstance(sources, list) else 0,
        "hourly_facts": result.get("hourly_facts"),
    }


manual_sync_registry = ManualSyncRegistry()


async def run_manual_feishu_sync(job_id: str) -> None:
    manual_sync_registry.mark_running(job_id)
    try:
        result = await sync_configured_sources("live_actual")
        if result.get("status") == "skipped":
            manual_sync_registry.mark_skipped(job_id, result)
        else:
            manual_sync_registry.mark_completed(job_id, result)
    except FeishuReauthorizationRequired:
        manual_sync_registry.mark_failed(job_id, "飞书授权已失效，请重新授权后再同步")
    except FeishuError as exc:
        manual_sync_registry.mark_failed(job_id, str(exc) or "飞书数据读取失败")
    except Exception:
        logger.exception("Manual Feishu sync failed", extra={"job_id": job_id})
        manual_sync_registry.mark_failed(job_id, "同步服务异常，请稍后重试")
