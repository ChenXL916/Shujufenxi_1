from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "live_ops",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.jobs"],
)
celery_app.conf.update(
    timezone=settings.timezone,
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "sync-live-actual": {
            "task": "app.tasks.jobs.sync_live_actual",
            "schedule": settings.live_sync_interval_minutes * 60,
        },
        "sync-schedules": {
            "task": "app.tasks.jobs.sync_schedules",
            "schedule": settings.schedule_sync_interval_minutes * 60,
        },
        "build-hourly-facts": {
            "task": "app.tasks.jobs.build_hourly_facts",
            "schedule": settings.live_sync_interval_minutes * 60,
        },
        "evaluate-alerts": {
            "task": "app.tasks.jobs.evaluate_alerts",
            "schedule": settings.live_sync_interval_minutes * 60,
        },
        "anchor-trend-summary": {
            "task": "app.tasks.jobs.anchor_trend_summary_job",
            "schedule": 300,
        },
        "retry-failed-pushes": {
            "task": "app.tasks.jobs.retry_failed_pushes",
            "schedule": 300,
        },
        "health-check-sources": {
            "task": "app.tasks.jobs.health_check_sources",
            "schedule": 900,
        },
        "cleanup-old-sync-runs": {
            "task": "app.tasks.jobs.cleanup_old_sync_runs",
            "schedule": 86400,
        },
        "refresh-daily-summary": {
            "task": "app.tasks.jobs.refresh_daily_summary",
            "schedule": 3600,
        },
        "reconcile-schedule-matches": {
            "task": "app.tasks.jobs.reconcile_schedule_matches",
            "schedule": 1800,
        },
    },
)
