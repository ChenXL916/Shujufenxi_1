from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    HourlyComparisonDetailsResponse,
    HourlyComparisonResponse,
    HourlyComparisonRulePayload,
    HourlyComparisonRuleRequest,
    RoomMetricTargetPayload,
    RoomMetricTargetRequest,
)
from app.auth.dependencies import (
    AlertRuleAccess,
    DashboardAccess,
    ExportAccess,
    RoiTargetAccess,
)
from app.core.paths import project_root
from app.db.session import get_db
from app.domain.metrics import MetricCatalog
from app.services.hourly_comparison_service import (
    HourlyComparisonFilters,
    HourlyComparisonService,
)
from app.services.permission_service import record_permission_audit

router = APIRouter(prefix="/api/v1")
DbSession = Annotated[Session, Depends(get_db)]
CATALOG = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")


def comparison_filters(
    end_date: date | None = None,
    period_days: int = 7,
    custom_start_date: date | None = None,
    custom_end_date: date | None = None,
    compare_enabled: bool = True,
    aggregation_mode: Literal["sum", "daily_average"] = "sum",
    chart_type: Literal["line", "business_kline", "bar"] = "line",
    metric_ids: Annotated[list[str] | None, Query()] = None,
    room_ids: Annotated[list[UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    anchor_ids: Annotated[list[str] | None, Query()] = None,
    anchor_members: Annotated[list[str] | None, Query()] = None,
    anchor_member_ids: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    controller_ids: Annotated[list[str] | None, Query()] = None,
    natural_hours: Annotated[list[str] | None, Query()] = None,
    series_dimension: Literal["summary", "room", "anchor", "controller", "room_anchor"] = "summary",
    include_today: bool = False,
    include_in_progress: bool = True,
    show_range_band: bool = False,
) -> HourlyComparisonFilters:
    return HourlyComparisonFilters(
        end_date=end_date,
        period_days=period_days,
        custom_start_date=custom_start_date,
        custom_end_date=custom_end_date,
        compare_enabled=compare_enabled,
        aggregation_mode=aggregation_mode,
        chart_type=chart_type,
        metric_ids=tuple(metric_ids or ("period_overall_roi", "period_spend")),
        room_ids=tuple(room_ids or ()),
        anchor_names=tuple(anchor_names or anchor_ids or ()),
        anchor_members=tuple(anchor_members or anchor_member_ids or ()),
        control_names=tuple(control_names or controller_ids or ()),
        natural_hours=tuple(natural_hours or ()),
        series_dimension=series_dimension,
        include_today=include_today,
        include_in_progress=include_in_progress,
        show_range_band=show_range_band,
    )


ComparisonFilters = Annotated[HourlyComparisonFilters, Depends(comparison_filters)]


@router.get(
    "/overview/hourly-comparison",
    response_model=HourlyComparisonResponse,
)
def hourly_comparison(
    db: DbSession, access: DashboardAccess, filters: ComparisonFilters
) -> HourlyComparisonResponse:
    access.assert_rooms(filters.room_ids)
    try:
        return HourlyComparisonService(db, CATALOG, access).compare(filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/overview/hourly-comparison/details",
    response_model=HourlyComparisonDetailsResponse,
)
def hourly_comparison_details(
    natural_hour: str,
    db: DbSession,
    access: DashboardAccess,
    filters: ComparisonFilters,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> HourlyComparisonDetailsResponse:
    access.assert_rooms(filters.room_ids)
    try:
        return HourlyComparisonService(db, CATALOG, access).details(
            filters,
            natural_hour,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/overview/hourly-comparison/export")
def export_hourly_comparison(
    db: DbSession,
    access: ExportAccess,
    request: Request,
    filters: ComparisonFilters,
) -> Response:
    access.assert_rooms(filters.room_ids)
    try:
        content, filename = HourlyComparisonService(db, CATALOG, access).export_csv(filters)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="sensitive_data_export",
        target_type="hourly_comparison_export",
        target_id=filename,
        after_value={
            "format": "csv",
            "requested_room_ids": [str(item) for item in filters.room_ids],
            "scope": access.scope_label,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/settings/room-metric-targets",
    response_model=list[RoomMetricTargetPayload],
)
def room_metric_targets(db: DbSession, access: RoiTargetAccess) -> list[RoomMetricTargetPayload]:
    return HourlyComparisonService(db, CATALOG, access).list_targets()


@router.post(
    "/settings/room-metric-targets",
    response_model=RoomMetricTargetPayload,
    status_code=status.HTTP_201_CREATED,
)
def create_room_metric_target(
    payload: RoomMetricTargetRequest,
    db: DbSession,
    access: RoiTargetAccess,
) -> RoomMetricTargetPayload:
    try:
        return HourlyComparisonService(db, CATALOG, access).create_target(payload, access.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put(
    "/settings/room-metric-targets/{target_id}",
    response_model=RoomMetricTargetPayload,
)
def update_room_metric_target(
    target_id: UUID,
    payload: RoomMetricTargetRequest,
    db: DbSession,
    access: RoiTargetAccess,
) -> RoomMetricTargetPayload:
    try:
        return HourlyComparisonService(db, CATALOG, access).update_target(
            target_id, payload, access.user_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/settings/hourly-comparison-rules",
    response_model=list[HourlyComparisonRulePayload],
)
def hourly_comparison_rules(
    db: DbSession, access: AlertRuleAccess
) -> list[HourlyComparisonRulePayload]:
    return HourlyComparisonService(db, CATALOG, access).list_rules()


@router.post(
    "/settings/hourly-comparison-rules",
    response_model=HourlyComparisonRulePayload,
    status_code=status.HTTP_201_CREATED,
)
def create_hourly_comparison_rule(
    payload: HourlyComparisonRuleRequest,
    db: DbSession,
    access: AlertRuleAccess,
) -> HourlyComparisonRulePayload:
    try:
        return HourlyComparisonService(db, CATALOG, access).create_rule(payload, access.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put(
    "/settings/hourly-comparison-rules/{rule_id}",
    response_model=HourlyComparisonRulePayload,
)
def update_hourly_comparison_rule(
    rule_id: UUID,
    payload: HourlyComparisonRuleRequest,
    db: DbSession,
    access: AlertRuleAccess,
) -> HourlyComparisonRulePayload:
    try:
        return HourlyComparisonService(db, CATALOG, access).update_rule(
            rule_id, payload, access.user_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
