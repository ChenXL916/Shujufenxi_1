from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import LEGACY_ROLE_MAP
from app.auth.session import SessionCodec
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.entities import (
    Permission,
    Role,
    RolePermission,
    RoleRoomScope,
    RoomResource,
    User,
    UserRole,
    UserRoomPermission,
)


@dataclass(frozen=True)
class AccessScope:
    user_id: uuid.UUID | None
    role: str
    room_ids: frozenset[uuid.UUID] | None
    can_export: bool
    export_room_ids: frozenset[uuid.UUID] | None = None
    role_codes: frozenset[str] = frozenset()
    permission_codes: frozenset[str] | None = frozenset()
    scope_label: str = "无直播间"
    auth_mode: str = "feishu_oauth"

    @property
    def is_developer(self) -> bool:
        return self.permission_codes is None or "developer" in self.role_codes

    def has_permission(self, permission_code: str) -> bool:
        return self.permission_codes is None or permission_code in self.permission_codes

    def assert_permission(self, permission_code: str) -> None:
        if not self.has_permission(permission_code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    def assert_rooms(self, requested: tuple[uuid.UUID, ...] | list[uuid.UUID]) -> None:
        requested_set = set(requested)
        if self.room_ids is not None and not requested_set.issubset(self.room_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="请求包含未授权直播间",
            )

    def effective_rooms(
        self, requested: tuple[uuid.UUID, ...] | list[uuid.UUID]
    ) -> frozenset[uuid.UUID] | None:
        self.assert_rooms(requested)
        requested_set = frozenset(requested)
        if requested_set:
            return requested_set
        return self.room_ids


def _session_user(request: Request, session: Session, settings: Settings) -> tuple[User, str]:
    session_cookie = request.cookies.get("live_ops_session")
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = SessionCodec(settings).loads(session_cookie)
        if payload is None:
            raise ValueError("invalid session")
        user_id = uuid.UUID(str(payload["user_id"]))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效"
        ) from exc
    user = session.get(User, user_id)
    if user is None or not user.active or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    auth_mode = payload.get("auth_mode", "feishu_oauth")
    if auth_mode not in {"feishu_oauth", "password"}:
        auth_mode = "feishu_oauth"
    return user, auth_mode


def _user_roles(session: Session, user: User) -> list[Role]:
    roles = list(
        session.scalars(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, Role.active.is_(True))
            .order_by(Role.role_code, Role.name)
        )
    )
    if roles:
        return roles
    legacy_code = LEGACY_ROLE_MAP.get(user.role_name, user.role_name)
    role = session.scalar(
        select(Role).where(
            (Role.role_code == legacy_code) | (Role.name == legacy_code),
            Role.active.is_(True),
        )
    )
    return [role] if role else []


def _scope_label(session: Session, room_ids: frozenset[uuid.UUID] | None) -> str:
    if room_ids is None:
        return "全部直播间"
    if not room_ids:
        return "无直播间"
    names = list(
        session.scalars(
            select(RoomResource.room_name)
            .where(RoomResource.room_id.in_(room_ids), RoomResource.enabled.is_(True))
            .order_by(RoomResource.room_name)
        )
    )
    return "、".join(names) if names else "无直播间"


