from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
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
    AuditLog,
    HourlyComparisonRule,
    Permission,
    PermissionAuditLog,
    Role,
    RolePermission,
    RoleRoomScope,
    Room,
    RoomMetricTarget,
    RoomResource,
    User,
    UserRole,
    UserRoomPermission,
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


def test_developer_manages_web_account_credentials_without_exposing_hash() -> None:
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
        credentials = client.put(
            f"/api/v1/admin/permissions/users/{user_id}/credentials",
            headers=headers,
            json={
                "username": " Renamed.Viewer ",
                "password": "Final-password-2026",
            },
        )
        with Session(engine) as session:
            rotated = session.get(User, UUID(user_id))
            assert rotated is not None
            password_after_rotation = rotated.password_hash
        rename_only = client.put(
            f"/api/v1/admin/permissions/users/{user_id}/credentials",
            headers=headers,
            json={"username": "Final.Viewer"},
        )
        conflict = client.put(
            f"/api/v1/admin/permissions/users/{user_id}/credentials",
            headers=headers,
            json={"username": "developer_test"},
        )
        with Session(engine) as session:
            stored = session.get(User, UUID(user_id))
            assert stored is not None
            stored.feishu_user_id = "ou_deleted_user"
            stored_hash = stored.password_hash
            audits = list(
                session.scalars(
                    select(PermissionAuditLog).where(PermissionAuditLog.target_user_id == stored.id)
                )
            )
            audit_actions = {audit.action for audit in audits}
            credential_audit_values = [
                (audit.before_value, audit.after_value)
                for audit in audits
                if audit.action == "user_credentials_updated"
            ]
            metric_target = RoomMetricTarget(
                room_id=None,
                room_name=None,
                product_category=None,
                metric_code="period_overall_roi",
                target_value=Decimal("2.50"),
                effective_start_date=None,
                effective_end_date=None,
                enabled=True,
                updated_by=stored.id,
            )
            comparison_rule = HourlyComparisonRule(
                name="保留删除用户历史引用",
                created_by=stored.id,
                updated_by=stored.id,
            )
            general_audit = AuditLog(
                user_id=stored.id,
                action="test_user_history",
                object_type="user",
                object_id=str(stored.id),
                before_summary=None,
                after_summary=None,
                ip_address=None,
            )
            session.add_all([metric_target, comparison_rule, general_audit])
            session.commit()
            metric_target_id = metric_target.id
            comparison_rule_id = comparison_rule.id
            general_audit_id = general_audit.id

        self_delete = client.delete(
            f"/api/v1/admin/permissions/users/{developer_id}",
            headers=headers,
        )
        deleted = client.delete(
            f"/api/v1/admin/permissions/users/{user_id}",
            headers=headers,
        )
        overview_after_delete = client.get("/api/v1/admin/permissions/overview")
        with Session(engine) as session:
            deleted_user = session.get(User, UUID(user_id))
            remaining_roles = list(
                session.scalars(select(UserRole).where(UserRole.user_id == UUID(user_id)))
            )
            remaining_room_scope = list(
                session.scalars(
                    select(UserRoomPermission).where(UserRoomPermission.user_id == UUID(user_id))
                )
            )
            kept_target = session.get(RoomMetricTarget, metric_target_id)
            kept_rule = session.get(HourlyComparisonRule, comparison_rule_id)
            kept_general_audit = session.get(AuditLog, general_audit_id)
            deletion_audit = session.scalar(
                select(PermissionAuditLog).where(
                    PermissionAuditLog.action == "user_deleted",
                    PermissionAuditLog.target_id == user_id,
                )
            )
            old_target_audits = list(
                session.scalars(
                    select(PermissionAuditLog).where(
                        PermissionAuditLog.target_id == user_id,
                        PermissionAuditLog.action != "user_deleted",
                    )
                )
            )

        client.cookies.set(
            "live_ops_session",
            SessionCodec(settings).dumps(
                {"user_id": user_id, "csrf": "csrf-deleted-user", "auth_mode": "password"}
            ),
        )
        deleted_login = client.get("/auth/me")
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
    assert credentials.status_code == 200
    assert credentials.json()["username"] == "renamed.viewer"
    assert rename_only.status_code == 200
    assert rename_only.json()["username"] == "final.viewer"
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "登录名已被其他用户使用"
    assert stored_hash is not None
    assert stored_hash == password_after_rotation
    assert not verify_password("Initial-password-2026", stored_hash)
    assert not verify_password("Replacement-password-2026", stored_hash)
    assert verify_password("Final-password-2026", stored_hash)
    assert audit_actions == {
        "user_created",
        "user_password_reset",
        "user_credentials_updated",
    }
    assert len(credential_audit_values) == 2
    assert all(
        "Final-password-2026" not in repr(audit_values) for audit_values in credential_audit_values
    )
    assert self_delete.status_code == 409
    assert self_delete.json()["detail"] == "不能删除当前登录账号"
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert deleted_user is not None
    assert deleted_user.active is False
    assert deleted_user.status == "deleted"
    assert deleted_user.username is None
    assert deleted_user.password_hash is None
    assert deleted_user.email is None
    assert deleted_user.feishu_user_id == "ou_deleted_user"
    assert remaining_roles == []
    assert remaining_room_scope == []
    assert overview_after_delete.status_code == 200
    assert user_id not in {item["id"] for item in overview_after_delete.json()["users"]}
    assert kept_target is not None and kept_target.updated_by == UUID(user_id)
    assert kept_rule is not None
    assert kept_rule.created_by == UUID(user_id)
    assert kept_rule.updated_by == UUID(user_id)
    assert kept_general_audit is not None and kept_general_audit.user_id == UUID(user_id)
    assert deletion_audit is not None
    assert deletion_audit.user_id == developer_id
    assert deletion_audit.target_user_id == UUID(user_id)
    assert deletion_audit.before_value is not None
    assert deletion_audit.before_value["username"] == "final.viewer"
    assert deletion_audit.after_value == {
        "deleted": True,
        "feishu_identity_blocked": True,
    }
    assert old_target_audits
    assert all(audit.target_user_id == UUID(user_id) for audit in old_target_audits)
    assert deleted_login.status_code == 401


def test_last_active_developer_cannot_be_deleted() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_permission_reference_data(session, None)
        developer = session.scalar(select(User).where(User.username == "developer_test"))
        assert developer is not None
        developer_id = developer.id

    settings = Settings(
        app_env="test",
        dev_auth_bypass=True,
        jwt_secret="last-developer-delete-test-secret",  # noqa: S106
    )

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    try:
        rejected = client.delete(f"/api/v1/admin/permissions/users/{developer_id}")
        with Session(engine) as session:
            preserved = session.get(User, developer_id)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "不能停用或移除最后一个开发者"
    assert preserved is not None
