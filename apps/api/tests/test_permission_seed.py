from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.entities import (
    Permission,
    Role,
    RoleRoomScope,
    Room,
    RoomResource,
    User,
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
            "live_manager",
            "water_pm",
            "primer_pm",
            "powder_pm",
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
        manager_role_id = session.scalar(select(Role.id).where(Role.role_code == "live_manager"))
        assert water_role_id is not None
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
