from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.entities import (
    Permission,
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


def test_permission_seed_is_idempotent_and_binds_exact_room_resources() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([_room("Mistine 水散粉"), _room("柏瑞美-妆前乳"), _room("柏瑞美-散粉")])
        session.commit()

        seed_permission_reference_data(session, "dev@example.com", include_test_accounts=True)
        seed_permission_reference_data(session, "dev@example.com", include_test_accounts=True)

        assert set(session.scalars(select(Role.role_code))) >= {
            "developer",
            "admin",
            "operations_lead",
            "live_manager",
            "water_pm",
            "primer_pm",
            "powder_pm",
            "viewer",
        }
        assert session.scalar(select(func.count(Permission.id))) == 16
        resources = {
            row.room_name: (row.product_category, row.permission_group)
            for row in session.scalars(select(RoomResource))
        }
        assert resources == {
            "Mistine 水散粉": ("water_powder", "water_pm"),
            "柏瑞美-妆前乳": ("primer", "primer_pm"),
            "柏瑞美-散粉": ("powder", "powder_pm"),
        }
        water_role_id = session.scalar(select(Role.id).where(Role.role_code == "water_pm"))
        admin_role_id = session.scalar(select(Role.id).where(Role.role_code == "admin"))
        operations_role_id = session.scalar(
            select(Role.id).where(Role.role_code == "operations_lead")
        )
        manager_role_id = session.scalar(select(Role.id).where(Role.role_code == "live_manager"))
        assert water_role_id is not None
        assert admin_role_id is not None
        assert operations_role_id is not None
        assert manager_role_id is not None
        assert (
            session.scalar(
                select(func.count(RoleRoomScope.id)).where(RoleRoomScope.role_id == water_role_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(RoleRoomScope.id)).where(RoleRoomScope.role_id == manager_role_id)
            )
            == 3
        )
        assert (
            session.scalar(
                select(func.count(RoleRoomScope.id)).where(RoleRoomScope.role_id == admin_role_id)
            )
            == 3
        )
        assert (
            session.scalar(
                select(func.count(RoleRoomScope.id)).where(
                    RoleRoomScope.role_id == operations_role_id
                )
            )
            == 3
        )
        admin_permissions = set(
            session.scalars(
                select(Permission.permission_code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == admin_role_id)
            )
        )
        operations_permissions = set(
            session.scalars(
                select(Permission.permission_code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == operations_role_id)
            )
        )
        assert "permission.manage" in admin_permissions
        assert "database.manage" not in admin_permissions
        assert operations_permissions == {
            "dashboard.view",
            "dashboard.export",
            "alert.view",
            "alert.manage",
            "roi_target.manage",
            "alert_rule.manage",
            "data_source.manage",
            "sync.run",
            "audit.view",
        }
        assert set(
            session.scalars(select(User.username).where(User.username.like("%_test", escape="!")))
        ) == {
            "developer_test",
            "live_manager_test",
            "water_pm_test",
            "primer_pm_test",
            "powder_pm_test",
        }
    engine.dispose()


def test_legacy_admin_is_not_kept_as_developer_after_formal_admin_role_is_seeded() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_permission_reference_data(session, None, include_test_accounts=False)
        developer_role = session.scalar(select(Role).where(Role.role_code == "developer"))
        assert developer_role is not None
        legacy_admin = User(
            feishu_user_id="legacy:admin",
            username="legacy_admin",
            name="旧管理员",
            email=None,
            password_hash=None,
            status="active",
            room_scope_mode="role",
            role_name="admin",
            active=True,
        )
        session.add(legacy_admin)
        session.flush()
        session.add(UserRole(user_id=legacy_admin.id, role_id=developer_role.id))
        session.commit()

        seed_permission_reference_data(session, None, include_test_accounts=False)
        role_codes = set(
            session.scalars(
                select(Role.role_code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == legacy_admin.id)
            )
        )

        assert legacy_admin.role_name == "admin"
        assert role_codes == {"admin"}
    engine.dispose()
