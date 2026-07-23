from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.rbac import (
    AUTO_PROVISION_ROLE_CODES,
    INITIAL_ROOM_RESOURCE_CONFIG,
    LEGACY_ROLE_MAP,
    PERMISSION_DEFINITIONS,
    ROLE_BY_CODE,
    ROLE_DEFINITIONS,
    TEST_ACCOUNT_DEFINITIONS,
)
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
)

SENSITIVE_KEY_PARTS = ("password", "secret", "token", "webhook", "authorization", "cookie")


def _role_code(role: Role) -> str:
    return role.role_code or role.name


def user_has_permission(db: Session, user_id: uuid.UUID, permission_code: str) -> bool:
    roles = list(
        db.scalars(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Role.active.is_(True))
        )
    )
    if any(role.all_permissions for role in roles):
        return True
    role_ids = [role.id for role in roles]
    if not role_ids:
        return False
    return (
        db.scalar(
            select(Permission.id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(
                RolePermission.role_id.in_(role_ids),
                Permission.permission_code == permission_code,
            )
            .limit(1)
        )
        is not None
    )


def provision_feishu_user(
    session: Session,
    *,
    feishu_user_id: str,
    name: str,
    avatar_url: str | None,
    email: str | None,
    default_role_code: str,
    ip_address: str | None = None,
) -> User:
    """Create a least-privilege business account for an authenticated Feishu identity."""
    role = session.scalar(
        select(Role).where(
            Role.role_code == default_role_code,
            Role.active.is_(True),
        )
    )
    if role is None:
        raise ValueError(f"飞书自动开户默认角色不可用：{default_role_code}")
    if _role_code(role) not in AUTO_PROVISION_ROLE_CODES:
        raise ValueError("飞书自动开户只能授予直播主管、项目 PM 或受限查看者角色")

    normalized_email = email.strip().lower() if email and email.strip() else None
    if normalized_email is not None:
        email_owner = session.scalar(select(User.id).where(User.email == normalized_email))
        if email_owner is not None:
            normalized_email = None
    user = User(
        feishu_user_id=feishu_user_id,
        username=None,
        name=name,
        avatar_url=avatar_url,
        email=normalized_email,
        password_hash=None,
        status="active",
        room_scope_mode="role",
        role_name=_role_code(role),
        active=True,
    )
    session.add(user)
    session.flush()
    _ensure_user_role(session, user, role)
    record_permission_audit(
        session,
        actor_user_id=user.id,
        action="feishu_user_auto_provisioned",
        target_type="user",
        target_id=str(user.id),
        target_user_id=user.id,
        after_value={
            "role_code": _role_code(role),
            "room_scope_mode": "role",
            "feishu_identity_bound": True,
        },
        ip_address=ip_address,
    )
    return user


def _redact(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def record_permission_audit(
    session: Session,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: str | None,
    target_user_id: uuid.UUID | None = None,
    before_value: dict[str, Any] | None = None,
    after_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> PermissionAuditLog:
    row = PermissionAuditLog(
        user_id=actor_user_id,
        action=action,
        target_user_id=target_user_id,
        target_type=target_type,
        target_id=target_id,
        before_value=_redact(before_value) if before_value is not None else None,
        after_value=_redact(after_value) if after_value is not None else None,
        ip_address=ip_address,
    )
    session.add(row)
    return row


def _ensure_role(session: Session, code: str) -> Role:
    definition = ROLE_BY_CODE[code]
    role = session.scalar(select(Role).where((Role.role_code == code) | (Role.name == code)))
    if role is None:
        role = Role(
            name=code, role_code=code, role_name=definition.name, description=definition.description
        )
        session.add(role)
        session.flush()
    role.name = code
    role.role_code = code
    role.role_name = definition.name
    role.description = definition.description
    role.all_permissions = definition.all_permissions
    role.system_role = True
    role.active = True
    return role


def _ensure_permissions(session: Session) -> dict[str, Permission]:
    result: dict[str, Permission] = {}
    for definition in PERMISSION_DEFINITIONS:
        permission = session.scalar(
            select(Permission).where(Permission.permission_code == definition.code)
        )
        if permission is None:
            permission = Permission(
                permission_code=definition.code,
                permission_name=definition.name,
                description=definition.description,
            )
            session.add(permission)
            session.flush()
        else:
            permission.permission_name = definition.name
            permission.description = definition.description
        result[definition.code] = permission
    return result


def _ensure_room_resources(session: Session) -> dict[uuid.UUID, RoomResource]:
    result: dict[uuid.UUID, RoomResource] = {}
    rooms = list(session.scalars(select(Room).where(Room.active.is_(True))))
    for room in rooms:
        configured = INITIAL_ROOM_RESOURCE_CONFIG.get(room.name)
        if configured is None:
            continue
        category, group = configured
        resource = session.scalar(select(RoomResource).where(RoomResource.room_id == room.id))
        if resource is None:
            resource = RoomResource(
                room_id=room.id,
                room_name=room.name,
                product_category=category,
                permission_group=group,
                enabled=True,
            )
            session.add(resource)
            session.flush()
        else:
            resource.room_name = room.name
            resource.product_category = category
            resource.permission_group = group
        result[room.id] = resource
    return result


def reconcile_role_room_scopes(session: Session) -> None:
    resources = list(session.scalars(select(RoomResource).where(RoomResource.enabled.is_(True))))
    roles = {
        _role_code(role): role
        for role in session.scalars(select(Role).where(Role.system_role.is_(True)))
    }
    for definition in ROLE_DEFINITIONS:
        role = roles.get(definition.code)
        if role is None or definition.all_permissions:
            continue
        expected = {
            resource.room_id
            for resource in resources
            if resource.permission_group in definition.room_groups
        }
        existing = {
            row.room_id: row
            for row in session.scalars(
                select(RoleRoomScope).where(RoleRoomScope.role_id == role.id)
            )
        }
        for room_id, row in existing.items():
            if room_id not in expected:
                session.delete(row)
        for room_id in expected - set(existing):
            session.add(RoleRoomScope(role_id=role.id, room_id=room_id))


def _ensure_user_role(session: Session, user: User, role: Role) -> None:
    if (
        session.scalar(
            select(UserRole.id).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        )
        is None
    ):
        session.add(UserRole(user_id=user.id, role_id=role.id))


def _ensure_test_accounts(session: Session, roles: dict[str, Role]) -> None:
    for username, display_name, role_code in TEST_ACCOUNT_DEFINITIONS:
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                feishu_user_id=f"test:{username}",
                username=username,
                name=display_name,
                avatar_url=None,
                email=f"{username}@example.local",
                password_hash=None,
                status="active",
                role_name=role_code,
                active=True,
                last_login_at=None,
            )
            session.add(user)
            session.flush()
        else:
            user.name = display_name
            user.status = "active"
            user.active = True
            user.role_name = role_code
        session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        _ensure_user_role(session, user, roles[role_code])


def seed_permission_reference_data(
    session: Session,
    dev_admin_email: str | None,
    *,
    include_test_accounts: bool = True,
    default_feishu_chat_id: str | None = None,
) -> None:
    permissions = _ensure_permissions(session)
    roles = {
        definition.code: _ensure_role(session, definition.code) for definition in ROLE_DEFINITIONS
    }
    for definition in ROLE_DEFINITIONS:
        role = roles[definition.code]
        existing = set(
            session.scalars(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            )
        )
        for permission_code in definition.permissions:
            permission = permissions[permission_code]
            if permission.id not in existing:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    _ensure_room_resources(session)
    session.flush()
    reconcile_role_room_scopes(session)

    users = list(session.scalars(select(User)))
    for user in users:
        original_role_name = user.role_name
        mapped = LEGACY_ROLE_MAP.get(original_role_name, original_role_name)
        user_role = roles.get(mapped)
        if user_role is None:
            continue
        # Older builds treated the legacy "admin" value as developer. Once the
        # formal administrator rank exists, remove that historical escalation.
        if original_role_name == "admin":
            session.execute(
                delete(UserRole).where(
                    UserRole.user_id == user.id,
                    UserRole.role_id == roles["developer"].id,
                )
            )
        user.role_name = mapped
        _ensure_user_role(session, user, user_role)
    if dev_admin_email:
        developer = session.scalar(select(User).where(User.email == dev_admin_email))
        if developer is not None:
            developer.role_name = "developer"
            _ensure_user_role(session, developer, roles["developer"])
    if include_test_accounts:
        _ensure_test_accounts(session, roles)
    if default_feishu_chat_id:
        group = session.scalar(
            select(FeishuGroup).where(FeishuGroup.chat_id == default_feishu_chat_id)
        )
        if group is None:
            group = FeishuGroup(
                name="直播主管群",
                chat_id=default_feishu_chat_id,
                all_rooms=False,
                enabled=True,
            )
            session.add(group)
            session.flush()
        business_room_ids = set(
            session.scalars(select(RoomResource.room_id).where(RoomResource.enabled.is_(True)))
        )
        existing = set(
            session.scalars(
                select(FeishuGroupRoomScope.room_id).where(
                    FeishuGroupRoomScope.group_id == group.id
                )
            )
        )
        for room_id in business_room_ids - existing:
            session.add(FeishuGroupRoomScope(group_id=group.id, room_id=room_id))
    session.commit()
