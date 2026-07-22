"""Add five-role RBAC, room data scopes, Feishu group scopes and permission audit.

Revision ID: 0006_rbac_data_scope
Revises: 0005_anchor_trend_summaries
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0006_rbac_data_scope"
down_revision = "0005_anchor_trend_summaries"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("dashboard.view", "查看经营数据", "查看总览、图表、比较、人员与详情"),
    ("dashboard.export", "导出经营数据", "按服务端数据范围导出 CSV/Excel"),
    ("alert.view", "查看预警", "查看范围内普通预警与主播趋势预警"),
    ("alert.manage", "处置预警", "评估、确认、重推与测试预警"),
    ("user.manage", "用户管理", "创建、停用和配置用户角色"),
    ("role.manage", "角色管理", "配置角色权限点"),
    ("permission.manage", "权限管理", "查看和修改权限矩阵"),
    ("room_scope.manage", "直播间权限管理", "配置直播间资源和数据范围"),
    ("roi_target.manage", "ROI目标管理", "配置直播间 ROI 目标"),
    ("alert_rule.manage", "预警规则管理", "配置普通及主播趋势预警规则"),
    ("feishu.manage", "飞书配置管理", "配置飞书授权、机器人和群范围"),
    ("data_source.manage", "数据源管理", "查看、扫描和同步数据源"),
    ("sync.run", "执行数据同步", "手动触发飞书数据同步"),
    ("system.manage", "系统设置管理", "修改系统运行设置和 Secret"),
    ("audit.view", "查看审计日志", "查看通用及权限审计日志"),
    ("database.manage", "数据库管理", "访问已有数据库管理入口"),
)
BUSINESS_PERMISSIONS = ("dashboard.view", "dashboard.export", "alert.view")
ROLES = (
    (
        "developer",
        "开发者/超级管理员",
        "系统最高权限，管理全部数据、用户、权限和配置",
        True,
        tuple(code for code, _name, _description in PERMISSIONS),
        (),
        "admin",
    ),
    (
        "live_manager",
        "直播主管",
        "查看三个业务直播间全部经营数据和预警",
        False,
        BUSINESS_PERMISSIONS,
        ("water_pm", "primer_pm", "powder_pm"),
        "operator",
    ),
    (
        "water_pm",
        "水散粉PM",
        "仅查看水散粉直播间数据",
        False,
        BUSINESS_PERMISSIONS,
        ("water_pm",),
        None,
    ),
    (
        "primer_pm",
        "妆前乳PM",
        "仅查看妆前乳直播间数据",
        False,
        BUSINESS_PERMISSIONS,
        ("primer_pm",),
        None,
    ),
    (
        "powder_pm",
        "散粉PM",
        "仅查看散粉直播间数据",
        False,
        BUSINESS_PERMISSIONS,
        ("powder_pm",),
        None,
    ),
    (
        "viewer",
        "受限查看者",
        "兼容既有按用户直播间授权的只读账号",
        False,
        BUSINESS_PERMISSIONS,
        (),
        None,
    ),
)
ROOM_CONFIG = {
    "Mistine 水散粉": ("water_powder", "water_pm"),
    "Mistine-水散粉": ("water_powder", "water_pm"),
    "柏瑞美-妆前乳": ("primer", "primer_pm"),
    "柏瑞美-散粉": ("powder", "powder_pm"),
}


def _new_id(bind: sa.Connection) -> uuid.UUID | str:
    value = uuid.uuid4()
    return value.hex if bind.dialect.name == "sqlite" else value


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _add_compatibility_columns() -> None:
    role_columns = _column_names("roles")
    user_columns = _column_names("users")
    with op.batch_alter_table("roles") as batch:
        if "role_code" not in role_columns:
            batch.add_column(sa.Column("role_code", sa.String(80), nullable=True))
        if "role_name" not in role_columns:
            batch.add_column(
                sa.Column("role_name", sa.String(100), nullable=False, server_default="")
            )
        if "all_permissions" not in role_columns:
            batch.add_column(
                sa.Column("all_permissions", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        if "system_role" not in role_columns:
            batch.add_column(
                sa.Column("system_role", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        if "active" not in role_columns:
            batch.add_column(
                sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true())
            )
    role_unique_names = {
        str(item["name"]) for item in sa.inspect(op.get_bind()).get_unique_constraints("roles")
    }
    if "uq_roles_role_code" not in role_unique_names:
        with op.batch_alter_table("roles") as batch:
            batch.create_unique_constraint("uq_roles_role_code", ["role_code"])

    with op.batch_alter_table("users") as batch:
        if "username" not in user_columns:
            batch.add_column(sa.Column("username", sa.String(120), nullable=True))
        if "password_hash" not in user_columns:
            batch.add_column(sa.Column("password_hash", sa.String(512), nullable=True))
        if "status" not in user_columns:
            batch.add_column(
                sa.Column("status", sa.String(30), nullable=False, server_default="active")
            )
        if "room_scope_mode" not in user_columns:
            batch.add_column(
                sa.Column("room_scope_mode", sa.String(20), nullable=False, server_default="role")
            )
    user_unique_names = {
        str(item["name"]) for item in sa.inspect(op.get_bind()).get_unique_constraints("users")
    }
    if "uq_users_username" not in user_unique_names:
        with op.batch_alter_table("users") as batch:
            batch.create_unique_constraint("uq_users_username", ["username"])


def _create_tables() -> None:
    tables = _table_names()
    if "room_resources" not in tables:
        op.create_table(
            "room_resources",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=False),
            sa.Column("room_name", sa.String(200), nullable=False),
            sa.Column("product_category", sa.String(80), nullable=False),
            sa.Column("permission_group", sa.String(80), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("room_id", name="uq_room_resources_room_id"),
        )
        op.create_index("ix_room_resources_room_id", "room_resources", ["room_id"])
        op.create_index(
            "ix_room_resources_product_category", "room_resources", ["product_category"]
        )
        op.create_index(
            "ix_room_resources_permission_group",
            "room_resources",
            ["permission_group", "enabled"],
        )
    if "permissions" not in tables:
        op.create_table(
            "permissions",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("permission_code", sa.String(120), nullable=False),
            sa.Column("permission_name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.UniqueConstraint("permission_code", name="uq_permissions_permission_code"),
        )
    if "role_permissions" not in tables:
        op.create_table(
            "role_permissions",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id"), nullable=False),
            sa.Column(
                "permission_id", sa.Uuid(), sa.ForeignKey("permissions.id"), nullable=False
            ),
            sa.UniqueConstraint(
                "role_id", "permission_id", name="uq_role_permissions_role_id"
            ),
        )
        op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
        op.create_index(
            "ix_role_permissions_permission_id", "role_permissions", ["permission_id"]
        )
    if "user_roles" not in tables:
        op.create_table(
            "user_roles",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id"), nullable=False),
            sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id"),
        )
        op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
        op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    if "role_room_scopes" not in tables:
        op.create_table(
            "role_room_scopes",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id"), nullable=False),
            sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=False),
            sa.UniqueConstraint("role_id", "room_id", name="uq_role_room_scopes_role_id"),
        )
        op.create_index("ix_role_room_scopes_role_id", "role_room_scopes", ["role_id"])
        op.create_index("ix_role_room_scopes_room_id", "role_room_scopes", ["room_id"])
    if "feishu_groups" not in tables:
        op.create_table(
            "feishu_groups",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("chat_id", sa.String(255), nullable=False),
            sa.Column("all_rooms", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("chat_id", name="uq_feishu_groups_chat_id"),
        )
    if "feishu_group_room_scopes" not in tables:
        op.create_table(
            "feishu_group_room_scopes",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "group_id",
                sa.Uuid(),
                sa.ForeignKey("feishu_groups.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=False),
            sa.UniqueConstraint(
                "group_id", "room_id", name="uq_feishu_group_room_scopes_group_id"
            ),
        )
        op.create_index(
            "ix_feishu_group_room_scopes_group_id",
            "feishu_group_room_scopes",
            ["group_id"],
        )
        op.create_index(
            "ix_feishu_group_room_scopes_room_id",
            "feishu_group_room_scopes",
            ["room_id"],
        )
    if "permission_audit_logs" not in tables:
        op.create_table(
            "permission_audit_logs",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("action", sa.String(120), nullable=False),
            sa.Column("target_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("target_type", sa.String(100), nullable=False),
            sa.Column("target_id", sa.String(200), nullable=True),
            sa.Column("before_value", sa.JSON(), nullable=True),
            sa.Column("after_value", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_permission_audit_logs_user_id", "permission_audit_logs", ["user_id"]
        )
        op.create_index(
            "ix_permission_audit_logs_action", "permission_audit_logs", ["action"]
        )
        op.create_index(
            "ix_permission_audit_logs_target_user_id",
            "permission_audit_logs",
            ["target_user_id"],
        )


def _ensure_role(
    bind: sa.Connection,
    roles: sa.Table,
    code: str,
    role_name: str,
    description: str,
    all_permissions: bool,
    legacy_name: str | None,
) -> Any:
    row = bind.execute(
        sa.select(roles).where((roles.c.role_code == code) | (roles.c.name == code))
    ).mappings().first()
    if row is None and legacy_name:
        row = bind.execute(sa.select(roles).where(roles.c.name == legacy_name)).mappings().first()
    values = {
        "name": code,
        "role_code": code,
        "role_name": role_name,
        "description": description,
        "all_permissions": all_permissions,
        "system_role": True,
        "active": True,
    }
    if row is None:
        role_id = _new_id(bind)
        bind.execute(roles.insert().values(id=role_id, **values))
        return role_id
    bind.execute(roles.update().where(roles.c.id == row["id"]).values(**values))
    return row["id"]


def _insert_once(
    bind: sa.Connection,
    table: sa.Table,
    where_clause: Any,
    values: dict[str, Any],
) -> None:
    if bind.scalar(sa.select(table.c.id).where(where_clause).limit(1)) is None:
        bind.execute(table.insert().values(id=_new_id(bind), **values))


def _seed_reference_data() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    roles = sa.Table("roles", metadata, autoload_with=bind)
    users = sa.Table("users", metadata, autoload_with=bind)
    rooms = sa.Table("rooms", metadata, autoload_with=bind)
    permissions = sa.Table("permissions", metadata, autoload_with=bind)
    role_permissions = sa.Table("role_permissions", metadata, autoload_with=bind)
    user_roles = sa.Table("user_roles", metadata, autoload_with=bind)
    resources = sa.Table("room_resources", metadata, autoload_with=bind)
    role_rooms = sa.Table("role_room_scopes", metadata, autoload_with=bind)
    groups = sa.Table("feishu_groups", metadata, autoload_with=bind)
    group_rooms = sa.Table("feishu_group_room_scopes", metadata, autoload_with=bind)
    now = datetime.now(UTC)

    # Backfill unknown legacy roles before the unique role_code constraint is relied on.
    for row in bind.execute(sa.select(roles)).mappings():
        if not row["role_code"]:
            bind.execute(
                roles.update()
                .where(roles.c.id == row["id"])
                .values(role_code=row["name"], role_name=row["description"] or row["name"])
            )

    permission_ids: dict[str, Any] = {}
    for code, name, description in PERMISSIONS:
        row = bind.execute(
            sa.select(permissions).where(permissions.c.permission_code == code)
        ).mappings().first()
        if row is None:
            permission_id = _new_id(bind)
            bind.execute(
                permissions.insert().values(
                    id=permission_id,
                    permission_code=code,
                    permission_name=name,
                    description=description,
                )
            )
        else:
            permission_id = row["id"]
        permission_ids[code] = permission_id

    role_ids: dict[str, Any] = {}
    for code, name, description, all_permissions, permission_codes, _groups, legacy in ROLES:
        role_id = _ensure_role(
            bind, roles, code, name, description, all_permissions, legacy
        )
        role_ids[code] = role_id
        for permission_code in permission_codes:
            _insert_once(
                bind,
                role_permissions,
                (role_permissions.c.role_id == role_id)
                & (role_permissions.c.permission_id == permission_ids[permission_code]),
                {"role_id": role_id, "permission_id": permission_ids[permission_code]},
            )

    bind.execute(
        users.update().where(users.c.role_name == "admin").values(role_name="developer")
    )
    bind.execute(
        users.update().where(users.c.role_name == "operator").values(role_name="live_manager")
    )
    user_room_permissions = sa.Table(
        "user_room_permissions", sa.MetaData(), autoload_with=bind
    )
    users_with_custom_scope = sa.select(user_room_permissions.c.user_id).distinct()
    bind.execute(
        users.update()
        .where(users.c.id.in_(users_with_custom_scope))
        .values(room_scope_mode="custom")
    )
    for user in bind.execute(sa.select(users.c.id, users.c.role_name)).mappings():
        role_id = role_ids.get(user["role_name"])
        if role_id is not None:
            _insert_once(
                bind,
                user_roles,
                (user_roles.c.user_id == user["id"]) & (user_roles.c.role_id == role_id),
                {"user_id": user["id"], "role_id": role_id},
            )

    resource_ids: dict[str, tuple[Any, str]] = {}
    for room in bind.execute(sa.select(rooms.c.id, rooms.c.name)).mappings():
        config = ROOM_CONFIG.get(room["name"])
        if config is None:
            continue
        category, permission_group = config
        existing = bind.execute(
            sa.select(resources).where(resources.c.room_id == room["id"])
        ).mappings().first()
        if existing is None:
            resource_id = _new_id(bind)
            bind.execute(
                resources.insert().values(
                    id=resource_id,
                    room_id=room["id"],
                    room_name=room["name"],
                    product_category=category,
                    permission_group=permission_group,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            resource_id = existing["id"]
        resource_ids[str(room["id"])] = (room["id"], permission_group)

    role_group_map = {code: groups_ for code, _n, _d, _a, _p, groups_, _l in ROLES}
    for role_code, groups_ in role_group_map.items():
        role_id = role_ids[role_code]
        for room_id, permission_group in resource_ids.values():
            if permission_group not in groups_:
                continue
            _insert_once(
                bind,
                role_rooms,
                (role_rooms.c.role_id == role_id) & (role_rooms.c.room_id == room_id),
                {"role_id": role_id, "room_id": room_id},
            )

    destination_columns = (
        ("hourly_comparison_rules", "push_chat_id"),
        ("alert_events", "push_chat_id"),
        ("anchor_trend_events", "destination_group"),
    )
    destinations: set[str] = set()
    for table_name, column_name in destination_columns:
        if table_name not in _table_names() or column_name not in _column_names(table_name):
            continue
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        for value in bind.scalars(
            sa.select(table.c[column_name]).where(table.c[column_name].is_not(None)).distinct()
        ):
            if isinstance(value, str) and value:
                destinations.add(value)
    for destination in destinations:
        group = bind.execute(
            sa.select(groups).where(groups.c.chat_id == destination)
        ).mappings().first()
        if group is None:
            group_id = _new_id(bind)
            bind.execute(
                groups.insert().values(
                    id=group_id,
                    name="迁移既有直播主管群",
                    chat_id=destination,
                    all_rooms=False,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            group_id = group["id"]
        for room_id, _permission_group in resource_ids.values():
            _insert_once(
                bind,
                group_rooms,
                (group_rooms.c.group_id == group_id) & (group_rooms.c.room_id == room_id),
                {"group_id": group_id, "room_id": room_id},
            )


def upgrade() -> None:
    _add_compatibility_columns()
    _create_tables()
    _seed_reference_data()


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()
    if "permission_audit_logs" in tables:
        audit_logs = sa.Table("permission_audit_logs", sa.MetaData(), autoload_with=bind)
        if bind.scalar(sa.select(sa.func.count()).select_from(audit_logs)):
            raise RuntimeError("permission_audit_logs 已有审计数据；拒绝破坏性降级")
    users = sa.Table("users", sa.MetaData(), autoload_with=bind)
    bind.execute(
        users.update().where(users.c.role_name == "developer").values(role_name="admin")
    )
    bind.execute(
        users.update().where(users.c.role_name == "live_manager").values(role_name="operator")
    )
    bind.execute(
        users.update()
        .where(users.c.role_name.in_(("water_pm", "primer_pm", "powder_pm")))
        .values(role_name="viewer")
    )
    for table_name in (
        "permission_audit_logs",
        "feishu_group_room_scopes",
        "feishu_groups",
        "role_room_scopes",
        "user_roles",
        "role_permissions",
        "permissions",
        "room_resources",
    ):
        if table_name in _table_names():
            op.drop_table(table_name)
    roles = sa.Table("roles", sa.MetaData(), autoload_with=bind)
    bind.execute(roles.delete().where(roles.c.name.in_(("water_pm", "primer_pm", "powder_pm"))))
    bind.execute(roles.update().where(roles.c.name == "developer").values(name="admin"))
    bind.execute(roles.update().where(roles.c.name == "live_manager").values(name="operator"))
    with op.batch_alter_table("users") as batch:
        for column_name in ("room_scope_mode", "status", "password_hash", "username"):
            if column_name in _column_names("users"):
                batch.drop_column(column_name)
    with op.batch_alter_table("roles") as batch:
        for column_name in (
            "active",
            "system_role",
            "all_permissions",
            "role_name",
            "role_code",
        ):
            if column_name in _column_names("roles"):
                batch.drop_column(column_name)
