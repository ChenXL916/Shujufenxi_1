from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    AnchorTrendEventDetailsResponse,
    AnchorTrendListResponse,
    AnchorTrendPushResponse,
    AnchorTrendRecalculateRequest,
    AnchorTrendRecalculateResponse,
    AnchorTrendSendRequest,
    AnchorTrendTestRequest,
)
from app.auth.dependencies import AlertViewAccess, OperatorAccess
from app.core.paths import project_root
from app.core.runtime_settings import load_runtime_settings
from app.db.session import get_db
from app.domain.metrics import MetricCatalog
from app.integrations.feishu.bot import FeishuBotClient
from app.services.alert_service import AlertService
from app.services.anchor_trend_service import AnchorTrendService

router = APIRouter(prefix="/api/v1")
DbSession = Annotated[Session, Depends(get_db)]
CATALOG = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")


@router.get("/alerts/anchor-trends", response_model=AnchorTrendListResponse)
def anchor_trends(
    db: DbSession,
    access: AlertViewAccess,
    period_days: Annotated[int, Query()] = 3,
    end_date: date | None = None,
    room_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    anchor_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    anchor_names: Annotated[list[str] | None, Query()] = None,
    control_names: Annotated[list[str] | None, Query()] = None,
    trend_type: Literal["all", "rise", "fall", "insufficient"] = "all",
    roi_target_status: Literal["reached", "not_reached"] | None = None,
    pushed: bool | None = None,
    destination_group: str | None = None,
    minimum_coverage_rate: Annotated[Decimal | None, Query(ge=0, le=1)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> AnchorTrendListResponse:
    access.assert_rooms(tuple(room_ids or ()))
    try:
        return AnchorTrendListResponse.model_validate(
            AnchorTrendService(
                db,
                CATALOG,
                access,
                load_runtime_settings(db),
            ).list_results(
                period_days=period_days,
                end_date=end_date,
                room_ids=tuple(room_ids or ()),
                anchor_ids=tuple(anchor_ids or ()),
                anchor_names=tuple(anchor_names or ()),
                control_names=tuple(control_names or ()),
                trend_type=trend_type,
                roi_target_status=roi_target_status,
                pushed=pushed,
                destination_group=destination_group,
                minimum_coverage_rate=minimum_coverage_rate,
                limit=limit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/alerts/anchor-trends/recalculate",
    response_model=AnchorTrendRecalculateResponse,
)
def recalculate_anchor_trends(
    payload: AnchorTrendRecalculateRequest,
    db: DbSession,
    access: OperatorAccess,
) -> AnchorTrendRecalculateResponse:
    access.assert_rooms(tuple(payload.room_ids))
    try:
        return AnchorTrendRecalculateResponse.model_validate(
            AnchorTrendService(
                db,
                CATALOG,
                access,
                load_runtime_settings(db),
            ).recalculate(
                rule_id=payload.rule_id,
                period_days=payload.period_days,
                end_date=payload.end_date,
                room_ids=tuple(payload.room_ids),
                anchor_names=tuple(payload.anchor_names),
                operator_id=access.user_id,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/alerts/anchor-trends/send",
    response_model=AnchorTrendPushResponse,
    response_model_exclude_none=True,
)
async def send_anchor_trend_summary(
    payload: AnchorTrendSendRequest,
    db: DbSession,
    access: OperatorAccess,
) -> AnchorTrendPushResponse:
    if payload.force_resend and not (payload.resend_reason or "").strip():
        raise HTTPException(status_code=422, detail="强制重新发送必须填写原因")
    try:
        return AnchorTrendPushResponse.model_validate(
            await AnchorTrendService(
                db,
                CATALOG,
                access,
                load_runtime_settings(db),
            ).send_summary(
                rule_id=payload.rule_id,
                period=payload.period,
                notification_type=payload.notification_type,
                force_resend=payload.force_resend,
                resend_reason=payload.resend_reason,
                operator_id=access.user_id,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/alerts/anchor-trends/{event_id}",
    response_model=AnchorTrendEventDetailsResponse,
)
def anchor_trend_event(
    event_id: uuid.UUID,
    db: DbSession,
    access: AlertViewAccess,
) -> AnchorTrendEventDetailsResponse:
    try:
        return AnchorTrendEventDetailsResponse.model_validate(
            AnchorTrendService(
                db,
                CATALOG,
                access,
                load_runtime_settings(db),
            ).get_event(event_id)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/alerts/anchor-trends/test-push",
    response_model=AnchorTrendPushResponse,
    response_model_exclude_none=True,
)
async def test_anchor_trend_push(
    payload: AnchorTrendTestRequest,
    db: DbSession,
    access: OperatorAccess,
) -> AnchorTrendPushResponse:
    settings = load_runtime_settings(db)
    rise = payload.notification_type == "anchor_rise_summary"
    title = "【主播近期数据上涨榜｜测试】" if rise else "【主播近期数据下跌预警｜测试】"
    card = FeishuBotClient.build_card(
        title,
        [
            "**周期：** 2026-07-13 至 2026-07-15（对比 2026-07-10 至 2026-07-12）",
            "**直播间：** 测试直播间｜**主播：** 测试主播",
            (
                "**ROI：** 1.50 → 1.95（+30.00%）｜**消耗：** ¥300.00 → ¥300.00（0.00%）"
                if rise
                else "**ROI：** 2.00 → 1.40（-30.00%）｜**消耗：** ¥300.00 → ¥300.00（0.00%）"
            ),
            "**ROI目标：** 1.81｜**主要贡献时段：** 08-09、09-10、10-11",
            "测试消息不会创建业务趋势事件。",
        ],
        {"查看详情": f"{settings.app_base_url}/alerts?tab={'rise' if rise else 'fall'}"},
        template="green" if rise else "red",
    )
    result = await AlertService(db, settings, None).send_card(
        card,
        idempotency_key=f"anchor-trend-test:{uuid.uuid4()}",
        chat_id=payload.chat_id,
        test_payload=True,
    )
    return AnchorTrendPushResponse.model_validate(
        {
            "push_status": "skipped" if result.get("mocked") is True else "sent",
            "provider": result,
            "payload": card,
        }
    )
