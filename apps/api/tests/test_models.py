from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import entities  # noqa: F401
from app.models.entities import (
    HourlyComparisonRule,
    MetricDefinition,
    Role,
    Room,
    RoomMetricTarget,
    ShiftRule,
    User,
)
from app.services.seed_service import seed_reference_data

ROOT = Path(__file__).resolve().parents[3]


def test_all_required_tables_create_on_sqlite() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())

    assert {
        "source_configs",
        "sync_runs",
        "raw_source_records",
        "rooms",
        "persons",
        "person_aliases",
        "live_points",
        "live_point_metrics",
        "anchor_schedules",
        "staff_schedules",
        "shift_rules",
        "hourly_facts",
        "hourly_metrics",
        "metric_definitions",
        "room_metric_targets",
        "hourly_comparison_rules",
        "alert_rules",
        "alert_events",
        "users",
        "roles",
        "user_room_permissions",
        "system_settings",
        "audit_logs",
    }.issubset(tables)


def test_reference_seed_is_complete_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Room(
                    name="柏瑞美-散粉",
                    brand="柏瑞美",
                    category="散粉",
                    active=True,
                    confirmed=True,
                    source_aliases=[],
                ),
                Room(
                    name="柏瑞美-妆前乳",
                    brand="柏瑞美",
                    category="妆前乳",
                    active=True,
                    confirmed=True,
                    source_aliases=[],
                ),
                Room(
                    name="Mistine-水散粉",
                    brand="Mistine",
                    category="水散粉",
                    active=True,
                    confirmed=True,
                    source_aliases=["Mistine 水散粉"],
                ),
            ]
        )
        session.commit()
        seed_reference_data(session, ROOT, "seed-admin@example.com")
        seed_reference_data(session, ROOT, "seed-admin@example.com")
        assert session.scalar(select(func.count()).select_from(MetricDefinition)) == 46
        assert session.scalar(select(func.count()).select_from(ShiftRule)) == 5
        assert session.scalar(select(func.count()).select_from(Role)) == 8
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(RoomMetricTarget)) == 3
        assert session.scalar(select(func.count()).select_from(HourlyComparisonRule)) == 1
        assert set(session.scalars(select(Role.role_code))) == {
            "developer",
            "admin",
            "operations_lead",
            "live_manager",
            "water_pm",
            "primer_pm",
            "powder_pm",
            "viewer",
        }
        seeded_admin = session.scalar(select(User).where(User.email == "seed-admin@example.com"))
        assert seeded_admin is not None
        assert seeded_admin.role_name == "developer"
        targets = {
            target.room_name: target.target_value
            for target in session.scalars(select(RoomMetricTarget))
        }
        assert targets == {
            "柏瑞美-散粉": Decimal("1.81"),
            "柏瑞美-妆前乳": Decimal("1.82"),
            "Mistine-水散粉": Decimal("2.00"),
        }
        roi = session.scalar(
            select(MetricDefinition).where(MetricDefinition.metric_key == "period_overall_roi")
        )
        cumulative = session.scalar(
            select(MetricDefinition).where(MetricDefinition.metric_key == "overall_roi")
        )
        assert roi is not None and roi.supports_hourly_trend and roi.supports_kline
        assert cumulative is not None and cumulative.is_cumulative
