from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    AlertAcknowledgeRequest,
    AlertRuleRequest,
    DetailResponse,
    FilterOptionsResponse,
    OverviewResponse,
    TimelineResponse,
)
from app.auth.dependencies import (
    Access,
    AlertRuleAccess,
    AlertViewAccess,
    DashboardAccess,
    ExportAccess,
    OperatorAccess,
)
from app.core.paths import project_root
from app.core.runtime_settings import load_runtime_settings
from app.db.session import get_db
from app.domain.metrics import MetricCatalog
from app.services.alert_service import AlertService
from app.services.analysis_service import AnalysisService
from app.services.dashboard_query_service import (
    DashboardFilters,
    DashboardQueryService,
)
from app.services.hourly_comparison_alert_service import HourlyComparisonAlertService
from app.services.permission_service import record_permission_audit

router = APIRouter(prefix="/api/v1")
DbSession = Annotated[Session, Depends(get_db)]
ROOT = project_root()
CATALOG = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")


def filters_from_query(
    start_date: date | None,
    end_date: date | None,
    room_ids: list[UUID] | None,
    anchor_names: list[str] | None,
    anchor_members: list[str] | None,
    control_names: list[str] | None,
    hour_slots: list[str] | None,
) -> DashboardFilters:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    return DashboardFilters(
        start_date=start_date,
        end_date=end_date,
        room_ids=tuple(room_ids or ()),
        anchor_names=tuple(anchor_names or ()),
        anchor_members=tuple(anchor_members or ()),
        control_names=tuple(control_names or ()),
        hour_slots=tuple(hour_slots or ()),
    )


@router.get("/filters/options", response_model=FilterOptionsResponse)
def filter_options(db: DbSession, access: DashboardAccess) -> FilterOptionsResponse:
    return DashboardQueryService(db, CATALOG, access).filter_options()


@router.get("/dashboard/overview", response_model=OverviewResponse)
def overview(
    db: DbSession,
    access: DashboardAccess,
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
) -> OverviewResponse:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    return DashboardQueryService(db, CATALOG, access).overview(filters)


@router.get("/charts/timeline", response_model=TimelineResponse)
def timeline(
    db: DbSession,
    access: DashboardAccess,
    grain: Literal["hour", "point"] = "hour",
    metric_keys: Annotated[list[str] | None, Query()] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
) -> TimelineResponse:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    return DashboardQueryService(db, CATALOG, access).timeline(
        filters, grain, tuple(metric_keys or ())
    )


