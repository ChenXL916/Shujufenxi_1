from __future__ import annotations

import uuid
from datetime import time
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AdminAccess
from app.core.config import get_settings
from app.core.paths import project_root
from app.core.runtime_settings import load_runtime_settings
from app.core.secrets import SecretBox
from app.db.session import get_db
from app.integrations.excel.reader import scan_workbook
from app.integrations.feishu.client import FeishuBitableClient, FeishuError
from app.integrations.feishu.oauth_store import FeishuOAuthStore
from app.models.entities import (
    AuditLog,
    MetricDefinition,
    Room,
    ShiftRule,
    SourceConfig,
    SystemSetting,
    User,
    UserRoomPermission,
)
from app.services.feishu_sync_service import sync_configured_source

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(get_db)]
ROOT = project_root()


class SourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_type: str = "feishu_bitable"
    source_role: str
    app_token: str
    table_id: str
    view_id: str | None = None
    default_room_name: str | None = None
    schedule_year: int | None = None
    field_mapping: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class MetricPatch(BaseModel):
    display_name: str | None = None
    category: str | None = None
    unit: str | None = None
    direction: str | None = None
    chartable: bool | None = None
    comparable: bool | None = None
    alertable: bool | None = None
    enabled: bool | None = None


class ShiftPatch(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    crosses_midnight: bool | None = None
    is_rest: bool | None = None
    enabled: bool | None = None
    notes: str | None = None


class UserPatch(BaseModel):
    role_name: str | None = None
    active: bool | None = None


class PermissionRequest(BaseModel):
    room_ids: list[uuid.UUID]
    can_export: bool = False


class SettingsPatch(BaseModel):
    live_sync_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    schedule_sync_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    alert_delay_minutes: int | None = Field(default=None, ge=1, le=1440)
    feishu_app_id: str | None = Field(default=None, max_length=255)
    feishu_app_secret: str | None = Field(default=None, max_length=512)
    feishu_bot_webhook_url: str | None = Field(default=None, max_length=2048)
    feishu_bot_secret: str | None = Field(default=None, max_length=512)
    feishu_bot_chat_id: str | None = Field(default=None, max_length=255)
    daily_summary_time: str | None = None

    @field_validator(
        "feishu_app_id",
        "feishu_app_secret",
        "feishu_bot_webhook_url",
        "feishu_bot_secret",
        "feishu_bot_chat_id",
        mode="before",
    )
    @classmethod
    def blank_secret_means_unchanged(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("feishu_bot_webhook_url")
    @classmethod
    def validate_feishu_webhook(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"open.feishu.cn", "open.larksuite.com"}
            or not parsed.path.startswith("/open-apis/bot/v2/hook/")
        ):
            raise ValueError("仅支持飞书官方群机器人 Webhook 地址")
        return value

    @field_validator("feishu_bot_chat_id")
    @classmethod
    def validate_feishu_chat_id(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("oc_"):
            raise ValueError("飞书群 ID 必须以 oc_ 开头")
        return value


def audit(
    db: Session,
    request: Request,
    access: AdminAccess,
    action: str,
    object_type: str,
    object_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    db.add(
        AuditLog(
            user_id=access.user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before_summary=before,
            after_summary=after,
            ip_address=request.client.host if request.client else None,
        )
    )


@router.get("/sources")
def list_sources(db: DbSession, access: AdminAccess) -> list[dict[str, Any]]:
    return [source_payload(source) for source in db.scalars(select(SourceConfig))]


@router.post("/sources", status_code=201)
def create_source(
    payload: SourceRequest, request: Request, db: DbSession, access: AdminAccess
) -> dict[str, Any]:
    source = SourceConfig(**payload.model_dump())
    db.add(source)
    db.flush()
    audit(
        db, request, access, "create", "source_config", str(source.id), None, source_payload(source)
    )
    db.commit()
    return source_payload(source)


@router.patch("/sources/{source_id}")
def update_source(
    source_id: uuid.UUID,
    payload: SourceRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    source = db.get(SourceConfig, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    before = source_payload(source)
    for key, value in payload.model_dump().items():
        setattr(source, key, value)
    after = source_payload(source)
    audit(db, request, access, "update", "source_config", str(source.id), before, after)
    db.commit()
    return after


@router.post("/sources/{source_id}/test")
async def test_source(source_id: uuid.UUID, db: DbSession, access: AdminAccess) -> dict[str, Any]:
    source = db.get(SourceConfig, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    settings = get_settings()
    if not settings.feishu_credentials_configured:
        return {"ok": True, "mode": "fixture_mock", "message": "Mock Feishu API 连接正常"}
    client = await feishu_client(db)
    try:
        health = await client.health_check_source(source.app_token, source.table_id)
        return {
            "ok": health.ok,
            "tables": health.tables,
            "fields": health.fields,
            "latency_ms": health.latency_ms,
        }
    except FeishuError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router.get("/sources/{source_id}/scan")
async def scan_source(source_id: uuid.UUID, db: DbSession, access: AdminAccess) -> dict[str, Any]:
    source = db.get(SourceConfig, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    settings = get_settings()
    if not settings.feishu_credentials_configured:
        workbooks = [scan_workbook(path) for path in (ROOT / "fixtures").glob("*.xlsx")]
        return {
            "mode": "fixture_mock",
            "tables": [
                {"table_id": sheet.name, "name": sheet.name, "fields": list(sheet.headers)}
                for workbook in workbooks
                for sheet in workbook.sheets
            ],
        }
    client = await feishu_client(db)
    try:
        tables = await client.list_tables(source.app_token)
        fields = await client.list_fields(source.app_token, source.table_id)
        return {"mode": "feishu", "tables": tables, "fields": fields}
    except FeishuError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router.post("/sources/{source_id}/sync")
async def sync_source(source_id: uuid.UUID, db: DbSession, access: AdminAccess) -> dict[str, Any]:
    source = db.get(SourceConfig, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        result = await sync_configured_source(source.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FeishuError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"source_id": str(source.id), "result": result}


@router.get("/metrics")
def metrics(db: DbSession, access: AdminAccess) -> list[dict[str, Any]]:
    return [
        row_payload(metric)
        for metric in db.scalars(select(MetricDefinition).order_by(MetricDefinition.sort_order))
    ]


@router.patch("/metrics/{metric_id}")
def update_metric(
    metric_id: uuid.UUID,
    payload: MetricPatch,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    metric = db.get(MetricDefinition, metric_id)
    if metric is None:
        raise HTTPException(status_code=404, detail="指标不存在")
    before = row_payload(metric)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(metric, key, value)
    after = row_payload(metric)
    audit(db, request, access, "update", "metric", str(metric.id), before, after)
    db.commit()
    return after


@router.get("/shifts")
def shifts(db: DbSession, access: AdminAccess) -> list[dict[str, Any]]:
    return [row_payload(shift) for shift in db.scalars(select(ShiftRule).order_by(ShiftRule.name))]


@router.patch("/shifts/{shift_id}")
def update_shift(
    shift_id: uuid.UUID,
    payload: ShiftPatch,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    shift = db.get(ShiftRule, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="班次不存在")
    before = row_payload(shift)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(shift, key, value)
    after = row_payload(shift)
    audit(db, request, access, "update", "shift", str(shift.id), before, after)
    db.commit()
    return after


@router.get("/users")
def users(db: DbSession, access: AdminAccess) -> list[dict[str, Any]]:
    permissions = list(db.scalars(select(UserRoomPermission)))
    return [
        {
            **row_payload(user),
            "room_ids": [str(item.room_id) for item in permissions if item.user_id == user.id],
        }
        for user in db.scalars(select(User).order_by(User.name))
    ]


@router.patch("/users/{user_id}")
def update_user(
    user_id: uuid.UUID,
    payload: UserPatch,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    before = {"role_name": user.role_name, "active": user.active}
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(user, key, value)
    after = {"role_name": user.role_name, "active": user.active}
    audit(db, request, access, "update", "user", str(user.id), before, after)
    db.commit()
    return row_payload(user)


@router.put("/users/{user_id}/permissions")
def update_permissions(
    user_id: uuid.UUID,
    payload: PermissionRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    rooms = list(db.scalars(select(Room).where(Room.id.in_(payload.room_ids))))
    if user is None or len(rooms) != len(set(payload.room_ids)):
        raise HTTPException(status_code=404, detail="用户或直播间不存在")
    existing = list(
        db.scalars(select(UserRoomPermission).where(UserRoomPermission.user_id == user_id))
    )
    for item in existing:
        db.delete(item)
    for room_id in set(payload.room_ids):
        db.add(UserRoomPermission(user_id=user_id, room_id=room_id, can_export=payload.can_export))
    audit(
        db,
        request,
        access,
        "update_permissions",
        "user",
        str(user_id),
        {"room_ids": [str(item.room_id) for item in existing]},
        {"room_ids": [str(item) for item in payload.room_ids], "can_export": payload.can_export},
    )
    db.commit()
    return {"user_id": str(user_id), "room_ids": [str(item) for item in payload.room_ids]}


@router.get("/settings")
def system_settings(db: DbSession, access: AdminAccess) -> dict[str, Any]:
    settings = load_runtime_settings(db)
    stored = {item.key: item.value for item in db.scalars(select(SystemSetting))}
    return {
        "live_sync_interval_minutes": stored.get("live_sync_interval_minutes", {}).get(
            "value", settings.live_sync_interval_minutes
        ),
        "schedule_sync_interval_minutes": stored.get("schedule_sync_interval_minutes", {}).get(
            "value", settings.schedule_sync_interval_minutes
        ),
        "alert_delay_minutes": stored.get("alert_delay_minutes", {}).get(
            "value", settings.alert_delay_minutes
        ),
        "daily_summary_time": stored.get("daily_summary_time", {}).get("value", "09:00"),
        "feishu_app_configured": settings.feishu_credentials_configured,
        "feishu_bot_configured": settings.feishu_bot_configured,
        "feishu_bot_webhook_configured": bool(settings.feishu_bot_webhook_url),
        "feishu_bot_signing_secret_configured": bool(settings.feishu_bot_secret),
        "feishu_bot_chat_configured": bool(settings.feishu_bot_chat_id),
    }


@router.patch("/settings")
def update_settings(
    payload: SettingsPatch,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    secret_box = SecretBox(get_settings())
    safe_after: dict[str, Any] = {}
    for key, value in payload.model_dump(exclude_none=True).items():
        is_secret = key in {
            "feishu_app_id",
            "feishu_app_secret",
            "feishu_bot_webhook_url",
            "feishu_bot_secret",
            "feishu_bot_chat_id",
        }
        stored_value = secret_box.encrypt(str(value)) if is_secret else value
        setting = db.get(SystemSetting, key)
        if setting is None:
            setting = SystemSetting(
                key=key,
                value={"value": stored_value},
                encrypted=is_secret,
                updated_by=access.user_id,
            )
            db.add(setting)
        else:
            setting.value = {"value": stored_value}
            setting.encrypted = is_secret
            setting.updated_by = access.user_id
        safe_after[key] = bool(value) if is_secret else value
    audit(db, request, access, "update", "system_settings", None, None, safe_after)
    db.commit()
    return system_settings(db, access)


@router.get("/audit-logs")
def audit_logs(db: DbSession, access: AdminAccess) -> list[dict[str, Any]]:
    return [
        row_payload(item)
        for item in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200))
    ]


def source_payload(source: SourceConfig) -> dict[str, Any]:
    return row_payload(source)


async def feishu_client(db: Session) -> FeishuBitableClient:
    settings = load_runtime_settings(db)
    credential = FeishuOAuthStore(settings).load(db)
    access_token = (
        await FeishuOAuthStore(settings).valid_access_token(db) if credential is not None else None
    )
    return FeishuBitableClient(
        settings.feishu_app_id,
        settings.feishu_app_secret,
        access_token=access_token,
    )


def row_payload(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
