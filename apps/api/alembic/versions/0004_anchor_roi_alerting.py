"""Add anchor-level ROI/spend alert configuration and event evidence.

Revision ID: 0004_anchor_roi_alerting
Revises: 0003_release_hardening
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0004_anchor_roi_alerting"
down_revision = "0003_release_hardening"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(24, 8)
BACKUP_ACTION = "alembic_0004_downgrade_backup"
RULE_COLUMNS = (
    "spend_decrease_threshold",
    "applicable_anchors",
    "push_chat_id",
    "cooldown_minutes",
)
EVENT_COLUMNS = (
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
)


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _index_names(table_name: str) -> set[str]:
    return {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def _add_column(table_name: str, column: sa.Column[object]) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def _create_index(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=False)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    return value


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


def _new_id(bind: sa.Connection) -> uuid.UUID | str:
    value = uuid.uuid4()
    return value.hex if bind.dialect.name == "sqlite" else value


def _backup_extended_data() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    audit_logs = sa.Table("audit_logs", metadata, autoload_with=bind)
    rules = sa.Table("hourly_comparison_rules", metadata, autoload_with=bind)
    events = sa.Table("alert_events", metadata, autoload_with=bind)

    def rows(table: sa.Table, columns: tuple[str, ...]) -> list[dict[str, Any]]:
        selected = [table.c.id, *(table.c[name] for name in columns)]
        return [
            {key: _json_value(value) for key, value in row.items()}
            for row in bind.execute(sa.select(*selected)).mappings()
        ]

    bind.execute(audit_logs.delete().where(audit_logs.c.action == BACKUP_ACTION))
    bind.execute(
        audit_logs.insert().values(
            id=_new_id(bind),
            user_id=None,
            action=BACKUP_ACTION,
            object_type="alembic_migration",
            object_id=revision,
            before_summary=None,
            after_summary={
                "hourly_comparison_rules": rows(rules, RULE_COLUMNS),
                "alert_events": rows(events, EVENT_COLUMNS),
            },
            ip_address=None,
            created_at=datetime.now(UTC),
        )
    )


def _restore_extended_data() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    audit_logs = sa.Table("audit_logs", metadata, autoload_with=bind)
    backup = bind.execute(
        sa.select(audit_logs.c.id, audit_logs.c.after_summary)
        .where(audit_logs.c.action == BACKUP_ACTION)
        .order_by(audit_logs.c.created_at.desc())
        .limit(1)
    ).mappings().first()
    if backup is None:
        return

    payload = backup["after_summary"] or {}
    for table_name, columns in (
        ("hourly_comparison_rules", RULE_COLUMNS),
        ("alert_events", EVENT_COLUMNS),
    ):
        table = sa.Table(table_name, metadata, autoload_with=bind)
        for row in payload.get(table_name, []):
            row_id = _database_value(table.c.id, row["id"])
            values = {
                name: _database_value(table.c[name], row.get(name))
                for name in columns
                if name in row
            }
            bind.execute(table.update().where(table.c.id == row_id).values(**values))
    bind.execute(audit_logs.delete().where(audit_logs.c.id == backup["id"]))


def upgrade() -> None:
    for column in (
        sa.Column(
            "spend_decrease_threshold",
            MONEY,
            nullable=False,
            server_default="-0.30",
        ),
        sa.Column(
            "applicable_anchors", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("push_chat_id", sa.String(200), nullable=True),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="60"),
    ):
        _add_column("hourly_comparison_rules", column)

    for column in (
        sa.Column("comparison_rule_id", sa.Uuid(), nullable=True),
        sa.Column("anchor_id", sa.Uuid(), nullable=True),
        sa.Column("control_id", sa.Uuid(), nullable=True),
        sa.Column("current_spend", MONEY, nullable=True),
        sa.Column("baseline_spend", MONEY, nullable=True),
        sa.Column("spend_growth_rate", MONEY, nullable=True),
        sa.Column("current_roi", MONEY, nullable=True),
        sa.Column("baseline_roi", MONEY, nullable=True),
        sa.Column("roi_growth_rate", MONEY, nullable=True),
        sa.Column("roi_target", MONEY, nullable=True),
        sa.Column("roi_target_gap", MONEY, nullable=True),
        sa.Column("roi_target_reached", sa.Boolean(), nullable=True),
        sa.Column("notification_type", sa.String(50), nullable=True),
        sa.Column("message_color", sa.String(20), nullable=True),
        sa.Column("push_chat_id", sa.String(200), nullable=True),
        sa.Column("base_dedup_key", sa.String(64), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
    ):
        _add_column("alert_events", column)

    for name, columns in (
        ("ix_alert_events_comparison_rule_id", ["comparison_rule_id"]),
        ("ix_alert_events_anchor_id", ["anchor_id"]),
        ("ix_alert_events_base_dedup_key", ["base_dedup_key"]),
        ("ix_alert_events_notification_type", ["notification_type"]),
    ):
        _create_index(name, "alert_events", columns)
    _restore_extended_data()


def _drop_column(table_name: str, column_name: str) -> None:
    if column_name in _column_names(table_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column(column_name)


def downgrade() -> None:
    _backup_extended_data()
    for name in (
        "ix_alert_events_notification_type",
        "ix_alert_events_base_dedup_key",
        "ix_alert_events_anchor_id",
        "ix_alert_events_comparison_rule_id",
    ):
        if name in _index_names("alert_events"):
            op.drop_index(name, table_name="alert_events")
    for column_name in reversed(EVENT_COLUMNS):
        _drop_column("alert_events", column_name)
    for column_name in reversed(RULE_COLUMNS):
        _drop_column("hourly_comparison_rules", column_name)
