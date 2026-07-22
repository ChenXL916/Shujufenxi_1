from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa

import app.models  # noqa: F401 - register all current ORM tables for legacy bootstrap coverage
from app.db.base import Base

API_ROOT = Path(__file__).resolve().parents[1]


def _run_alembic(database: Path, *arguments: str) -> None:
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite+pysqlite:///{database.as_posix()}",
        "PYTHONPATH": str(API_ROOT),
    }
    subprocess.run(  # noqa: S603 - arguments are fixed test-controlled Alembic commands
        [sys.executable, "-m", "alembic", *arguments],
        cwd=API_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _schema(database: Path) -> dict[str, Any]:
    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    inspector = sa.inspect(engine)
    result: dict[str, Any] = {}
    for table_name in sorted(set(inspector.get_table_names()) - {"alembic_version"}):
        result[table_name] = {
            "columns": [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column["nullable"],
                    "default": column["default"],
                }
                for column in inspector.get_columns(table_name)
            ],
            "indexes": sorted(
                (
                    index["name"],
                    tuple(index["column_names"]),
                    bool(index["unique"]),
                )
                for index in inspector.get_indexes(table_name)
            ),
        }
    engine.dispose()
    return result


def _normalize(value: Any) -> Any:
    if isinstance(value, (date, datetime, Decimal, uuid.UUID)):
        return str(value)
    return value


def _rows(engine: sa.Engine, table_name: str) -> list[dict[str, Any]]:
    table = sa.Table(table_name, sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        rows = connection.execute(sa.select(table)).mappings()
        return sorted(
            ({key: _normalize(value) for key, value in row.items()} for row in rows),
            key=lambda row: str(row.get("id", row)),
        )


def test_migrations_are_frozen_reproducible_and_preserve_configuration(tmp_path: Path) -> None:
    database = tmp_path / "roundtrip.db"
    fresh_0001 = tmp_path / "fresh-0001.db"
    _run_alembic(database, "upgrade", "0001")
    _run_alembic(fresh_0001, "upgrade", "0001")
    assert _schema(database) == _schema(fresh_0001)

    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    metric_definitions = sa.Table("metric_definitions", sa.MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            metric_definitions.insert().values(
                metric_key="custom_metric",
                source_field_name="自定义指标",
                display_name="自定义指标",
                category="测试",
                unit="ratio",
                precision=2,
                scope="period",
                aggregation_strategy="SUM",
                numerator_metric_key=None,
                denominator_metric_key=None,
                chartable=True,
                comparable=True,
                alertable=False,
                direction="higher_better",
                default_visible=False,
                enabled=True,
                sort_order=1,
                description="迁移往返测试",
                id=uuid.uuid4().hex,
            )
        )
    engine.dispose()

    _run_alembic(database, "upgrade", "head")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    metadata = sa.MetaData()
    targets = sa.Table("room_metric_targets", metadata, autoload_with=engine)
    rules = sa.Table("hourly_comparison_rules", metadata, autoload_with=engine)
    metric_definitions = sa.Table("metric_definitions", metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            targets.update()
            .where(targets.c.room_name == "柏瑞美-散粉")
            .values(target_value=Decimal("8.88"), product_category="自定义目标")
        )
        connection.execute(
            rules.update()
            .where(rules.c.name == "1天小时ROI与消耗周期对比")
            .values(spend_increase_threshold=Decimal("9.99"), push_enabled=False)
        )
        connection.execute(
            metric_definitions.update()
            .where(metric_definitions.c.metric_key == "custom_metric")
            .values(
                supports_hourly_trend=True,
                supports_kline=True,
                is_cumulative=False,
            )
        )
    before_schema = _schema(database)
    before_rows = {
        name: _rows(engine, name)
        for name in ("room_metric_targets", "hourly_comparison_rules", "metric_definitions")
    }
    engine.dispose()

    _run_alembic(database, "downgrade", "0001")
    assert _schema(database) == _schema(fresh_0001)
    _run_alembic(database, "upgrade", "head")

    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    assert _schema(database) == before_schema
    after_rows = {
        name: _rows(engine, name)
        for name in ("room_metric_targets", "hourly_comparison_rules", "metric_definitions")
    }
    assert after_rows == before_rows
    assert _rows(engine, "audit_logs") == []
    engine.dispose()

    migration_source = (API_ROOT / "alembic" / "versions" / "0001_initial.py").read_text(
        encoding="utf-8"
    )
    assert "Base.metadata" not in migration_source
    assert "app.models" not in migration_source


def test_release_hardening_migration_updates_existing_conversion_definition(
    tmp_path: Path,
) -> None:
    database = tmp_path / "existing.db"
    _run_alembic(database, "upgrade", "0001")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    metric_definitions = sa.Table("metric_definitions", sa.MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            metric_definitions.insert().values(
                metric_key="period_view_conversion_rate",
                source_field_name="时段观看-成交率（人数）",
                display_name="时段观看-成交率（人数）",
                category="转化",
                unit="percent",
                precision=2,
                scope="period",
                aggregation_strategy="NONE",
                numerator_metric_key=None,
                denominator_metric_key=None,
                chartable=True,
                comparable=False,
                alertable=False,
                direction="higher_better",
                default_visible=False,
                enabled=True,
                sort_order=22,
                description="旧版定义",
                id=uuid.uuid4().hex,
            )
        )
    engine.dispose()

    _run_alembic(database, "upgrade", "head")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    metric_definitions = sa.Table("metric_definitions", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.select(metric_definitions).where(
                    metric_definitions.c.metric_key == "period_view_conversion_rate"
                )
            )
            .mappings()
            .one()
        )
    engine.dispose()

    assert row["scope"] == "derived"
    assert row["aggregation_strategy"] == "RATIO_OF_SUMS"
    assert row["numerator_metric_key"] == "period_buyers"
    assert row["denominator_metric_key"] == "period_viewers"
    assert row["comparable"] is True
    assert row["supports_hourly_trend"] is True
    assert row["supports_kline"] is True


