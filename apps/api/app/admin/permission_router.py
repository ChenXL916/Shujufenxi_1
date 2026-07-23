from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AdminAccess
from app.auth.passwords import hash_password
from app.db.session import get_db
from app.models.entities import (
    FeishuGroup,
    FeishuGroupRoomScope,
    Permission,
    PermissionAuditLog,
    Role,
    RolePermission,
    RoleRoomScope,
    Room,
    RoomResource,
    User,
    UserRole,
    UserRoomPermission,
)
from app.services.permission_service import (
    reconcile_role_room_scopes,
    record_permission_audit,
)

router = APIRouter(prefix="/api/v1/admin/permissions", tags=["permission-admin"])
DbSession = Annotated[Session, Depends(get_db)]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    password: SecretStr = Field(min_length=10, max_length=128)
    role_codes: list[str] = Field(min_length=1)
    room_ids: list[uuid.UUID] | None = None
    active: bool = True

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("登录名至少 2 位")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("姓名不能为空")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


class UserAccessUpdateRequest(BaseModel):
    role_codes: list[str] = Field(min_length=1)
    room_ids: list[uuid.UUID] | None = None
    active: bool = True


class UserPasswordResetRequest(BaseModel):
    password: SecretStr = Field(min_length=10, max_length=128)


class UserCredentialsUpdateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    password: SecretStr | None = Field(default=None, min_length=10, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("登录名至少 2 位")
        return normalized


class RoleAccessUpdateRequest(BaseModel):
    role_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    permission_codes: list[str]
    room_ids: list[uuid.UUID]
    active: bool = True


class RoomResourceUpdateRequest(BaseModel):
    product_category: str = Field(min_length=1, max_length=80)
    permission_group: str = Field(min_length=1, max_length=80)
    enabled: bool = True


class FeishuGroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    chat_id: str = Field(min_length=3, max_length=255)
    room_ids: list[uuid.UUID]
    enabled: bool = True


class FeishuGroupUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    room_ids: list[uuid.UUID]
    enabled: bool = True


def _roles_for_user(db: Session, user_id: uuid.UUID) -> list[Role]:
    return list(
        db.scalars(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.role_code.asc(), Role.name.asc())
        )
    )


def _role_code(role: Role) -> str:
    return role.role_code or role.name


def _room_map(db: Session) -> dict[uuid.UUID, Room]:
    return {room.id: room for room in db.scalars(select(Room))}


def _resource_map(db: Session) -> dict[uuid.UUID, RoomResource]:
    return {item.room_id: item for item in db.scalars(select(RoomResource))}


def _effective_user_rooms(
    db: Session, user: User, roles: list[Role]
) -> tuple[list[uuid.UUID] | None, list[str]]:
    if any(role.all_permissions for role in roles):
        return None, ["全部直播间"]
    if user.room_scope_mode == "custom":
        room_ids = list(
            db.scalars(
                select(UserRoomPermission.room_id)
                .where(UserRoomPermission.user_id == user.id)
                .order_by(UserRoomPermission.room_id.asc())
            )
        )
    else:
        role_ids = [role.id for role in roles]
        room_ids = (
            list(
                db.scalars(
                    select(RoleRoomScope.room_id)
                    .where(RoleRoomScope.role_id.in_(role_ids))
                    .distinct()
                    .order_by(RoleRoomScope.room_id.asc())
                )
            )
            if role_ids
            else []
        )
    rooms = _room_map(db)
    names = [rooms[room_id].name for room_id in room_ids if room_id in rooms]
    return room_ids, names


