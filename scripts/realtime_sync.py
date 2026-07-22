from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.auth.dependencies import AccessScope  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.paths import project_root  # noqa: E402
from app.core.runtime_settings import load_runtime_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.metrics import MetricCatalog  # noqa: E402
from app.services.alert_service import AlertService  # noqa: E402
from app.services.anchor_trend_service import AnchorTrendService  # noqa: E402
from app.services.feishu_sync_service import sync_configured_sources  # noqa: E402
from app.services.hourly_comparison_alert_service import (  # noqa: E402
    HourlyComparisonAlertService,
)

CATALOG = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")


async def run_forever() -> None:
    last_schedule_sync: float | None = None
    while True:
        started = time.monotonic()
        reports: dict[str, object] = {}
        try:
            reports["live_actual"] = await sync_configured_sources("live_actual")
        except Exception as exc:
            reports["live_actual"] = {"status": "waiting", "reason": str(exc)}
        settings = get_settings()
        try:
            with get_session_factory()() as session:
                settings = load_runtime_settings(session)
                alert_service = AlertService(session, settings)
                reports["alert_retries"] = await alert_service.push_queued_events()
                reports["legacy_alerts"] = await alert_service.evaluate_recent_and_push()
                hourly_event_ids = HourlyComparisonAlertService(
                    session,
                    settings,
                    CATALOG,
                ).evaluate_due_event_ids()
                reports["anchor_hourly_alerts"] = await alert_service.push_events(hourly_event_ids)
                trend_service = AnchorTrendService(
                    session,
                    CATALOG,
                    AccessScope(
                        user_id=None,
                        role="admin",
                        room_ids=None,
                        can_export=True,
                    ),
                    settings,
                )
                due_trend_rules = trend_service.due_rules()
                reports["anchor_trend_summaries"] = [
                    await trend_service.run_rule(rule) for rule in due_trend_rules
                ]
        except Exception as exc:
            reports["alerts"] = {"status": "waiting", "reason": str(exc)}
        schedule_interval = max(60, settings.schedule_sync_interval_minutes * 60)
        if last_schedule_sync is None or started - last_schedule_sync >= schedule_interval:
            try:
                reports["schedules"] = await sync_configured_sources("anchor_schedule")
                last_schedule_sync = time.monotonic()
            except Exception as exc:
                reports["schedules"] = {"status": "waiting", "reason": str(exc)}
        print(json.dumps(reports, ensure_ascii=False, default=str), flush=True)
        interval = max(60, settings.live_sync_interval_minutes * 60)
        await asyncio.sleep(max(1, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    asyncio.run(run_forever())
