"""Add batched anchor trend summary rules, events, and items.

Revision ID: 0005_anchor_trend_summaries
Revises: 0004_anchor_roi_alerting
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0005_anchor_trend_summaries"
down_revision = "0004_anchor_roi_alerting"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(24, 8)
BACKUP_ACTION = "alembic_0005_downgrade_backup"
RULE_COLUMNS = (
    ("rule_type", sa.String(60), "hourly_comparison_legacy"),
    ("minimum_effective_hours", sa.Integer(), "1"),
    ("push_schedule", sa.String(80), "daily@09:30"),
    ("schedule_timezone", sa.String(80), "Asia/Shanghai"),
    ("send_rise", sa.Boolean(), sa.true()),
    ("send_fall", sa.Boolean(), sa.true()),
    ("rise_limit", sa.Integer(), "10"),
    ("fall_limit", sa.Integer(), "10"),
    ("send_empty_summary", sa.Boolean(), sa.false()),
    ("allow_force_resend", sa.Boolean(), sa.true()),
    ("push_retry_limit", sa.Integer(), "3"),
)
ALERT_RULE_COLUMNS = (
    ("system_record_enabled", sa.Boolean(), sa.true()),
    ("business_push_enabled", sa.Boolean(), sa.true()),
    ("technical_push_enabled", sa.Boolean(), sa.false()),
    ("technical_chat_id", sa.String(200), None),
)
DEFAULT_RULE_NAMES = ("主播3天趋势通知", "主播7天趋势通知")
DATA_QUALITY_RULE_TYPES = (
    "data_delay",
    "missing_data",
    "unentered_data",
    "delayed_entry",
    "missing_hourly_record",
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


def _backup_extended_rule_data() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    audit_logs = sa.Table("audit_logs", metadata, autoload_with=bind)
    rules = sa.Table("hourly_comparison_rules", metadata, autoload_with=bind)
    alert_rules = sa.Table("alert_rules", metadata, autoload_with=bind)

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
                "hourly_comparison_rules": rows(
                    rules, tuple(name for name, _type, _default in RULE_COLUMNS)
                ),
                "alert_rules": rows(
                    alert_rules,
                    tuple(name for name, _type, _default in ALERT_RULE_COLUMNS),
                ),
            },
            ip_address=None,
            created_at=datetime.now(UTC),
        )
    )


def _restore_extended_rule_data() -> None:
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
    for table_name, definitions in (
        ("hourly_comparison_rules", RULE_COLUMNS),
        ("alert_rules", ALERT_RULE_COLUMNS),
    ):
        table = sa.Table(table_name, metadata, autoload_with=bind)
        for row in payload.get(table_name, []):
            row_id = _database_value(table.c.id, row["id"])
            values = {
                name: _database_value(table.c[name], row.get(name))
                for name, _type, _default in definitions
                if name in row
            }
            bind.execute(table.update().where(table.c.id == row_id).values(**values))
    bind.execute(audit_logs.delete().where(audit_logs.c.id == backup["id"]))


def _extend_rules() -> None:
    for name, type_, default in RULE_COLUMNS:
        _add_column(
            "hourly_comparison_rules",
            sa.Column(name, type_, nullable=False, server_default=default),
        )
    _create_index(
        "ix_hourly_comparison_rules_rule_type",
        "hourly_comparison_rules",
        ["rule_type"],
    )
    for name, type_, default in ALERT_RULE_COLUMNS:
        _add_column(
            "alert_rules",
            sa.Column(name, type_, nullable=default is None, server_default=default),
        )


def _create_event_tables() -> None:
    if "anchor_trend_events" not in _table_names():
        op.create_table(
            "anchor_trend_events",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "rule_id",
                sa.Uuid(),
                sa.ForeignKey("hourly_comparison_rules.id"),
                nullable=False,
            ),
            sa.Column("period_days", sa.Integer(), nullable=False),
            sa.Column("current_period_start", sa.Date(), nullable=False),
            sa.Column("current_period_end", sa.Date(), nullable=False),
            sa.Column("baseline_period_start", sa.Date(), nullable=False),
            sa.Column("baseline_period_end", sa.Date(), nullable=False),
            sa.Column("notification_type", sa.String(60), nullable=False),
            sa.Column("destination_group", sa.String(200), nullable=True),
            sa.Column("room_scope", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("anchor_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("message_snapshot", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("dedup_key", sa.String(64), nullable=False, unique=True),
            sa.Column("push_status", sa.String(24), nullable=False, server_default="pending"),
            sa.Column("push_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("push_error", sa.Text(), nullable=True),
            sa.Column("manual_resend", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "source_event_id",
                sa.Uuid(),
                sa.ForeignKey("anchor_trend_events.id"),
                nullable=True,
            ),
            sa.Column("resend_reason", sa.Text(), nullable=True),
            sa.Column("operated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    for name, columns in (
        ("ix_anchor_trend_events_rule_id", ["rule_id"]),
        ("ix_anchor_trend_events_period_days", ["period_days"]),
        ("ix_anchor_trend_events_current_period_end", ["current_period_end"]),
        ("ix_anchor_trend_events_notification_type", ["notification_type"]),
        ("ix_anchor_trend_events_destination_group", ["destination_group"]),
        ("ix_anchor_trend_events_push_status", ["push_status"]),
        ("ix_anchor_trend_events_source_event_id", ["source_event_id"]),
    ):
        _create_index(name, "anchor_trend_events", columns)

    if "anchor_trend_items" not in _table_names():
        op.create_table(
            "anchor_trend_items",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "event_id",
                sa.Uuid(),
                sa.ForeignKey("anchor_trend_events.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("rank", sa.Integer(), nullable=True),
            sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id"), nullable=False),
            sa.Column("room_name", sa.String(200), nullable=False),
            sa.Column("anchor_id", sa.Uuid(), nullable=True),
            sa.Column("anchor_name", sa.String(200), nullable=False),
            sa.Column("control_names", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("trend_type", sa.String(24), nullable=False),
            sa.Column("current_amount", MONEY, nullable=True),
            sa.Column("baseline_amount", MONEY, nullable=True),
            sa.Column("current_spend", MONEY, nullable=True),
            sa.Column("baseline_spend", MONEY, nullable=True),
            sa.Column("spend_growth_rate", MONEY, nullable=True),
            sa.Column("current_roi", MONEY, nullable=True),
            sa.Column("baseline_roi", MONEY, nullable=True),
            sa.Column("roi_growth_rate", MONEY, nullable=True),
            sa.Column("current_orders", MONEY, nullable=True),
            sa.Column("baseline_orders", MONEY, nullable=True),
            sa.Column("current_order_cost", MONEY, nullable=True),
            sa.Column("baseline_order_cost", MONEY, nullable=True),
            sa.Column("roi_target", MONEY, nullable=True),
            sa.Column("roi_target_gap", MONEY, nullable=True),
            sa.Column("roi_target_reached", sa.Boolean(), nullable=True),
            sa.Column("primary_status", sa.String(100), nullable=False),
            sa.Column("primary_status_name", sa.String(100), nullable=False),
            sa.Column("reason_codes", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("reasons", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("major_rise_hours", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("major_fall_hours", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("major_spend_hours", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("hourly_details", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("current_effective_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("baseline_effective_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_effective_hours", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("baseline_effective_hours", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_coverage_rate", MONEY, nullable=True),
            sa.Column("baseline_coverage_rate", MONEY, nullable=True),
            sa.Column("comparison_basis", sa.String(300), nullable=False),
            sa.Column("suggestion", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("event_id", "room_id", "anchor_name"),
        )
    for name, columns in (
        ("ix_anchor_trend_items_event_id", ["event_id"]),
        ("ix_anchor_trend_items_room_id", ["room_id"]),
        ("ix_anchor_trend_items_anchor_id", ["anchor_id"]),
        ("ix_anchor_trend_items_anchor_name", ["anchor_name"]),
        ("ix_anchor_trend_items_trend_type", ["trend_type"]),
        ("ix_anchor_trend_items_primary_status", ["primary_status"]),
        ("ix_anchor_trend_items_scope", ["room_id", "anchor_name", "trend_type"]),
    ):
        _create_index(name, "anchor_trend_items", columns)


def _seed_default_rules() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    rules = sa.Table("hourly_comparison_rules", metadata, autoload_with=bind)
    now = datetime.now(UTC)
    for name, period_days, schedule in (
        ("主播3天趋势通知", 3, "daily@09:30"),
        ("主播7天趋势通知", 7, "weekly:1@09:40"),
    ):
        if bind.scalar(sa.select(rules.c.id).where(rules.c.name == name)) is not None:
            continue
        bind.execute(
            rules.insert().values(
                id=_new_id(bind),
                name=name,
                rule_type="anchor_trend_summary",
                period_days=period_days,
                spend_increase_threshold=Decimal("0.30"),
                spend_decrease_threshold=Decimal("-0.30"),
                roi_increase_threshold=Decimal("0.30"),
                roi_decrease_threshold=Decimal("-0.30"),
                minimum_spend=Decimal(0),
                minimum_orders=0,
                minimum_coverage_rate=Decimal("0.80"),
                minimum_effective_hours=1,
                evaluation_delay_minutes=0,
                push_schedule=schedule,
                schedule_timezone="Asia/Shanghai",
                applicable_rooms=[],
                applicable_anchors=[],
                enabled=True,
                push_enabled=True,
                push_chat_id=None,
                send_rise=True,
                send_fall=True,
                rise_limit=10,
                fall_limit=10,
                send_empty_summary=False,
                allow_force_resend=True,
                push_retry_limit=3,
                cooldown_minutes=0,
                created_by=None,
                updated_by=None,
                created_at=now,
                updated_at=now,
            )
        )


def _quarantine_data_quality_business_pushes() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    alert_rules = sa.Table("alert_rules", metadata, autoload_with=bind)
    alert_events = sa.Table("alert_events", metadata, autoload_with=bind)
    quality_rule_ids = sa.select(alert_rules.c.id).where(
        alert_rules.c.rule_type.in_(DATA_QUALITY_RULE_TYPES)
    )
    bind.execute(
        alert_rules.update()
        .where(alert_rules.c.rule_type.in_(DATA_QUALITY_RULE_TYPES))
        .values(
            push_enabled=False,
            system_record_enabled=True,
            business_push_enabled=False,
            technical_push_enabled=False,
        )
    )
    bind.execute(
        alert_events.update()
        .where(
            alert_events.c.rule_id.in_(quality_rule_ids),
            alert_events.c.push_status.in_(("pending", "failed", "sending")),
        )
        .values(
            push_status="skipped",
            push_error="数据质量事件仅系统记录，业务群推送已关闭",
        )
    )


def upgrade() -> None:
    _extend_rules()
    _create_event_tables()
    _restore_extended_rule_data()
    _quarantine_data_quality_business_pushes()
    _seed_default_rules()


def _drop_column(table_name: str, column_name: str) -> None:
    if column_name in _column_names(table_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column(column_name)


def downgrade() -> None:
    bind = op.get_bind()
    if "anchor_trend_events" in _table_names():
        events = sa.Table("anchor_trend_events", sa.MetaData(), autoload_with=bind)
        if bind.scalar(sa.select(sa.func.count()).select_from(events)):
            raise RuntimeError(
                "anchor_trend_events 已有审计数据；拒绝破坏性降级，请先导出并归档趋势事件"
            )
    _backup_extended_rule_data()
    if "anchor_trend_items" in _table_names():
        op.drop_table("anchor_trend_items")
    if "anchor_trend_events" in _table_names():
        op.drop_table("anchor_trend_events")
    if "ix_hourly_comparison_rules_rule_type" in _index_names("hourly_comparison_rules"):
        op.drop_index(
            "ix_hourly_comparison_rules_rule_type",
            table_name="hourly_comparison_rules",
        )
    for name, _type, _default in reversed(ALERT_RULE_COLUMNS):
        _drop_column("alert_rules", name)
    for name, _type, _default in reversed(RULE_COLUMNS):
        _drop_column("hourly_comparison_rules", name)