def get_access_scope(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccessScope:
    if settings.dev_auth_bypass:
        return AccessScope(
            user_id=None,
            role="developer",
            role_codes=frozenset({"developer"}),
            permission_codes=None,
            room_ids=None,
            export_room_ids=None,
            can_export=True,
            scope_label="全部直播间",
            auth_mode="development_bypass",
        )

    user, auth_mode = _session_user(request, session, settings)
    require_csrf(request, settings)
    roles = _user_roles(session, user)
    role_codes = frozenset((role.role_code or role.name) for role in roles)
    all_permissions = any(role.all_permissions for role in roles)
    if all_permissions:
        permission_codes: frozenset[str] | None = None
    elif roles:
        permission_codes = frozenset(
            session.scalars(
                select(Permission.permission_code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id.in_([role.id for role in roles]))
            )
        )
    else:
        permission_codes = frozenset()

    individual = list(
        session.scalars(select(UserRoomPermission).where(UserRoomPermission.user_id == user.id))
    )
    if all_permissions:
        room_ids: frozenset[uuid.UUID] | None = None
        export_room_ids: frozenset[uuid.UUID] | None = None
    elif user.room_scope_mode == "custom":
        enabled_room_ids = set(
            session.scalars(
                select(RoomResource.room_id).where(
                    RoomResource.enabled.is_(True),
                    RoomResource.room_id.in_([item.room_id for item in individual]),
                )
            )
        )
        room_ids = frozenset(enabled_room_ids)
        export_room_ids = frozenset(
            item.room_id
            for item in individual
            if item.can_export and item.room_id in enabled_room_ids
        )
    else:
        role_ids = [role.id for role in roles]
        room_ids = frozenset(
            session.scalars(
                select(RoleRoomScope.room_id)
                .join(RoomResource, RoomResource.room_id == RoleRoomScope.room_id)
                .where(
                    RoleRoomScope.role_id.in_(role_ids),
                    RoomResource.enabled.is_(True),
                )
            )
        )
        export_room_ids = (
            room_ids if permission_codes and "dashboard.export" in permission_codes else frozenset()
        )

    can_export = permission_codes is None or "dashboard.export" in permission_codes
    primary_role = next(
        iter(sorted(role_codes)), LEGACY_ROLE_MAP.get(user.role_name, user.role_name)
    )
    return AccessScope(
        user_id=user.id,
        role=primary_role,
        role_codes=role_codes,
        permission_codes=permission_codes,
        room_ids=room_ids,
        export_room_ids=export_room_ids,
        can_export=can_export,
        scope_label=_scope_label(session, room_ids),
        auth_mode=auth_mode,
    )


def require_permission(permission_code: str):  # type: ignore[no-untyped-def]
    def dependency(access: Annotated[AccessScope, Depends(get_access_scope)]) -> AccessScope:
        access.assert_permission(permission_code)
        return access

    return dependency


Access = Annotated[AccessScope, Depends(get_access_scope)]
DashboardAccess = Annotated[AccessScope, Depends(require_permission("dashboard.view"))]
ExportAccess = Annotated[AccessScope, Depends(require_permission("dashboard.export"))]
AlertViewAccess = Annotated[AccessScope, Depends(require_permission("alert.view"))]
OperatorAccess = Annotated[AccessScope, Depends(require_permission("alert.manage"))]
AdminAccess = Annotated[AccessScope, Depends(require_permission("permission.manage"))]
AlertRuleAccess = Annotated[AccessScope, Depends(require_permission("alert_rule.manage"))]
RoiTargetAccess = Annotated[AccessScope, Depends(require_permission("roi_target.manage"))]
SyncAccess = Annotated[AccessScope, Depends(require_permission("sync.run"))]
SystemAccess = Annotated[AccessScope, Depends(require_permission("system.manage"))]
DataSourceAccess = Annotated[AccessScope, Depends(require_permission("data_source.manage"))]
AuditAccess = Annotated[AccessScope, Depends(require_permission("audit.view"))]
UserManageAccess = Annotated[AccessScope, Depends(require_permission("user.manage"))]
RoleManageAccess = Annotated[AccessScope, Depends(require_permission("role.manage"))]
RoomScopeManageAccess = Annotated[AccessScope, Depends(require_permission("room_scope.manage"))]


def require_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if settings.dev_auth_bypass or request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    session_cookie = request.cookies.get("live_ops_session")
    header_token = request.headers.get("X-CSRF-Token")
    if not session_cookie or not header_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
    try:
        payload = SessionCodec(settings).loads(session_cookie)
        if payload is None:
            raise ValueError("invalid session")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败") from exc
    if payload.get("csrf") != header_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