@router.get("/hourly-facts/{fact_id}", response_model=DetailResponse)
def hourly_fact_detail(fact_id: UUID, db: DbSession, access: DashboardAccess) -> DetailResponse:
    try:
        return DashboardQueryService(db, CATALOG, access).hourly_detail(fact_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/live-points/{point_id}", response_model=DetailResponse)
def point_detail(point_id: UUID, db: DbSession, access: DashboardAccess) -> DetailResponse:
    try:
        return DashboardQueryService(db, CATALOG, access).point_detail(point_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/analytics/anchors/summary")
def anchor_summary(
    db: DbSession,
    access: DashboardAccess,
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
    metric_keys: Annotated[list[str] | None, Query()] = None,
) -> list[dict[str, object]]:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    return AnalysisService(db, CATALOG, access).summary("anchor", filters, tuple(metric_keys or ()))


@router.get("/analytics/controls/summary")
def control_summary(
    db: DbSession,
    access: DashboardAccess,
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
    metric_keys: Annotated[list[str] | None, Query()] = None,
) -> list[dict[str, object]]:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    return AnalysisService(db, CATALOG, access).summary(
        "control", filters, tuple(metric_keys or ())
    )


@router.get("/analytics/pairings")
def pairing_summary(
    db: DbSession,
    access: DashboardAccess,
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
    metric_keys: Annotated[list[str] | None, Query()] = None,
) -> list[dict[str, object]]:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    return AnalysisService(db, CATALOG, access).summary(
        "pairing", filters, tuple(metric_keys or ())
    )


@router.get("/comparisons")
def comparisons(
    db: DbSession,
    access: DashboardAccess,
    comparison_type: Literal["previous_day", "previous_week", "previous_month"] = "previous_day",
    metric_keys: Annotated[list[str] | None, Query()] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
) -> list[dict[str, object]]:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    metrics = tuple(metric_keys or ("period_overall_amount", "period_spend", "period_overall_roi"))
    return AnalysisService(db, CATALOG, access).comparisons(filters, comparison_type, metrics)


@router.get("/pivot/anchor-control")
def anchor_control_pivot(
    db: DbSession,
    access: DashboardAccess,
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
) -> list[dict[str, object]]:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    return AnalysisService(db, CATALOG, access).pivot(filters)


@router.post("/exports")
def export_data(
    db: DbSession,
    access: ExportAccess,
    request: Request,
    file_format: Literal["csv", "xlsx"] = "xlsx",
    start_date: date | None = None,
    end_date: date | None = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
) -> Response:
    filters = filters_from_query(
        start_date, end_date, room_ids, anchor_names, anchor_members, control_names, hour_slots
    )
    access.assert_rooms(filters.room_ids)
    try:
        content, media_type, filename = AnalysisService(db, CATALOG, access).export_pivot(
            filters, file_format
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="sensitive_data_export",
        target_type="dashboard_export",
        target_id=filename,
        after_value={
            "format": file_format,
            "requested_room_ids": [str(item) for item in filters.room_ids],
            "scope": access.scope_label,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/alerts/events")
def alert_events(
    db: DbSession,
    access: AlertViewAccess,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    hour_slots: Annotated[list[str] | None, Query()] = None,
    period_days: Annotated[list[int] | None, Query()] = None,
    notification_types: Annotated[list[str] | None, Query()] = None,
    alert_types: Annotated[list[str] | None, Query()] = None,
    pushed: bool | None = None,
    acknowledged: bool | None = None,
) -> list[dict[str, object]]:
    access.assert_rooms(tuple(room_ids or ()))
    return AlertService(db, load_runtime_settings(db), access.room_ids).list_events(
        room_ids=tuple(room_ids or ()),
        anchor_names=tuple(anchor_names or ()),
        control_names=tuple(control_names or ()),
        hour_slots=tuple(hour_slots or ()),
        period_days=tuple(period_days or ()),
        notification_types=tuple(notification_types or ()),
        alert_types=tuple(alert_types or ()),
        pushed=pushed,
        acknowledged=acknowledged,
    )


@router.get("/alerts/events/{event_id}")
def alert_event(event_id: UUID, db: DbSession, access: AlertViewAccess) -> dict[str, object]:
    try:
        return AlertService(db, load_runtime_settings(db), access.room_ids).get_event(event_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/alerts/events/{event_id}/acknowledge")
def acknowledge_alert(
    event_id: UUID, payload: AlertAcknowledgeRequest, db: DbSession, access: OperatorAccess
) -> dict[str, object]:
    try:
        event = AlertService(db, load_runtime_settings(db), access.room_ids).acknowledge(
            event_id, payload.resolution_note, access.user_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": str(event.id), "acknowledged": True}


@router.post("/alerts/events/{event_id}/retry-push")
async def retry_alert_push(
    event_id: UUID, db: DbSession, access: OperatorAccess
) -> dict[str, object]:
    try:
        return await AlertService(db, load_runtime_settings(db), access.room_ids).push_event(
            event_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/alerts/evaluate")
async def evaluate_alerts(db: DbSession, access: OperatorAccess) -> dict[str, int]:
    settings = load_runtime_settings(db)
    alert_service = AlertService(db, settings, access.room_ids)
    legacy = await alert_service.evaluate_recent_and_push()
    hourly_event_ids = HourlyComparisonAlertService(
        db,
        settings,
        CATALOG,
        access.room_ids,
    ).evaluate_due_event_ids()
    anchor = await alert_service.push_events(hourly_event_ids)
    return {
        "queued": legacy["queued"] + anchor["queued"],
        "sent": legacy["sent"] + anchor["sent"],
        "failed": legacy["failed"] + anchor["failed"],
        "skipped": legacy["skipped"] + anchor["skipped"],
        "legacy_queued": legacy["queued"],
        "anchor_queued": anchor["queued"],
    }


@router.post("/alerts/test-push")
async def test_alert_push(db: DbSession, access: OperatorAccess) -> dict[str, Any]:
    return await AlertService(db, load_runtime_settings(db)).push_test_card()


@router.get("/alerts/rules")
def alert_rules(db: DbSession, access: AlertRuleAccess) -> list[dict[str, object]]:
    return AlertService(db, load_runtime_settings(db)).list_rules()


@router.post("/alerts/rules", status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleRequest, db: DbSession, access: AlertRuleAccess
) -> dict[str, object]:
    return AlertService(db, load_runtime_settings(db)).create_rule(
        payload.model_dump(), access.user_id
    )


@router.patch("/alerts/rules/{rule_id}")
def update_alert_rule(
    rule_id: UUID, payload: AlertRuleRequest, db: DbSession, access: AlertRuleAccess
) -> dict[str, object]:
    try:
        return AlertService(db, load_runtime_settings(db)).update_rule(
            rule_id, payload.model_dump()
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/alerts/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(rule_id: UUID, db: DbSession, access: AlertRuleAccess) -> Response:
    try:
        AlertService(db, load_runtime_settings(db)).delete_rule(rule_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
def me(access: Access) -> dict[str, str]:
    return {"name": "开发管理员", "role": access.role, "auth_mode": "development_bypass"}
