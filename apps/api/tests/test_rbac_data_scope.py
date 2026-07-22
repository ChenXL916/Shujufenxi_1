from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.passwords import verify_password
from app.auth.session import SessionCodec
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import (
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


def test_water_pm_role_scope_is_resolved_and_explicit_room_escalation_is_forbidden() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        water = _room("Mistine-水散粉")
        primer = _room("柏瑞美-妆前乳")
        powder = _room("柏瑞美-散粉")
        session.add_all([water, primer, powder])
        session.flush()
        for room, category, group in (
            (water, "water_powder", "water_pm"),
            (primer, "primer", "primer_pm"),
            (powder, "powder", "powder_pm"),
        ):
            session.add(
                RoomResource(
                    room_id=room.id,
                    room_name=room.name,
                    product_category=category,
                    permission_group=group,
                    enabled=True,
                )
            )
        role = Role(name="water_pm", description="水散粉PM")
        permission = Permission(
            permission_code="dashboard.view",
            permission_name="查看经营数据",
            description="",
        )
        user = User(
            feishu_user_id="ou_water_pm_test",
            name="水散粉PM测试",
            avatar_url=None,
            email="water_pm_test@example.local",
            role_name="water_pm",
            active=True,
            last_login_at=None,
        )
        session.add_all([role, permission, user])
        session.flush()
        session.add_all(
            [
                UserRole(user_id=user.id, role_id=role.id),
                RolePermission(role_id=role.id, permission_id=permission.id),
                RoleRoomScope(role_id=role.id, room_id=water.id),
            ]
        )
        session.commit()
        user_id = user.id
        powder_id: UUID = powder.id

    settings = Settings(
        app_env="test",
        dev_auth_bypass=False,
        jwt_secret="rbac-test-session-secret",  # noqa: S106
    )

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    client.cookies.set(
        "live_ops_session",
        SessionCodec(settings).dumps({"user_id": str(user_id), "csrf": "csrf-test"}),
    )
    try:
        options = client.get("/api/v1/filters/options")
        escalation = client.get(
            "/api/v1/dashboard/overview",
            params={"room_ids": str(powder_id)},
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert options.status_code == 200
    assert [room["name"] for room in options.json()["rooms"]] == ["Mistine-水散粉"]
    assert escalation.status_code == 403
    assert escalation.json()["detail"] == "请求包含未授权直播间"


def test_only_developer_can_change_user_scope_and_change_is_audited() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        rooms = [_room("Mistine-水散粉"), _room("柏瑞美-妆前乳"), _room("柏瑞美-散粉")]
        session.add_all(rooms)
        session.commit()
        seed_permission_reference_data(session, "developer_test@example.local")
        developer = session.scalar(select(User).where(User.username == "developer_test"))
        water_user = session.scalar(select(User).where(User.username == "water_pm_test"))
        primer_room = session.scalar(select(Room).where(Room.name == "柏瑞美-妆前乳"))
        assert developer is not None and water_user is not None and primer_room is not None
        developer_id = developer.id
        water_user_id = water_user.id
        primer_room_id = primer_room.id

    settings = Settings(
        app_env="test",
        dev_auth_bypass=False,
        jwt_secret="rbac-admin-test-session-secret",  # noqa: S106
    )

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    access_path = f"/api/v1/admin/permissions/users/{water_user_id}/access"
    access_payload = {
        "role_codes": ["primer_pm"],
        "room_ids": [str(primer_room_id)],
        "active": True,
    }
    unauthenticated = client.put(
        access_path,
        headers={"X-CSRF-Token": "csrf-admin"},
        json=access_payload,
    )
    client.cookies.set(
        "live_ops_session",
        SessionCodec(settings).dumps({"user_id": str(developer_id), "csrf": "csrf-admin"}),
    )
    client.cookies.set("live_ops_csrf", "csrf-admin")
    try:
        rejected = client.put(access_path, json=access_payload)
        mismatched = client.put(
            access_path,
            headers={"X-CSRF-Token": "wrong-token"},
            json=access_payload,
        )
        with Session(engine) as session:
            unchanged_user = session.get(User, water_user_id)
            rejected_audit = session.scalar(
                select(PermissionAuditLog).where(PermissionAuditLog.action == "user_access_updated")
            )
            assert unchanged_user is not None
            assert unchanged_user.role_name == "water_pm"
            assert rejected_audit is None

        changed = client.put(
            access_path,
            headers={"X-CSRF-Token": "csrf-admin"},
            json=access_payload,
        )
        with Session(engine) as session:
            audit = session.scalar(
                select(PermissionAuditLog).where(PermissionAuditLog.action == "user_access_updated")
            )
            water_user = session.get(User, water_user_id)
            assert water_user is not None
            assert audit is not None
            assert audit.user_id == developer_id
            assert audit.target_user_id == water_user_id
            assert water_user.role_name == "primer_pm"
            assert water_user.room_scope_mode == "custom"

        with Session(engine) as session:
            water_pm = session.scalar(select(User).where(User.username == "water_pm_test"))
            assert water_pm is not None
            water_pm_id = water_pm.id
        client.cookies.set(
            "live_ops_session",
            SessionCodec(settings).dumps({"user_id": str(water_pm_id), "csrf": "csrf-pm"}),
        )
        client.cookies.set("live_ops_csrf", "csrf-pm")
        ordinary_forbidden = client.put(
            access_path,
            headers={"X-CSRF-Token": "csrf-pm"},
            json=access_payload,
        )
        forbidden = client.get("/api/v1/admin/permissions/overview")
        with Session(engine) as session:
            audit_count = len(
                list(
                    session.scalars(
                        select(PermissionAuditLog).where(
                            PermissionAuditLog.action == "user_access_updated"
                        )
                    )
                )
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert unauthenticated.status_code == 401
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "CSRF 校验失败"
    assert mismatched.status_code == 403
    assert mismatched.json()["detail"] == "CSRF 校验失败"
    assert changed.status_code == 200
    assert changed.json()["role_codes"] == ["primer_pm"]
    assert changed.json()["room_ids"] == [str(primer_room_id)]
    assert ordinary_forbidden.status_code == 403
    assert ordinary_forbidden.json()["detail"] == "权限不足"
    assert audit_count == 1
    assert forbidden.status_code == 403


def test_developer_creates_web_account_and_resets_password_without_exposing_hash() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        rooms = [_room("Mistine-水散粉"), _room("柏瑞美-妆前乳"), _room("柏瑞美-散粉")]
        session.add_all(rooms)
        session.commit()
        seed_permission_reference_data(session, "developer_test@example.local")
        developer = session.scalar(select(User).where(User.username == "developer_test"))
        assert developer is not None
        developer_id = developer.id
    settings = Settings(
        app_env="test",
        dev_auth_bypass=False,
        jwt_secret="web-account-admin-test-secret",  # noqa: S106
    )

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    client.cookies.set(
        "live_ops_session",
        SessionCodec(settings).dumps({"user_id": str(developer_id), "csrf": "csrf-account-admin"}),
    )
    client.cookies.set("live_ops_csrf", "csrf-account-admin")
    headers = {"X-CSRF-Token": "csrf-account-admin"}
    try:
        created = client.post(
            "/api/v1/admin/permissions/users",
            headers=headers,
            json={
                "username": " Room.Viewer ",
                "name": "网页受限查看者",
                "email": None,
                "password": "Initial-password-2026",
                "role_codes": ["viewer"],
                "room_ids": [],
                "active": True,
            },
        )
        user_id = created.json()["id"]
        reset = client.put(
            f"/api/v1/admin/permissions/users/{user_id}/password",
            headers=headers,
            json={"password": "Replacement-password-2026"},
        )
        with Session(engine) as session:
            stored = session.get(User, UUID(user_id))
            assert stored is not None
            stored_hash = stored.password_hash
            audits = list(
                session.scalars(
                    select(PermissionAuditLog).where(PermissionAuditLog.target_user_id == stored.id)
                )
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert created.status_code == 201
    assert created.json()["username"] == "room.viewer"
    assert created.json()["email"] is None
    assert created.json()["password_login_enabled"] is True
    assert "password" not in created.json()
    assert "password_hash" not in created.json()
    assert reset.status_code == 200
    assert stored_hash is not None
    assert not verify_password("Initial-password-2026", stored_hash)
    assert verify_password("Replacement-password-2026", stored_hash)
    assert {audit.action for audit in audits} == {"user_created", "user_password_reset"}