def test_anchor_roi_alerting_migration_adds_rule_event_fields_and_targets(
    tmp_path: Path,
) -> None:
    database = tmp_path / "anchor-alerting.db"
    _run_alembic(database, "upgrade", "head")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    inspector = sa.inspect(engine)
    rule_columns = {column["name"] for column in inspector.get_columns("hourly_comparison_rules")}
    event_columns = {column["name"] for column in inspector.get_columns("alert_events")}

    assert {
        "spend_decrease_threshold",
        "applicable_anchors",
        "push_chat_id",
        "cooldown_minutes",
    } <= rule_columns
    assert {
        "comparison_rule_id",
        "anchor_id",
        "control_id",
        "current_spend",
        "baseline_spend",
        "spend_growth_rate",
        "current_roi",
        "baseline_roi",
        "roi_growth_rate",
        "roi_target",
        "roi_target_gap",
        "roi_target_reached",
        "notification_type",
        "message_color",
        "push_chat_id",
        "base_dedup_key",
        "state_version",
    } <= event_columns

    targets = sa.Table("room_metric_targets", sa.MetaData(), autoload_with=engine)
    rules = sa.Table("hourly_comparison_rules", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        target_rows = connection.execute(
            sa.select(
                targets.c.room_name,
                targets.c.product_category,
                targets.c.target_value,
            )
        ).all()
        default_rule = (
            connection.execute(sa.select(rules).where(rules.c.period_days == 1)).mappings().one()
        )
    engine.dispose()

    expected_targets = {
        ("柏瑞美-散粉", "散粉", Decimal("1.81")),
        ("柏瑞美-妆前乳", "妆前乳", Decimal("1.82")),
        ("Mistine-水散粉", "水散粉", Decimal("2.00")),
    }
    assert expected_targets <= {
        (name, category, Decimal(str(value))) for name, category, value in target_rows
    }
    assert Decimal(str(default_rule["spend_increase_threshold"])) == Decimal("0.30")
    assert Decimal(str(default_rule["spend_decrease_threshold"])) == Decimal("-0.30")
    assert Decimal(str(default_rule["roi_increase_threshold"])) == Decimal("0.30")
    assert Decimal(str(default_rule["roi_decrease_threshold"])) == Decimal("-0.30")
    assert Decimal(str(default_rule["minimum_coverage_rate"])) == Decimal("0.80")


def test_migrations_upgrade_unversioned_legacy_database_after_current_metadata_bootstrap(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-bootstrap.db"
    _run_alembic(database, "upgrade", "0001")

    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
    engine.dispose()

    _run_alembic(database, "stamp", "0001")
    _run_alembic(database, "upgrade", "head")

    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    inspector = sa.inspect(engine)
    alert_columns = {column["name"] for column in inspector.get_columns("alert_events")}
    rules = sa.Table("hourly_comparison_rules", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        default_rule = (
            connection.execute(sa.select(rules).where(rules.c.name == "1天小时ROI与消耗周期对比"))
            .mappings()
            .one()
        )
    engine.dispose()

    assert version == "0006_rbac_data_scope"
    assert {"period_days", "comparison_rule_id", "state_version"} <= alert_columns
    assert default_rule["rule_type"] == "hourly_comparison_legacy"
    assert default_rule["schedule_timezone"] == "Asia/Shanghai"


def test_rbac_migration_creates_and_seeds_authorization_schema(tmp_path: Path) -> None:
    database = tmp_path / "rbac.db"
    _run_alembic(database, "upgrade", "head")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    inspector = sa.inspect(engine)
    assert {
        "room_resources",
        "permissions",
        "role_permissions",
        "user_roles",
        "role_room_scopes",
        "feishu_groups",
        "feishu_group_room_scopes",
        "permission_audit_logs",
    } <= set(inspector.get_table_names())
    assert {"role_code", "role_name", "all_permissions", "system_role", "active"} <= {
        column["name"] for column in inspector.get_columns("roles")
    }
    assert {"username", "password_hash", "status", "room_scope_mode"} <= {
        column["name"] for column in inspector.get_columns("users")
    }
    roles = sa.Table("roles", sa.MetaData(), autoload_with=engine)
    permissions = sa.Table("permissions", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        role_codes = set(connection.scalars(sa.select(roles.c.role_code)))
        permission_codes = set(connection.scalars(sa.select(permissions.c.permission_code)))
    engine.dispose()
    assert {
        "developer",
        "live_manager",
        "water_pm",
        "primer_pm",
        "powder_pm",
    } <= role_codes
    assert len(permission_codes) == 16
    assert {"dashboard.view", "dashboard.export", "permission.manage"} <= permission_codes