def _serialize_user(db: Session, user: User) -> dict[str, Any]:
    roles = _roles_for_user(db, user.id)
    room_ids, room_names = _effective_user_rooms(db, user, roles)
    return {
        "id": str(user.id),
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "role_codes": [_role_code(role) for role in roles],
        "status": user.status,
        "active": user.active,
        "room_scope_mode": user.room_scope_mode,
        "room_ids": None if room_ids is None else [str(item) for item in room_ids],
        "room_names": room_names,
        "scope_label": "全部直播间" if room_ids is None else ("、".join(room_names) or "无直播间"),
        "feishu_bound": bool(
            user.feishu_user_id and not user.feishu_user_id.startswith(("pending:", "test:"))
        ),
        "password_login_enabled": bool(user.username and user.password_hash),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _serialize_role(db: Session, role: Role) -> dict[str, Any]:
    permission_codes = list(
        db.scalars(
            select(Permission.permission_code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .order_by(Permission.permission_code.asc())
        )
    )
    room_ids = list(
        db.scalars(
            select(RoleRoomScope.room_id)
            .where(RoleRoomScope.role_id == role.id)
            .order_by(RoleRoomScope.room_id.asc())
        )
    )
    rooms = _room_map(db)
    return {
        "id": str(role.id),
        "role_code": _role_code(role),
        "role_name": role.role_name or role.description or role.name,
        "description": role.description,
        "all_permissions": role.all_permissions,
        "system_role": role.system_role,
        "active": role.active,
        "permission_codes": permission_codes,
        "room_ids": [str(item) for item in room_ids],
        "room_names": [rooms[item].name for item in room_ids if item in rooms],
    }


def _serialize_group(db: Session, group: FeishuGroup) -> dict[str, Any]:
    room_ids = list(
        db.scalars(
            select(FeishuGroupRoomScope.room_id)
            .where(FeishuGroupRoomScope.group_id == group.id)
            .order_by(FeishuGroupRoomScope.room_id.asc())
        )
    )
    rooms = _room_map(db)
    return {
        "id": str(group.id),
        "name": group.name,
        "chat_id": group.chat_id,
        "enabled": group.enabled,
        "room_ids": [str(item) for item in room_ids],
        "room_names": [rooms[item].name for item in room_ids if item in rooms],
    }


def _roles_by_codes(db: Session, role_codes: list[str]) -> list[Role]:
    normalized = list(dict.fromkeys(item.strip() for item in role_codes if item.strip()))
    roles = list(
        db.scalars(select(Role).where(Role.role_code.in_(normalized), Role.active.is_(True)))
    )
    found = {_role_code(role) for role in roles}
    missing = sorted(set(normalized) - found)
    if missing:
        raise HTTPException(status_code=422, detail=f"未知或停用角色：{', '.join(missing)}")
    return sorted(roles, key=lambda item: normalized.index(_role_code(item)))


def _validate_room_ids(db: Session, room_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    normalized = list(dict.fromkeys(room_ids))
    if not normalized:
        return []
    valid = set(
        db.scalars(
            select(RoomResource.room_id).where(
                RoomResource.room_id.in_(normalized), RoomResource.enabled.is_(True)
            )
        )
    )
    missing = [str(room_id) for room_id in normalized if room_id not in valid]
    if missing:
        raise HTTPException(status_code=422, detail=f"未配置或停用的直播间：{', '.join(missing)}")
    return normalized


def _replace_user_access(
    db: Session,
    user: User,
    *,
    roles: list[Role],
    room_ids: list[uuid.UUID] | None,
    active: bool,
) -> None:
    db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db.add_all(UserRole(user_id=user.id, role_id=role.id) for role in roles)
    user.role_name = _role_code(roles[0])
    user.active = active
    user.status = "active" if active else "disabled"
    db.execute(delete(UserRoomPermission).where(UserRoomPermission.user_id == user.id))
    if room_ids is None:
        user.room_scope_mode = "role"
    else:
        user.room_scope_mode = "custom"
        can_export = any(
            permission_code == "dashboard.export"
            for role in roles
            for permission_code in db.scalars(
                select(Permission.permission_code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            )
        ) or any(role.all_permissions for role in roles)
        db.add_all(
            UserRoomPermission(
                user_id=user.id,
                room_id=room_id,
                can_export=can_export,
            )
            for room_id in room_ids
        )


def _ensure_developer_remains(db: Session, target: User, roles: list[Role], active: bool) -> None:
    current_codes = {_role_code(role) for role in _roles_for_user(db, target.id)}
    next_codes = {_role_code(role) for role in roles}
    if "developer" not in current_codes or ("developer" in next_codes and active):
        return
    developer_role = db.scalar(select(Role).where(Role.role_code == "developer"))
    if developer_role is None:
        raise HTTPException(status_code=409, detail="开发者角色不存在")
    other_count = db.scalar(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .where(
            UserRole.role_id == developer_role.id,
            User.id != target.id,
            User.active.is_(True),
        )
        .limit(1)
    )
    if other_count is None:
        raise HTTPException(status_code=409, detail="不能停用或移除最后一个开发者")


@router.get("/overview")
def permission_overview(db: DbSession, access: AdminAccess) -> dict[str, Any]:
    permissions = list(db.scalars(select(Permission).order_by(Permission.permission_code.asc())))
    roles = list(db.scalars(select(Role).order_by(Role.role_code.asc(), Role.name.asc())))
    resources = list(
        db.scalars(
            select(RoomResource).order_by(RoomResource.permission_group, RoomResource.room_name)
        )
    )
    groups = list(db.scalars(select(FeishuGroup).order_by(FeishuGroup.name.asc())))
    users = list(
        db.scalars(
            select(User)
            .where(User.status != "deleted")
            .order_by(User.username.asc(), User.email.asc())
        )
    )
    return {
        "current_actor": str(access.user_id) if access.user_id else None,
        "users": [_serialize_user(db, item) for item in users],
        "roles": [_serialize_role(db, item) for item in roles],
        "permissions": [
            {
                "id": str(item.id),
                "code": item.permission_code,
                "name": item.permission_name,
                "description": item.description,
            }
            for item in permissions
        ],
        "room_resources": [
            {
                "id": str(item.id),
                "room_id": str(item.room_id),
                "room_name": item.room_name,
                "product_category": item.product_category,
                "permission_group": item.permission_group,
                "enabled": item.enabled,
            }
            for item in resources
        ],
        "feishu_groups": [_serialize_group(db, item) for item in groups],
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    roles = _roles_by_codes(db, payload.role_codes)
    room_ids = None if payload.room_ids is None else _validate_room_ids(db, payload.room_ids)
    normalized_username = payload.username.strip().casefold()
    normalized_email = payload.email.strip().lower() if payload.email else None
    username_exists = db.scalar(
        select(User.id).where(func.lower(func.trim(User.username)) == normalized_username)
    )
    if username_exists is not None:
        raise HTTPException(status_code=409, detail="账号或邮箱已存在")
    if normalized_email:
        email_exists = db.scalar(
            select(User.id).where(func.lower(func.trim(User.email)) == normalized_email)
        )
        if email_exists is not None:
            raise HTTPException(status_code=409, detail="账号或邮箱已存在")
    user = User(
        feishu_user_id=None,
        username=normalized_username,
        name=payload.name.strip(),
        email=normalized_email,
        password_hash=hash_password(payload.password.get_secret_value()),
        role_name=_role_code(roles[0]),
        status="active" if payload.active else "disabled",
        active=payload.active,
    )
    db.add(user)
    try:
        db.flush()
        _replace_user_access(db, user, roles=roles, room_ids=room_ids, active=payload.active)
        record_permission_audit(
            db,
            actor_user_id=access.user_id,
            action="user_created",
            target_type="user",
            target_id=str(user.id),
            target_user_id=user.id,
            after_value=_serialize_user(db, user),
            ip_address=request.client.host if request.client else None,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="账号或邮箱已存在") from exc
    db.refresh(user)
    return _serialize_user(db, user)


@router.put("/users/{user_id}/password")
def reset_user_password(
    user_id: uuid.UUID,
    payload: UserPasswordResetRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.username:
        raise HTTPException(status_code=409, detail="请先为该用户配置登录名")
    before_enabled = bool(user.password_hash)
    user.password_hash = hash_password(payload.password.get_secret_value())
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="user_password_reset",
        target_type="user",
        target_id=str(user.id),
        target_user_id=user.id,
        before_value={"password_login_enabled": before_enabled},
        after_value={"password_login_enabled": True},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _serialize_user(db, user)


@router.put("/users/{user_id}/credentials")
def update_user_credentials(
    user_id: uuid.UUID,
    payload: UserCredentialsUpdateRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    normalized_username = payload.username.strip().casefold()
    username_exists = db.scalar(
        select(User.id).where(
            func.lower(func.trim(User.username)) == normalized_username,
            User.id != user.id,
        )
    )
    if username_exists is not None:
        raise HTTPException(status_code=409, detail="登录名已被其他用户使用")

    before = {
        "username": user.username,
        "web_login_enabled": bool(user.username and user.password_hash),
    }
    secret_rotated = payload.password is not None
    user.username = normalized_username
    if payload.password is not None:
        user.password_hash = hash_password(payload.password.get_secret_value())
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="user_credentials_updated",
        target_type="user",
        target_id=str(user.id),
        target_user_id=user.id,
        before_value=before,
        after_value={
            "username": user.username,
            "web_login_enabled": bool(user.username and user.password_hash),
            "secret_rotated": secret_rotated,
        },
        ip_address=request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="登录名已被其他用户使用") from exc
    db.refresh(user)
    return _serialize_user(db, user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if access.user_id == user.id:
        raise HTTPException(status_code=409, detail="不能删除当前登录账号")

    _ensure_developer_remains(db, user, roles=[], active=False)
    before = _serialize_user(db, user)

    # Preserve an invisible identity tombstone so a deleted Feishu user cannot
    # be auto-provisioned again on their next OAuth login.
    db.execute(delete(UserRoomPermission).where(UserRoomPermission.user_id == user.id))
    db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    user.username = None
    user.password_hash = None
    user.email = None
    user.avatar_url = None
    user.active = False
    user.status = "deleted"
    user.role_name = "deleted"
    user.room_scope_mode = "role"
    try:
        db.flush()
        record_permission_audit(
            db,
            actor_user_id=access.user_id,
            action="user_deleted",
            target_type="user",
            target_id=str(user_id),
            target_user_id=user.id,
            before_value=before,
            after_value={
                "deleted": True,
                "feishu_identity_blocked": bool(user.feishu_user_id),
            },
            ip_address=request.client.host if request.client else None,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户仍有关联数据，无法删除") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/users/{user_id}/access")
def update_user_access(
    user_id: uuid.UUID,
    payload: UserAccessUpdateRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    roles = _roles_by_codes(db, payload.role_codes)
    room_ids = None if payload.room_ids is None else _validate_room_ids(db, payload.room_ids)
    _ensure_developer_remains(db, user, roles, payload.active)
    before = _serialize_user(db, user)
    _replace_user_access(db, user, roles=roles, room_ids=room_ids, active=payload.active)
    db.flush()
    after = _serialize_user(db, user)
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="user_access_updated",
        target_type="user",
        target_id=str(user.id),
        target_user_id=user.id,
        before_value=before,
        after_value=after,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return after


@router.put("/roles/{role_id}")
def update_role_access(
    role_id: uuid.UUID,
    payload: RoleAccessUpdateRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    if _role_code(role) == "developer":
        raise HTTPException(status_code=409, detail="开发者 ALL 权限不可降级")
    permission_codes = list(dict.fromkeys(payload.permission_codes))
    permissions = list(
        db.scalars(select(Permission).where(Permission.permission_code.in_(permission_codes)))
    )
    if {item.permission_code for item in permissions} != set(permission_codes):
        raise HTTPException(status_code=422, detail="包含未知权限点")
    room_ids = _validate_room_ids(db, payload.room_ids)
    before = _serialize_role(db, role)
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    db.add_all(RolePermission(role_id=role.id, permission_id=item.id) for item in permissions)
    db.execute(delete(RoleRoomScope).where(RoleRoomScope.role_id == role.id))
    db.add_all(RoleRoomScope(role_id=role.id, room_id=room_id) for room_id in room_ids)
    if payload.role_name is not None:
        role.role_name = payload.role_name.strip()
    if payload.description is not None:
        role.description = payload.description.strip()
    role.active = payload.active
    db.flush()
    after = _serialize_role(db, role)
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="role_access_updated",
        target_type="role",
        target_id=str(role.id),
        before_value=before,
        after_value=after,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return after


@router.put("/room-resources/{resource_id}")
def update_room_resource(
    resource_id: uuid.UUID,
    payload: RoomResourceUpdateRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    resource = db.get(RoomResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="直播间资源不存在")
    before = {
        "product_category": resource.product_category,
        "permission_group": resource.permission_group,
        "enabled": resource.enabled,
    }
    resource.product_category = payload.product_category.strip()
    resource.permission_group = payload.permission_group.strip()
    resource.enabled = payload.enabled
    reconcile_role_room_scopes(db)
    db.flush()
    after = {
        "id": str(resource.id),
        "room_id": str(resource.room_id),
        "room_name": resource.room_name,
        "product_category": resource.product_category,
        "permission_group": resource.permission_group,
        "enabled": resource.enabled,
    }
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="room_resource_updated",
        target_type="room_resource",
        target_id=str(resource.id),
        before_value=before,
        after_value=after,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return after


def _replace_group_rooms(db: Session, group: FeishuGroup, room_ids: list[uuid.UUID]) -> None:
    db.execute(delete(FeishuGroupRoomScope).where(FeishuGroupRoomScope.group_id == group.id))
    db.add_all(FeishuGroupRoomScope(group_id=group.id, room_id=room_id) for room_id in room_ids)


@router.post("/feishu-groups", status_code=status.HTTP_201_CREATED)
def create_feishu_group(
    payload: FeishuGroupCreateRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    room_ids = _validate_room_ids(db, payload.room_ids)
    group = FeishuGroup(
        name=payload.name.strip(),
        chat_id=payload.chat_id.strip(),
        enabled=payload.enabled,
    )
    db.add(group)
    try:
        db.flush()
        _replace_group_rooms(db, group, room_ids)
        db.flush()
        after = _serialize_group(db, group)
        record_permission_audit(
            db,
            actor_user_id=access.user_id,
            action="feishu_group_created",
            target_type="feishu_group",
            target_id=str(group.id),
            after_value=after,
            ip_address=request.client.host if request.client else None,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="飞书群标识已存在") from exc
    return after


@router.put("/feishu-groups/{group_id}")
def update_feishu_group(
    group_id: uuid.UUID,
    payload: FeishuGroupUpdateRequest,
    request: Request,
    db: DbSession,
    access: AdminAccess,
) -> dict[str, Any]:
    group = db.get(FeishuGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="飞书群不存在")
    room_ids = _validate_room_ids(db, payload.room_ids)
    before = _serialize_group(db, group)
    group.name = payload.name.strip()
    group.enabled = payload.enabled
    _replace_group_rooms(db, group, room_ids)
    db.flush()
    after = _serialize_group(db, group)
    record_permission_audit(
        db,
        actor_user_id=access.user_id,
        action="feishu_group_scope_updated",
        target_type="feishu_group",
        target_id=str(group.id),
        before_value=before,
        after_value=after,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return after


@router.get("/audit-logs")
def permission_audit_logs(
    db: DbSession,
    access: AdminAccess,
    limit: int = 200,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    rows = list(
        db.scalars(
            select(PermissionAuditLog).order_by(PermissionAuditLog.created_at.desc()).limit(limit)
        )
    )
    return [
        {
            "id": str(item.id),
            "user_id": str(item.user_id) if item.user_id else None,
            "action": item.action,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "target_user_id": str(item.target_user_id) if item.target_user_id else None,
            "before_value": item.before_value,
            "after_value": item.after_value,
            "ip": item.ip_address,
            "created_at": item.created_at,
        }
        for item in rows
    ]
