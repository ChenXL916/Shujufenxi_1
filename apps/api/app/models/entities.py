from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
MONEY = Numeric(24, 8)


class SourceConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_configs"
    __table_args__ = (UniqueConstraint("source_type", "app_token", "table_id", "source_role"),)
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(40))
    source_role: Mapped[str] = mapped_column(String(40))
    app_token: Mapped[str] = mapped_column(String(200))
    table_id: Mapped[str] = mapped_column(String(200))
    view_id: Mapped[str | None] = mapped_column(String(200))
    default_room_name: Mapped[str | None] = mapped_column(String(200))
    schedule_year: Mapped[int | None]
    field_mapping: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class SyncRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_runs"
    source_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_configs.id"), index=True)
    mode: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str | None] = mapped_column(String(200))


class RawSourceRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "raw_source_records"
    __table_args__ = (UniqueConstraint("source_config_id", "source_record_id"),)
    source_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_configs.id"), index=True)
    source_record_id: Mapped[str] = mapped_column(String(300))
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_fields: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Room(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rooms"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    brand: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source_aliases: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)


class RoomResource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Formal authorization metadata for a live-room resource."""

    __tablename__ = "room_resources"
    __table_args__ = (
        UniqueConstraint("room_id"),
        Index("ix_room_resources_permission_group", "permission_group", "enabled"),
    )
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    room_name: Mapped[str] = mapped_column(String(200))
    product_category: Mapped[str] = mapped_column(String(80), index=True)
    permission_group: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Person(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "persons"
    display_name: Mapped[str] = mapped_column(String(200))
    base_name: Mapped[str] = mapped_column(String(100), index=True)
    prefix: Mapped[str | None] = mapped_column(String(20))
    primary_role: Mapped[str | None] = mapped_column(String(40))
    employment_status: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class PersonAlias(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "person_aliases"
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id"), index=True)
    alias: Mapped[str] = mapped_column(String(200))
    normalized_alias: Mapped[str] = mapped_column(String(200), unique=True)
    source: Mapped[str] = mapped_column(String(40))


class LivePoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "live_points"
    __table_args__ = (
        Index("ix_live_points_room_observed", "room_id", "observed_at"),
        Index("ix_live_points_room_date_hour", "room_id", "business_date", "hour_order"),
        Index("ix_live_points_anchor_date", "anchor_base_name", "business_date"),
        Index("ix_live_points_control_date", "control_base_name", "business_date"),
    )
    raw_source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("raw_source_records.id"), unique=True
    )
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_date: Mapped[date] = mapped_column(Date, index=True)
    year: Mapped[int]
    month: Mapped[int]
    hour_slot: Mapped[str | None] = mapped_column(String(8), index=True)
    hour_order: Mapped[int | None]
    anchor_raw: Mapped[str | None] = mapped_column(String(200))
    anchor_canonical: Mapped[str | None] = mapped_column(String(200))
    anchor_base_name: Mapped[str | None] = mapped_column(String(100))
    anchor_members: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    anchor_note: Mapped[str | None] = mapped_column(String(300))
    control_raw: Mapped[str | None] = mapped_column(String(200))
    control_canonical: Mapped[str | None] = mapped_column(String(200))
    control_base_name: Mapped[str | None] = mapped_column(String(100))
    auto_check_status: Mapped[str | None] = mapped_column(String(40))
    valid: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    invalid_reason: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)


class LivePointMetric(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "live_point_metrics"
    __table_args__ = (UniqueConstraint("live_point_id", "metric_key"),)
    live_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("live_points.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(100), index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(MONEY)
    raw_value: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(24), default="parsed")


class AnchorSchedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "anchor_schedules"
    __table_args__ = (UniqueConstraint("room_id", "schedule_date", "hour_slot"),)
    source_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_configs.id"))
    source_record_id: Mapped[str] = mapped_column(String(300))
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    schedule_date: Mapped[date] = mapped_column(Date, index=True)
    year: Mapped[int]
    month: Mapped[int]
    day: Mapped[int]
    hour_slot: Mapped[str] = mapped_column(String(8), index=True)
    hour_order: Mapped[int]
    planned_anchor_raw: Mapped[str | None] = mapped_column(String(200))
    planned_anchor_canonical: Mapped[str | None] = mapped_column(String(200))
    planned_anchor_base_names: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    schedule_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)


class StaffSchedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staff_schedules"
    __table_args__ = (UniqueConstraint("person_id", "schedule_date"),)
    source_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_configs.id"))
    source_record_id: Mapped[str] = mapped_column(String(300))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id"), index=True)
    schedule_date: Mapped[date] = mapped_column(Date, index=True)
    role: Mapped[str] = mapped_column(String(40))
    employment_status: Mapped[str | None] = mapped_column(String(40))
    shift_raw: Mapped[str | None] = mapped_column(String(100))
    shift_name: Mapped[str | None] = mapped_column(String(100))
    shift_start: Mapped[time | None] = mapped_column(Time)
    shift_end: Mapped[time | None] = mapped_column(Time)
    crosses_midnight: Mapped[bool] = mapped_column(Boolean, default=False)
    is_rest: Mapped[bool] = mapped_column(Boolean, default=False)
    time_configured: Mapped[bool] = mapped_column(Boolean, default=False)


class ShiftRule(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "shift_rules"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    crosses_midnight: Mapped[bool] = mapped_column(Boolean, default=False)
    is_rest: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class HourlyFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hourly_facts"
    __table_args__ = (
        UniqueConstraint("room_id", "business_date", "hour_slot"),
        Index(
            "ix_hourly_facts_date_hour_room",
            "business_date",
            "hour_order",
            "room_id",
        ),
        Index(
            "ix_hourly_facts_room_date_hour",
            "room_id",
            "business_date",
            "hour_order",
        ),
        Index(
            "ix_hourly_facts_date_anchor_hour",
            "business_date",
            "actual_anchor_canonical",
            "hour_order",
        ),
        Index(
            "ix_hourly_facts_date_control_hour",
            "business_date",
            "actual_control_canonical",
            "hour_order",
        ),
    )
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    year: Mapped[int]
    month: Mapped[int]
    hour_slot: Mapped[str] = mapped_column(String(8), index=True)
    hour_order: Mapped[int]
    hour_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hour_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latest_point_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("live_points.id"))
    latest_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_anchor_canonical: Mapped[str | None] = mapped_column(String(200))
    actual_anchor_base_names: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    actual_control_canonical: Mapped[str | None] = mapped_column(String(200))
    planned_anchor_canonical: Mapped[str | None] = mapped_column(String(200))
    planned_anchor_base_names: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    anchor_schedule_status: Mapped[str | None] = mapped_column(String(30))
    anchor_match_status: Mapped[str] = mapped_column(String(40), default="no_schedule")
    control_shift_name: Mapped[str | None] = mapped_column(String(100))
    control_is_scheduled: Mapped[bool | None]
    control_is_rest: Mapped[bool | None]
    control_may_be_on_duty: Mapped[bool | None]
    data_status: Mapped[str] = mapped_column(String(24), default="complete")


class HourlyMetric(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "hourly_metrics"
    __table_args__ = (UniqueConstraint("hourly_fact_id", "metric_key"),)
    hourly_fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hourly_facts.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(100), index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(MONEY)
    value_source: Mapped[str] = mapped_column(String(40))
    quality_status: Mapped[str] = mapped_column(String(40), default="valid")


class MetricDefinition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "metric_definitions"
    metric_key: Mapped[str] = mapped_column(String(100), unique=True)
    source_field_name: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(30))
    precision: Mapped[int] = mapped_column(Integer, default=2)
    scope: Mapped[str] = mapped_column(String(30))
    aggregation_strategy: Mapped[str] = mapped_column(String(40))
    numerator_metric_key: Mapped[str | None] = mapped_column(String(100))
    denominator_metric_key: Mapped[str | None] = mapped_column(String(100))
    chartable: Mapped[bool] = mapped_column(Boolean, default=True)
    comparable: Mapped[bool] = mapped_column(Boolean, default=True)
    alertable: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_hourly_trend: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_kline: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cumulative: Mapped[bool] = mapped_column(Boolean, default=False)
    direction: Mapped[str] = mapped_column(String(30), default="neutral")
    default_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")


class RoomMetricTarget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "room_metric_targets"
    __table_args__ = (
        Index(
            "ix_room_metric_targets_lookup",
            "metric_code",
            "enabled",
            "effective_start_date",
            "effective_end_date",
        ),
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id"), index=True)
    room_name: Mapped[str | None] = mapped_column(String(200), index=True)
    product_category: Mapped[str | None] = mapped_column(String(200), index=True)
    metric_code: Mapped[str] = mapped_column(String(100), index=True)
    target_value: Mapped[Decimal] = mapped_column(MONEY)
    effective_start_date: Mapped[date | None] = mapped_column(Date)
    effective_end_date: Mapped[date | None] = mapped_column(Date)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class HourlyComparisonRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hourly_comparison_rules"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    rule_type: Mapped[str] = mapped_column(String(60), default="anchor_trend_summary", index=True)
    period_days: Mapped[int] = mapped_column(Integer, default=1)
    spend_increase_threshold: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.30"))
    spend_decrease_threshold: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("-0.30"))
    roi_increase_threshold: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.30"))
    roi_decrease_threshold: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("-0.30"))
    minimum_spend: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    minimum_orders: Mapped[int] = mapped_column(Integer, default=0)
    minimum_coverage_rate: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.80"))
    minimum_effective_hours: Mapped[int] = mapped_column(Integer, default=1)
    evaluation_delay_minutes: Mapped[int] = mapped_column(Integer, default=15)
    push_schedule: Mapped[str] = mapped_column(String(80), default="daily@09:30")
    schedule_timezone: Mapped[str] = mapped_column(String(80), default="Asia/Shanghai")
    applicable_rooms: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    applicable_anchors: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_chat_id: Mapped[str | None] = mapped_column(String(200))
    send_rise: Mapped[bool] = mapped_column(Boolean, default=True)
    send_fall: Mapped[bool] = mapped_column(Boolean, default=True)
    rise_limit: Mapped[int] = mapped_column(Integer, default=10)
    fall_limit: Mapped[int] = mapped_column(Integer, default=10)
    send_empty_summary: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_force_resend: Mapped[bool] = mapped_column(Boolean, default=True)
    push_retry_limit: Mapped[int] = mapped_column(Integer, default=3)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AlertRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alert_rules"
    name: Mapped[str] = mapped_column(String(200))
    rule_type: Mapped[str] = mapped_column(String(80), index=True)
    metric_key: Mapped[str | None] = mapped_column(String(100))
    comparison_type: Mapped[str | None] = mapped_column(String(60))
    operator: Mapped[str] = mapped_column(String(12))
    threshold: Mapped[Decimal] = mapped_column(MONEY)
    min_spend: Mapped[Decimal | None] = mapped_column(MONEY)
    min_orders: Mapped[int | None]
    min_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    room_scope: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    anchor_scope: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    control_scope: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    severity: Mapped[str] = mapped_column(String(24))
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    system_record_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    business_push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    technical_push_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    technical_chat_id: Mapped[str | None] = mapped_column(String(200))
    suggestion_template: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID | None]


class AlertEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "alert_events"
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alert_rules.id"), index=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    hour_slot: Mapped[str] = mapped_column(String(8))
    anchor_name: Mapped[str | None] = mapped_column(String(200))
    control_name: Mapped[str | None] = mapped_column(String(200))
    metric_key: Mapped[str | None] = mapped_column(String(100))
    period_days: Mapped[int | None]
    current_period_start: Mapped[date | None] = mapped_column(Date)
    current_period_end: Mapped[date | None] = mapped_column(Date)
    comparison_period_start: Mapped[date | None] = mapped_column(Date)
    comparison_period_end: Mapped[date | None] = mapped_column(Date)
    alert_type: Mapped[str | None] = mapped_column(String(100), index=True)
    metric_codes: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    status_code: Mapped[str | None] = mapped_column(String(100), index=True)
    status_reasons: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    comparison_context: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    comparison_rule_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    anchor_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    control_id: Mapped[uuid.UUID | None]
    current_spend: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_spend: Mapped[Decimal | None] = mapped_column(MONEY)
    spend_growth_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    current_roi: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_roi: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_growth_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_target: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_target_gap: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_target_reached: Mapped[bool | None] = mapped_column(Boolean)
    notification_type: Mapped[str | None] = mapped_column(String(50), index=True)
    message_color: Mapped[str | None] = mapped_column(String(20))
    push_chat_id: Mapped[str | None] = mapped_column(String(200))
    base_dedup_key: Mapped[str | None] = mapped_column(String(64), index=True)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    current_value: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_value: Mapped[Decimal | None] = mapped_column(MONEY)
    delta_value: Mapped[Decimal | None] = mapped_column(MONEY)
    ratio_percent: Mapped[Decimal | None] = mapped_column(MONEY)
    growth_percent: Mapped[Decimal | None] = mapped_column(MONEY)
    severity: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text, default="")
    push_status: Mapped[str] = mapped_column(String(24), default="pending")
    push_attempts: Mapped[int] = mapped_column(Integer, default=0)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    push_error: Mapped[str | None] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[uuid.UUID | None]
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnchorTrendEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "anchor_trend_events"
    __table_args__ = (UniqueConstraint("dedup_key"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hourly_comparison_rules.id"), index=True)
    period_days: Mapped[int] = mapped_column(Integer, index=True)
    current_period_start: Mapped[date] = mapped_column(Date)
    current_period_end: Mapped[date] = mapped_column(Date, index=True)
    baseline_period_start: Mapped[date] = mapped_column(Date)
    baseline_period_end: Mapped[date] = mapped_column(Date)
    notification_type: Mapped[str] = mapped_column(String(60), index=True)
    destination_group: Mapped[str | None] = mapped_column(String(200), index=True)
    room_scope: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    anchor_count: Mapped[int] = mapped_column(Integer, default=0)
    message_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    push_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    push_attempts: Mapped[int] = mapped_column(Integer, default=0)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    push_error: Mapped[str | None] = mapped_column(Text)
    manual_resend: Mapped[bool] = mapped_column(Boolean, default=False)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anchor_trend_events.id"), index=True
    )
    resend_reason: Mapped[str | None] = mapped_column(Text)
    operated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnchorTrendItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "anchor_trend_items"
    __table_args__ = (
        UniqueConstraint("event_id", "room_id", "anchor_name"),
        Index("ix_anchor_trend_items_scope", "room_id", "anchor_name", "trend_type"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anchor_trend_events.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int | None] = mapped_column(Integer)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    room_name: Mapped[str] = mapped_column(String(200))
    anchor_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    anchor_name: Mapped[str] = mapped_column(String(200), index=True)
    control_names: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    trend_type: Mapped[str] = mapped_column(String(24), index=True)
    current_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    current_spend: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_spend: Mapped[Decimal | None] = mapped_column(MONEY)
    spend_growth_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    current_roi: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_roi: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_growth_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    current_orders: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_orders: Mapped[Decimal | None] = mapped_column(MONEY)
    current_order_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_order_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_target: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_target_gap: Mapped[Decimal | None] = mapped_column(MONEY)
    roi_target_reached: Mapped[bool | None] = mapped_column(Boolean)
    primary_status: Mapped[str] = mapped_column(String(100), index=True)
    primary_status_name: Mapped[str] = mapped_column(String(100))
    reason_codes: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    reasons: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    major_rise_hours: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    major_fall_hours: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    major_spend_hours: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    hourly_details: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    current_effective_days: Mapped[int] = mapped_column(Integer, default=0)
    baseline_effective_days: Mapped[int] = mapped_column(Integer, default=0)
    current_effective_hours: Mapped[int] = mapped_column(Integer, default=0)
    baseline_effective_hours: Mapped[int] = mapped_column(Integer, default=0)
    current_coverage_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    baseline_coverage_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    comparison_basis: Mapped[str] = mapped_column(String(300))
    suggestion: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Role(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(40), unique=True)
    role_code: Mapped[str | None] = mapped_column(String(80), unique=True)
    role_name: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    all_permissions: Mapped[bool] = mapped_column(Boolean, default=False)
    system_role: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Permission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "permissions"
    permission_code: Mapped[str] = mapped_column(String(120), unique=True)
    permission_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")


class RolePermission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), index=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permissions.id"), index=True)


class RoleRoomScope(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "role_room_scopes"
    __table_args__ = (UniqueConstraint("role_id", "room_id"),)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    feishu_user_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    username: Mapped[str | None] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(30), default="active")
    room_scope_mode: Mapped[str] = mapped_column(String(20), default="role")
    role_name: Mapped[str] = mapped_column(String(40), default="viewer")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRole(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), index=True)


class UserRoomPermission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_room_permissions"
    __table_args__ = (UniqueConstraint("user_id", "room_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    can_export: Mapped[bool] = mapped_column(Boolean, default=False)


class FeishuGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feishu_groups"
    name: Mapped[str] = mapped_column(String(200))
    chat_id: Mapped[str] = mapped_column(String(255), unique=True)
    all_rooms: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class FeishuGroupRoomScope(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "feishu_group_room_scopes"
    __table_args__ = (UniqueConstraint("group_id", "room_id"),)
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feishu_groups.id", ondelete="CASCADE"), index=True
    )
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)


class PermissionAuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "permission_audit_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(200))
    before_value: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    after_value: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[uuid.UUID | None]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    object_type: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[str | None] = mapped_column(String(200))
    before_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    after_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
