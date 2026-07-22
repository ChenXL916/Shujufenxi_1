"""Add 24-hour ROI/spend comparison configuration and alert context.

Revision ID: 0002_hourly_comparison
Revises: 0001
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0002_hourly_comparison"
down_revision = "0001"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(24, 8)
BACKUP_ACTION = "alembic_0002_downgrade_backup"
METRIC_FEATURE_COLUMNS = (
    "supports_hourly_trend",
    "supports_kline",
    "is_cumulative",
)
ALERT_CONTEXT_COLUMNS = (
    "period_days",
    "current_period_start",
    "current_period_end",
    "comparison_period_start",
    "comparison_period_end",
    "alert_type",
    "metric_codes",
    "status_code",
    "status_reasons",
    "comparison_context",
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _add_column(table_name: str, column: sa.Column[object]) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def _create_index(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=False)


def _new_id(bind: sa.Connection) -> uuid.UUID | str:
    value = uuid.uuid4()
    return value.hex if bind.dialect.name == "sqlite" else value


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, Decimal, uuid.UUID)):
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    return value


def _serialized_rows(
    bind: sa.Connection, table: sa.Table, columns: tuple[str, ...] | None = None
) -> list[dict[str, Any]]:
    selected = [table.c[name] for name in columns] if columns else list(table.c)
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in bind.execute(sa.select(*selected)).mappings()
    ]


def _database_value(column: sa.Column[Any], value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, sa.DateTime):
        return datetime.fromisoformat(str(value))
    if isinstance(column.type, sa.Date):
        return date.fromisoformat(str(value))
    if isinstance(column.type, sa.Numeric):
        return Decimal(str(value))
    if isinstance(column.type, sa.Uuid) and not isinstance(value, uuid.UUID):
        return uuid.UUID(str(value))
    return value


def _database_row(table: sa.Table, row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _database_value(table.c[key], value) for key, value in row.items() if key in table.c
    }


def _backup_added_data() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    audit_logs = sa.Table("audit_logs", metadata, autoload_with=bind)
    targets = sa.Table("room_metric_targets", metadata, autoload_with=bind)
    rules = sa.Table("hourly_comparison_rules", metadata, autoload_with=bind)
    metric_definitions = sa.Table("metric_definitions", metadata, autoload_with=bind)
    alert_events = sa.Table("alert_events", metadata, autoload_with=bind)
    payload = {
        "room_metric_targets": _serialized_rows(bind, targets),
        "hourly_comparison_rules": _serialized_rows(bind, rules),
        "metric_definitions": _serialized_rows(
            bind,
            metric_definitions,
            ("metric_key", *METRIC_FEATURE_COLUMNS),
        ),
        "alert_events": _serialized_rows(
            bind,
            alert_events,
            ("id", *ALERT_CONTEXT_COLUMNS),
        ),
    }
    bind.execute(audit_logs.delete().where(audit_logs.c.action == BACKUP_ACTION))
    bind.execute(
        audit_logs.insert().values(
            id=_new_id(bind),
            user_id=None,
            action=BACKUP_ACTION,
            object_type="alembic_migration",
            object_id=revision,
            before_summary=None,
            after_summary=payload,
            ip_address=None,
            created_at=datetime.now(UTC),
        )
    )


def _restore_added_data() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    audit_logs = sa.Table("audit_logs", metadata, autoload_with=bind)
    backup = (
        bind.execute(
            sa.select(audit_logs.c.id, audit_logs.c.after_summary)
            .where(audit_logs.c.action == BACKUP_ACTION)
            .order_by(audit_logs.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if backup is None:
        return
    payload = backup["after_summary"] or {}
    targets = sa.Table("room_metric_targets", metadata, autoload_with=bind)
    rules = sa.Table("hourly_comparison_rules", metadata, autoload_with=bind)
    metric_definitions = sa.Table("metric_definitions", metadata, autoload_with=bind)
    alert_events = sa.Table("alert_events", metadata, autoload_with=bind)
    for table, key in (
        (targets, "room_metric_targets"),
        (rules, "hourly_comparison_rules"),
    ):
        rows = [_database_row(table, row) for row in payload.get(key, [])]
        if rows:
            bind.execute(table.insert(), rows)
    for row in payload.get("metric_definitions", []):
        values = _database_row(metric_definitions, row)
        metric_key = values.pop("metric_key")
        bind.execute(
            metric_definitions.update()
            .where(metric_definitions.c.metric_key == metric_key)
            .values(**values)
        )
    for row in payload.get("alert_events", []):
        values = _database_row(alert_events, row)
        event_id = values.pop("id")
        bind.execute(alert_events.update().where(alert_events.c.id == event_id).values(**values))
    bind.execute(audit_logs.delete().where(audit_logs.c.id == backup["id"]))


def _create_tables() -> None:
    if "room_metric_targets" not in _table_names():
        op.create_table(
            "room_metric_targets",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=True),
            sa.Column("room_name", sa.String(200), nullable=True),
            sa.Column("product_category", sa.String(200), nullable=True),
            sa.Column("metric_code", sa.String(100), nullable=False),
            sa.Column("target_value", MONEY, nullable=False),
            sa.Column("effective_start_date", sa.Date(), nullable=True),
            sa.Column("effective_end_date", sa.Date(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    for name, columns in (
        ("ix_room_metric_targets_room_id", ["room_id"]),
        ("ix_room_metric_targets_room_name", ["room_name"]),
        ("ix_room_metric_targets_product_category", ["product_category"]),
        ("ix_room_metric_targets_metric_code", ["metric_code"]),
        (
            "ix_room_metric_targets_lookup",
            ["metric_code", "enabled", "effective_start_date", "effective_end_date"],
        ),
    ):
        _create_index(name, "room_metric_targets", columns)

    if "hourly_comparison_rules" not in _table_names():
        op.create_table(
            "hourly_comparison_rules",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(200), nullable=False, unique=True),
            sa.Column("period_days", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("spend_increase_threshold", MONEY, nullable=False, server_default="0.30"),
            sa.Column("roi_increase_threshold", MONEY, nullable=False, server_default="0.30"),
            sa.Column("roi_decrease_threshold", MONEY, nullable=False, server_default="-0.30"),
            sa.Column("minimum_spend", MONEY, nullable=False, server_default="0"),
            sa.Column("minimum_orders", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("minimum_coverage_rate", MONEY, nullable=False, server_default="0.80"),
            sa.Column(
                "evaluation_delay_minutes", sa.Integer(), nullable=False, server_default="15"
            ),
            sa.Column("applicable_rooms", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def _extend_existing_tables() -> None:
    for column in (
        sa.Column("supports_hourly_trend", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_kline", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_cumulative", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        _add_column("metric_definitions", column)

    for column in (
        sa.Column("period_days", sa.Integer(), nullable=True),
        sa.Column("current_period_start", sa.Date(), nullable=True),
        sa.Column("current_period_end", sa.Date(), nullable=True),
        sa.Column("comparison_period_start", sa.Date(), nullable=True),
        sa.Column("comparison_period_end", sa.Date(), nullable=True),
        sa.Column("alert_type", sa.String(100), nullable=True),
        sa.Column("metric_codes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status_code", sa.String(100), nullable=True),
        sa.Column("status_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("comparison_context", sa.JSON(), nullable=True),
    ):
        _add_column("alert_events", column)
    _create_index("ix_alert_events_alert_type", "alert_events", ["alert_type"])
    _create_index("ix_alert_events_status_code", "alert_events", ["status_code"])

    for name, columns in (
        (
            "ix_hourly_facts_date_hour_room",
            ["business_date", "hour_order", "room_id"],
        ),
        (
            "ix_hourly_facts_room_date_hour",
            ["room_id", "business_date", "hour_order"],
        ),
        (
            "ix_hourly_facts_date_anchor_hour",
            ["business_date", "actual_anchor_canonical", "hour_order"],
        ),
        (
            "ix_hourly_facts_date_control_hour",
            ["business_date", "actual_control_canonical", "hour_order"],
        ),
    ):
        _create_index(name, "hourly_facts", columns)


def _seed_reference_rows() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    rooms = sa.Table("rooms", metadata, autoload_with=bind)
    targets = sa.Table("room_metric_targets", metadata, autoload_with=bind)
    rules = sa.Table("hourly_comparison_rules", metadata, autoload_with=bind)
    now = datetime.now(UTC)

    room_map = {row.name: row.id for row in bind.execute(sa.select(rooms.c.id, rooms.c.name))}
    for room_name, category, value in (
        ("柏瑞美-散粉", "散粉", Decimal("1.81")),
        ("柏瑞美-妆前乳", "妆前乳", Decimal("1.82")),
        ("Mistine-水散粉", "水散粉", Decimal("2.00")),
    ):
        existing = bind.scalar(
            sa.select(targets.c.id).where(
                targets.c.room_name == room_name,
                targets.c.metric_code == "period_overall_roi",
                targets.c.effective_start_date.is_(None),
                targets.c.effective_end_date.is_(None),
            )
        )
        values = {
            "room_id": room_map.get(room_name),
            "room_name": room_name,
            "product_category": category,
            "metric_code": "period_overall_roi",
            "target_value": value,
            "effective_start_date": None,
            "effective_end_date": None,
            "enabled": True,
            "updated_by": None,
            "updated_at": now,
        }
        if existing is None:
            bind.execute(targets.insert().values(id=_new_id(bind), created_at=now, **values))

    rule_name = "1天小时ROI与消耗周期对比"
    existing_rule = bind.scalar(sa.select(rules.c.id).where(rules.c.name == rule_name))
    rule_values = {
        "period_days": 1,
        "spend_increase_threshold": Decimal("0.30"),
        "roi_increase_threshold": Decimal("0.30"),
        "roi_decrease_threshold": Decimal("-0.30"),
        "minimum_spend": Decimal(0),
        "minimum_orders": 0,
        "minimum_coverage_rate": Decimal("0.80"),
        "evaluation_delay_minutes": 15,
        "applicable_rooms": [],
        "enabled": True,
        "push_enabled": True,
        "created_by": None,
        "updated_by": None,
        "updated_at": now,
    }
    later_schema_defaults = {
        "rule_type": "hourly_comparison_legacy",
        "spend_decrease_threshold": Decimal("-0.30"),
        "minimum_effective_hours": 1,
        "push_schedule": "daily@09:30",
        "schedule_timezone": "Asia/Shanghai",
        "applicable_anchors": [],
        "push_chat_id": None,
        "send_rise": True,
        "send_fall": True,
        "rise_limit": 10,
        "fall_limit": 10,
        "send_empty_summary": False,
        "allow_force_resend": True,
        "push_retry_limit": 3,
        "cooldown_minutes": 60,
    }
    rule_values.update(
        {name: value for name, value in later_schema_defaults.items() if name in rules.c}
    )
    if existing_rule is None:
        bind.execute(
            rules.insert().values(id=_new_id(bind), name=rule_name, created_at=now, **rule_values)
        )


def upgrade() -> None:
    _create_tables()
    _extend_existing_tables()
    _restore_added_data()
    _seed_reference_rows()


def _drop_column_if_present(table_name: str, column_name: str) -> None:
    if column_name in _column_names(table_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column(column_name)


def downgrade() -> None:
    _backup_added_data()
    for name in (
        "ix_hourly_facts_date_control_hour",
        "ix_hourly_facts_date_anchor_hour",
        "ix_hourly_facts_room_date_hour",
        "ix_hourly_facts_date_hour_room",
    ):
        if name in _index_names("hourly_facts"):
            op.drop_index(name, table_name="hourly_facts")
    for name in ("ix_alert_events_status_code", "ix_alert_events_alert_type"):
        if name in _index_names("alert_events"):
            op.drop_index(name, table_name="alert_events")
    for column_name in (
        "comparison_context",
        "status_reasons",
        "status_code",
        "metric_codes",
        "alert_type",
        "comparison_period_end",
        "comparison_period_start",
        "current_period_end",
        "current_period_start",
        "period_days",
    ):
        _drop_column_if_present("alert_events", column_name)
    for column_name in ("is_cumulative", "supports_kline", "supports_hourly_trend"):
        _drop_column_if_present("metric_definitions", column_name)
    if "hourly_comparison_rules" in _table_names():
        op.drop_table("hourly_comparison_rules")
    if "room_metric_targets" in _table_names():
        op.drop_table("room_metric_targets")
