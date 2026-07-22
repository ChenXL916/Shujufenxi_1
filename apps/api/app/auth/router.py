from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import Access, SyncAccess, require_csrf
from app.auth.oauth import FeishuOAuthClient
from app.auth.session import SessionCodec
from app.core.runtime_settings import load_runtime_settings
from app.db.base import utc_now
from app.db.session import get_db
from app.integrations.feishu.client import FeishuError
from app.integrations.feishu.oauth_store import FeishuOAuthStore, FeishuReauthorizationRequired
from app.models.entities import RoomResource, SourceConfig, User
from app.services.feishu_sync_service import sync_configured_sources
from app.services.permission_service import provision_feishu_user, user_has_permission

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/feishu/login")
def feishu_login(db: DbSession) -> Response:
    settings = load_runtime_settings(db)
    if not settings.feishu_credentials_configured:
        raise HTTPException(
            status_code=503, detail="尚未配置飞书 App ID/App Secret；开发环境可使用登录旁路"
        )
    state = secrets.token_urlsafe(32)
    codec = SessionCodec(settings)
    response = RedirectResponse(FeishuOAuthClient(settings).authorization_url(state))
    response.set_cookie(
        "live_ops_oauth_state",
        codec.dumps_state(state),
        max_age=600,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    return response


@router.get("/feishu/callback")
async def feishu_callback(
    request: Request,
    db: DbSession,
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=1)],
    state_cookie: Annotated[str | None, Cookie(alias="live_ops_oauth_state")] = None,
) -> Response:
    settings = load_runtime_settings(db)
    expected = SessionCodec(settings).loads_state(state_cookie or "")
    if expected is None or not hmac.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="OAuth state 校验失败")
    client = FeishuOAuthClient(settings)
    try:
        grant = await client.exchange_authorization(code)
    except FeishuError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()
    identity = grant.identity
    user = db.scalar(select(User).where(User.feishu_user_id == identity.user_id))
    if user is None and identity.email:
        normalized_email = identity.email.strip().lower()
        invitations = list(
            db.scalars(
                select(User).where(
                    func.lower(func.trim(User.email)) == normalized_email,
                    or_(
                        User.feishu_user_id.is_(None),
                        User.feishu_user_id.like("pending:%"),
                    ),
                    User.active.is_(True),
                )
            )
        )
        if len(invitations) == 1:
            user = invitations[0]
            user.feishu_user_id = identity.user_id
    if user is None:
        if not settings.feishu_auto_provision_enabled:
            raise HTTPException(
                status_code=403,
                detail="该飞书账号尚未被邀请使用本系统",
            )
        try:
            user = provision_feishu_user(
                db,
                feishu_user_id=identity.user_id,
                name=identity.name,
                avatar_url=identity.avatar_url,
                email=identity.email,
                default_role_code=settings.feishu_auto_provision_role,
                ip_address=request.client.host if request.client else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    user.name = identity.name
    user.avatar_url = identity.avatar_url
    if identity.email:
        normalized_email = identity.email.strip().lower()
        conflicting_user = db.scalar(
            select(User.id).where(User.email == normalized_email, User.id != user.id)
        )
        if conflicting_user is None:
            user.email = normalized_email
    user.last_login_at = utc_now()
    db.commit()
    sync_result = "identity_only"
    if user_has_permission(db, user.id, "feishu.manage"):
        try:
            FeishuOAuthStore(settings).save_grant(db, grant, user.id)
        except FeishuReauthorizationRequired as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        sync_result = "success"
        try:
            await sync_configured_sources("live_actual")
        except Exception:
            # Identity login still succeeds; developers can inspect the source error.
            sync_result = "failed"
    csrf = secrets.token_urlsafe(32)
    session_cookie = SessionCodec(settings).dumps({"user_id": str(user.id), "csrf": csrf})
    response = RedirectResponse(
        f"{settings.app_base_url}/overview?{urlencode({'feishu_sync': sync_result})}"
    )
    response.set_cookie(
        "live_ops_session",
        session_cookie,
        max_age=SessionCodec.max_age_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    response.set_cookie(
        "live_ops_csrf",
        csrf,
        max_age=SessionCodec.max_age_seconds,
        httponly=False,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    response.delete_cookie("live_ops_oauth_state")
    return response


@router.get("/feishu/status")
def feishu_status(db: DbSession, access: Access) -> dict[str, object]:
    settings = load_runtime_settings(db)
    credential = FeishuOAuthStore(settings).load(db)
    source = db.scalar(
        select(SourceConfig).where(
            SourceConfig.app_token == settings.feishu_live_app_token,
            SourceConfig.table_id == settings.feishu_live_table_id,
            SourceConfig.source_role == "live_actual",
        )
    )
    refresh_valid = bool(
        credential
        and (
            credential.refresh_expires_at is None
            or credential.refresh_expires_at.astimezone(UTC) > datetime.now(UTC)
        )
    )
    response: dict[str, object] = {
        "can_manage": access.has_permission("feishu.manage"),
        "last_success_at": source.last_success_at if source else None,
        "realtime_ready": bool(
            credential
            and refresh_valid
            and source
            and source.source_type == "feishu_bitable"
            and source.last_success_at
        ),
        "sync_interval_minutes": settings.live_sync_interval_minutes,
    }
    if not access.has_permission("feishu.manage"):
        return response
    response.update(
        {
            "credentials_configured": settings.feishu_credentials_configured,
            "live_source_configured": bool(
                settings.feishu_live_app_token and settings.feishu_live_table_id
            ),
            "user_authorized": credential is not None,
            "refresh_valid": refresh_valid,
            "scope": credential.scope.split() if credential else [],
            "last_error": source.last_error if source else None,
            "login_url": f"{settings.api_base_url}/auth/feishu/login",
        }
    )
    return response


@router.post("/feishu/sync")
async def sync_feishu_now(access: SyncAccess) -> dict[str, Any]:
    try:
        return await sync_configured_sources("live_actual")
    except FeishuReauthorizationRequired as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except FeishuError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/logout")
def logout(_: Annotated[None, Depends(require_csrf)]) -> Response:
    response = Response(status_code=204)
    response.delete_cookie("live_ops_session")
    response.delete_cookie("live_ops_csrf")
    return response


@router.get("/me")
def current_user(access: Access, db: DbSession) -> dict[str, object]:
    room_names = (
        ["全部直播间"]
        if access.room_ids is None
        else list(
            db.scalars(
                select(RoomResource.room_name)
                .where(
                    RoomResource.room_id.in_(access.room_ids),
                    RoomResource.enabled.is_(True),
                )
                .order_by(RoomResource.room_name.asc())
            )
        )
    )
    shared = {
        "role": access.role,
        "roles": sorted(access.role_codes),
        "permissions": ["*"]
        if access.permission_codes is None
        else sorted(access.permission_codes),
        "room_ids": None
        if access.room_ids is None
        else sorted(str(item) for item in access.room_ids),
        "room_names": room_names,
        "scope_label": access.scope_label,
        "can_export": access.can_export,
        "can_manage_permissions": access.has_permission("permission.manage"),
        "can_manage_system": access.has_permission("system.manage"),
        "can_manage_alerts": access.has_permission("alert.manage"),
        "can_sync": access.has_permission("sync.run"),
        "features": {
            "can_view_dashboard": access.has_permission("dashboard.view"),
            "can_export": access.has_permission("dashboard.export"),
            "can_view_alerts": access.has_permission("alert.view"),
            "can_manage_alerts": access.has_permission("alert.manage"),
            "can_manage_permissions": access.has_permission("permission.manage"),
            "can_manage_system": access.has_permission("system.manage"),
            "can_manage_feishu": access.has_permission("feishu.manage"),
            "can_sync": access.has_permission("sync.run"),
        },
    }
    if access.user_id is None:
        return {
            "id": None,
            "name": "开发管理员",
            "auth_mode": "development_bypass",
            "csrf_token": None,
            **shared,
        }
    user = db.get(User, access.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return {
        "id": str(user.id),
        "name": user.name,
        "avatar_url": user.avatar_url,
        "auth_mode": "feishu_oauth",
        **shared,
    }
