from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.rbac import OPERATIONS_LEAD_PERMISSIONS
from app.auth.session import SessionCodec
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import Role, Room, User, UserRole
from app.services.permission_service import seed_permission_reference_data


def _room(name: str) -> Room:
    return Room(
        name=name,
        brand=None,
        category=None,
        active=True,
        confirmed=True,
        source_aliases=[],
    )


def test_administrator_can_manage_lower_roles_but_cannot_cross_hierarchy() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([_room("Mistine-水散粉"), _room("柏瑞美-妆前乳"), _room("柏瑞美-散粉")])
        session.commit()
        seed_permission_reference_data(session, None, include_test_accounts=True)
        admin_role = session.scalar(select(Role).where(Role.role_code == "admin"))
        operations_role = session.scalar(select(Role).where(Role.role_code == "operations_lead"))
        developer = session.scalar(select(User).where(User.username == "developer_test"))
        assert admin_role is not None and operations_role is not None and developer is not None
        admin = User(
            feishu_user_id="test:hierarchy-admin",
            username="hierarchy_admin",
            name="层级管理员",
            email=None,
            password_hash=None,
            status="active",
            room_scope_mode="role",
            role_name="admin",
            active=True,
        )
        operations = User(
            feishu_user_id="test:hierarchy-operations",
            username="hierarchy_operations",
            name="运营负责人",
            email=None,
            password_hash=None,
            status="active",
            room_scope_mode="role",
            role_name="operations_lead",
            active=True,
        )
        session.add_all([admin, operations])
        session.flush()
        session.add_all(
            [
                UserRole(user_id=admin.id, role_id=admin_role.id),
                UserRole(user_id=operations.id, role_id=operations_role.id),
            ]
        )
        session.commit()
        admin_id = admin.id
        operations_id = operations.id
        developer_id = developer.id
        operations_role_id = operations_role.id

    settings = Settings(
        app_env="test",
        dev_auth_bypass=False,
        jwt_secret="role-hierarchy-session-secret",  # noqa: S106
    )

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    csrf = "role-hierarchy-csrf"
    client.cookies.set(
        "live_ops_session",
        SessionCodec(settings).dumps({"user_id": str(admin_id), "csrf": csrf}),
    )
    client.cookies.set("live_ops_csrf", csrf)
    headers = {"X-CSRF-Token": csrf}
    try:
        overview = client.get("/api/v1/admin/permissions/overview")
        roles = {item["role_code"]: item for item in overview.json()["roles"]}
        users = {item["id"]: item for item in overview.json()["users"]}

        create_developer = client.post(
            "/api/v1/admin/permissions/users",
            headers=headers,
            json={
                "username": "forbidden_developer",
                "name": "禁止提升账号",
                "email": None,
                "password": "Forbidden-password-2026",
                "role_codes": ["developer"],
                "room_ids": None,
                "active": True,
            },
        )
        edit_developer_credentials = client.put(
            f"/api/v1/admin/permissions/users/{developer_id}/credentials",
            headers=headers,
            json={"username": "developer_test"},
        )
        edit_self_access = client.put(
            f"/api/v1/admin/permissions/users/{admin_id}/access",
            headers=headers,
            json={"role_codes": ["operations_lead"], "room_ids": None, "active": True},
        )
        elevate_operations = client.put(
            f"/api/v1/admin/permissions/users/{operations_id}/access",
            headers=headers,
            json={"role_codes": ["admin"], "room_ids": None, "active": True},
        )
        edit_operations_credentials = client.put(
            f"/api/v1/admin/permissions/users/{operations_id}/credentials",
            headers=headers,
            json={"username": "hierarchy_operations_renamed"},
        )
        overpowered_role = client.put(
            f"/api/v1/admin/permissions/roles/{operations_role_id}",
            headers=headers,
            json={
                "role_name": "运营负责人",
                "description": "不能被配置成隐藏管理员",
                "permission_codes": sorted(OPERATIONS_LEAD_PERMISSIONS | {"user.manage"}),
                "room_ids": roles["operations_lead"]["room_ids"],
                "active": True,
            },
        )
        allowed_role = client.put(
            f"/api/v1/admin/permissions/roles/{operations_role_id}",
            headers=headers,
            json={
                "role_name": "运营负责人",
                "description": "负责全部直播间运营",
                "permission_codes": sorted(OPERATIONS_LEAD_PERMISSIONS),
                "room_ids": roles["operations_lead"]["room_ids"],
                "active": True,
            },
        )
        created_pm = client.post(
            "/api/v1/admin/permissions/users",
            headers=headers,
            json={
                "username": "created_project_pm",
                "name": "新项目 PM",
                "email": None,
                "password": "Project-password-2026",
                "role_codes": ["water_pm"],
                "room_ids": None,
                "active": True,
            },
        )
        client.cookies.set(
            "live_ops_session",
            SessionCodec(settings).dumps(
                {"user_id": str(operations_id), "csrf": "operations-csrf"}
            ),
        )
        operations_sources = client.get("/api/v1/admin/sources")
        operations_audit = client.get("/api/v1/admin/audit-logs")
        operations_settings = client.get("/api/v1/admin/settings")
        operations_permissions = client.get("/api/v1/admin/permissions/overview")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert overview.status_code == 200
    assert overview.json()["current_actor_role_codes"] == ["admin"]
    assert overview.json()["current_actor_level"] == 400
    assert roles["developer"]["level"] == 500
    assert roles["developer"]["assignable"] is False
    assert roles["developer"]["editable"] is False
    assert roles["admin"]["level"] == 400
    assert roles["admin"]["assignable"] is False
    assert roles["admin"]["editable"] is False
    assert roles["operations_lead"]["level"] == 300
    assert roles["operations_lead"]["assignable"] is True
    assert roles["operations_lead"]["editable"] is True
    assert users[str(developer_id)]["can_edit_access"] is False
    assert users[str(developer_id)]["can_edit_credentials"] is False
    assert users[str(operations_id)]["can_edit_access"] is True
    assert users[str(operations_id)]["can_edit_credentials"] is True
    assert create_developer.status_code == 403
    assert create_developer.json()["detail"] == "不能授予同级或更高等级角色"
    assert edit_developer_credentials.status_code == 403
    assert edit_developer_credentials.json()["detail"] == "不能管理同级或更高等级账号"
    assert edit_self_access.status_code == 409
    assert edit_self_access.json()["detail"] == "不能修改当前登录账号的角色或状态"
    assert elevate_operations.status_code == 403
    assert elevate_operations.json()["detail"] == "不能授予同级或更高等级角色"
    assert edit_operations_credentials.status_code == 200
    assert edit_operations_credentials.json()["username"] == "hierarchy_operations_renamed"
    assert overpowered_role.status_code == 403
    assert "user.manage" in overpowered_role.json()["detail"]
    assert allowed_role.status_code == 200
    assert set(allowed_role.json()["permission_codes"]) == set(OPERATIONS_LEAD_PERMISSIONS)
    assert created_pm.status_code == 201
    assert created_pm.json()["role_codes"] == ["water_pm"]
    assert UUID(created_pm.json()["id"])
    assert operations_sources.status_code == 200
    assert operations_audit.status_code == 200
    assert operations_settings.status_code == 403
    assert operations_permissions.status_code == 403
