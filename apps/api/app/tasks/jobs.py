from __future__ import annotations

# mypy: disable-error-code=untyped-decorator
import asyncio
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult

from app.auth.dependencies import AccessScope
from app.core.config import get_settings
from app.core.distributed_lock import locked_job
from app.core.paths import project_root
from app.core.runtime_settings import load_runtime_settings
from app.db.base import utc_now
from app.db.session import get_session_factory
from app.domain.metrics import MetricCatalog
from app.models.entities import HourlyFact, SyncRun
from app.services.alert_service import AlertService
from app.services.anchor_trend_service import AnchorTrendService
from app.services.feishu_sync_service import sync_configured_sources
from app.services.hourly_comparison_alert_service import HourlyComparisonAlertService
from app.services.hourly_fact_service import HourlyFactService
from app.tasks.celery_app import celery_app

ROOT = project_root()


def _source_mode(source: str) -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ready",
        "source": source,
        "mode": "feishu" if settings.feishu_credentials_configured else "fixture_mock",
    }


@celery_app.task(name="app.tasks.jobs.sync_live_actual")
def sync_live_actual() -> dict[str, Any]:
    return asyncio.run(sync_configured_sources("live_actual"))


@celery_app.task(name="app.tasks.jobs.sync_schedules")
def sync_schedules() -> dict[str, Any]:
    return asyncio.run(sync_configured_sources("anchor_schedule"))


@celery_app.task(name="app.tasks.jobs.build_hourly_facts")
def build_hourly_facts() -> dict[str, Any]:
    return locked_job("facts-rebuild", _rebuild_facts)


def _rebuild_facts() -> dict[str, Any]:
    catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
    with get_session_factory()() as session:
        count = HourlyFactService(session, catalog).rebuild()
    return {"status": "completed", "facts": count}


@celery_app.task(name="app.tasks.jobs.evaluate_alerts")
def evaluate_alerts() -> dict[str, Any]:
    async def run() -> dict[str, int]:
        with get_session_factory()() as session:
            settings = load_runtime_settings(session)
            legacy = await AlertService(session, settings).evaluate_recent_and_push()
            catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
            hourly = await HourlyComparisonAlertService(
                session, settings, catalog
            ).evaluate_due_and_push()
            return {
                **legacy,
                **{f"hourly_comparison_{key}": value for key, value in hourly.items()},
            }

    return locked_job("evaluate-alerts", lambda: asyncio.run(run()))


@celery_app.task(name="app.tasks.jobs.anchor_trend_summary_job")
def anchor_trend_summary_job() -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        with get_session_factory()() as session:
            settings = load_runtime_settings(session)
            catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
            service = AnchorTrendService(
                session,
                catalog,
                AccessScope(
                    user_id=None,
                    role="admin",
                    room_ids=None,
                    can_export=True,
                ),
                settings,
            )
            rules = service.due_rules()
            results = [await service.run_rule(rule) for rule in rules]
            return {
                "status": "completed",
                "due_rules": len(rules),
                "events": sum(len(result["calculation"]["event_ids"]) for result in results),
                "sent": sum(
                    item.get("push_status") == "sent"
                    for result in results
                    for item in result["sent"]
                ),
                "skipped": sum(
                    item.get("push_status") == "skipped"
                    for result in results
                    for item in result["sent"]
                ),
            }

    return locked_job(
        "anchor-trend-summary",
        lambda: asyncio.run(run()),
    )


@celery_app.task(name="app.tasks.jobs.retry_failed_pushes")
def retry_failed_pushes() -> dict[str, Any]:
    async def run_pushes() -> dict[str, int]:
        with get_session_factory()() as session:
            return await AlertService(
                session,
                load_runtime_settings(session),
            ).push_queued_events()

    return locked_job(
        "retry-failed-pushes",
        lambda: {"status": "completed", **asyncio.run(run_pushes())},
    )


@celery_app.task(name="app.tasks.jobs.health_check_sources")
def health_check_sources() -> dict[str, str]:
    return locked_job("health-check-sources", lambda: _source_mode("all"))


@celery_app.task(name="app.tasks.jobs.cleanup_old_sync_runs")
def cleanup_old_sync_runs() -> dict[str, Any]:
    def run() -> dict[str, Any]:
        cutoff = utc_now() - timedelta(days=30)
        with get_session_factory()() as session:
            result = cast(
                CursorResult[Any],
                session.execute(delete(SyncRun).where(SyncRun.started_at < cutoff)),
            )
            session.commit()
            return {"status": "completed", "deleted": result.rowcount}

    return locked_job("cleanup-old-sync-runs", run)


@celery_app.task(name="app.tasks.jobs.refresh_daily_summary")
def refresh_daily_summary() -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with get_session_factory()() as session:
            count = session.scalar(select(func.count()).select_from(HourlyFact)) or 0
        return {"status": "completed", "hourly_facts": count}

    return locked_job("refresh-daily-summary", run)


@celery_app.task(name="app.tasks.jobs.reconcile_schedule_matches")
def reconcile_schedule_matches() -> dict[str, Any]:
    return locked_job("facts-rebuild", _rebuild_facts)
