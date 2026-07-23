from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoomOption(BaseModel):
    id: UUID
    name: str


class MetricOption(BaseModel):
    key: str
    name: str
    category: str
    unit: str
    precision: int
    scope: str
    aggregation: str
    numerator: str | None
    denominator: str | None
    direction: str
    default_visible: bool
    analysis_default: bool
    supports_hourly_trend: bool
    supports_kline: bool
    supports_alerts: bool
    is_cumulative: bool


class FilterOptionsResponse(BaseModel):
    min_date: date | None
    max_date: date | None
    months: list[str]
    rooms: list[RoomOption]
    anchors: list[str]
    anchor_members: list[str]
    controls: list[str]
    hour_slots: list[str]
    metrics: list[MetricOption]
    comparison_types: list[str]


class ComparisonPayload(BaseModel):
    current_value: Decimal | None
    baseline_value: Decimal | None
    delta_value: Decimal | None
    ratio_percent: Decimal | None
    growth_percent: Decimal | None
    direction_status: str
    explanation: str


class KpiPayload(BaseModel):
    metric_key: str
    name: str
    unit: str
    precision: int
    direction: str
    value: Decimal | None
    comparison: ComparisonPayload


class OverviewResponse(BaseModel):
    start_date: date | None
    end_date: date | None
    kpis: list[KpiPayload]
    room_ranking: list[dict[str, Any]]
    anchor_match_rate: Decimal | None
    data_completeness: Decimal | None
    data_submission_deadline_hour: int
    active_alerts: int
    sync_mode: Literal["feishu", "feishu_base_export", "fixture_mock"]


class XItem(BaseModel):
    key: str
    fact_id: UUID | None = None
    point_id: UUID | None = None
    label: str
    date: date
    hour_slot: str | None
    anchor: str | None
    control: str | None
    observed_at: datetime | None


class TimelineSeries(BaseModel):
    metric_key: str
    name: str
    unit: str
    axis_group: str
    data: list[Decimal | None]


class TimelineGroup(BaseModel):
    group_key: str
    group_label: str
    x_items: list[XItem]
    series: list[TimelineSeries]
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class TimelineResponse(BaseModel):
    grain: Literal["hour", "point"]
    groups: list[TimelineGroup]


class AnchorHourDetailItem(BaseModel):
    key: str
    fact_id: UUID
    business_date: date
    hour_slot: str
    hour_order: int
    room_id: UUID
    room_name: str
    anchor_name: str
    control_name: str | None
    latest_observed_at: datetime | None
    anchor_match_status: str
    data_status: str
    metrics: dict[str, Decimal | None]


class AnchorHourDetailResponse(BaseModel):
    items: list[AnchorHourDetailItem]
    total: int
    page: int
    page_size: int
    metric_keys: list[str]


class HourDescriptorPayload(BaseModel):
    key: str
    label: str
    sort: int


class DatePeriodPayload(BaseModel):
    start: date
    end: date
    days: int
    complete: bool


class BusinessKlinePayload(BaseModel):
    open: Decimal
    close: Decimal
    high: Decimal
    low: Decimal
    average: Decimal
    median: Decimal
    total: Decimal
    effective_days: int
    first_date: date
    last_date: date
    high_date: date
    low_date: date


class HourPeriodValuesPayload(BaseModel):
    roi: Decimal | None
    spend: Decimal | None
    metrics: dict[str, Decimal | None] = Field(default_factory=dict)
    roi_ohlc: BusinessKlinePayload | None
    spend_ohlc: BusinessKlinePayload | None
    metric_ohlc: dict[str, BusinessKlinePayload | None] = Field(default_factory=dict)
    effective_days: int
    effective_samples: int
    expected_samples: int | None
    coverage_rate: Decimal | None
    in_progress: bool = False
    future: bool = False


class HourComparisonResultPayload(BaseModel):
    roi_difference: Decimal | None
    roi_ratio: Decimal | None
    roi_percentage: Decimal | None
    roi_growth: Decimal | None
    roi_growth_percentage: Decimal | None
    spend_difference: Decimal | None
    spend_ratio: Decimal | None
    spend_percentage: Decimal | None
    spend_growth: Decimal | None
    spend_growth_percentage: Decimal | None
    roi_target_gap: Decimal | None
    roi_target_attainment: Decimal | None
    roi_target_reached: bool | None


class HourStatusPayload(BaseModel):
    code: str
    name: str
    level: str
    reasons: list[str]
    reason_codes: list[str]
    should_push: bool


class HourlySeriesPointPayload(BaseModel):
    hour: str
    label: str
    sort: int
    current: HourPeriodValuesPayload
    comparison: HourPeriodValuesPayload | None
    comparison_result: HourComparisonResultPayload
    roi_target: Decimal | None
    target_message: str | None
    status: HourStatusPayload


class HourlyComparisonSeriesPayload(BaseModel):
    series_key: str
    series_name: str
    dimension: str
    room_id: UUID | None
    room_name: str | None
    product_category: str | None
    anchor_name: str | None = None
    roi_target: Decimal | None
    multiple_targets: bool = False
    target_message: str | None = None
    points: list[HourlySeriesPointPayload]


class HourlyComparisonMetaPayload(BaseModel):
    timezone: str
    generated_at: datetime
    data_updated_at: datetime | None
    period_days: int
    aggregation_mode: Literal["sum", "daily_average"]
    chart_type: Literal["line", "business_kline", "bar"]
    series_dimension: Literal["summary", "room", "anchor", "controller", "room_anchor"]
    compare_enabled: bool
    include_today: bool
    latest_complete_date: date | None


class HourlyComparisonResponse(BaseModel):
    meta: HourlyComparisonMetaPayload
    current_period: DatePeriodPayload
    comparison_period: DatePeriodPayload | None
    hours: list[HourDescriptorPayload]
    metrics: list[MetricOption]
    series: list[HourlyComparisonSeriesPayload]


class HourlyComparisonDetailsResponse(BaseModel):
    natural_hour: str
    current_period: DatePeriodPayload
    comparison_period: DatePeriodPayload | None
    summary: list[HourlySeriesPointPayload]
    daily_rows: list[dict[str, Any]]
    room_rows: list[dict[str, Any]]
    kline_rows: list[dict[str, Any]]
    raw_records: list[dict[str, Any]]
    raw_total: int
    page: int
    page_size: int


class RoomMetricTargetRequest(BaseModel):
    room_id: UUID | None = None
    room_name: str | None = Field(default=None, max_length=200)
    product_category: str | None = Field(default=None, max_length=200)
    metric_code: str = Field(min_length=1, max_length=100)
    target_value: Decimal
    effective_start_date: date | None = None
    effective_end_date: date | None = None
    enabled: bool = True


class RoomMetricTargetPayload(RoomMetricTargetRequest):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime
    updated_by: UUID | None


class HourlyComparisonRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rule_type: Literal["hourly_comparison_legacy", "anchor_trend_summary"] = (
        "hourly_comparison_legacy"
    )
    period_days: Literal[1, 3, 5, 7, 15, 30]
    spend_increase_threshold: Decimal = Field(default=Decimal("0.30"), ge=0)
    spend_decrease_threshold: Decimal = Field(default=Decimal("-0.30"), le=0)
    roi_increase_threshold: Decimal = Field(default=Decimal("0.30"), ge=0)
    roi_decrease_threshold: Decimal = Field(default=Decimal("-0.30"), le=0)
    minimum_spend: Decimal = Field(default=Decimal(0), ge=0)
    minimum_orders: int = Field(default=0, ge=0)
    minimum_coverage_rate: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    minimum_effective_hours: int = Field(default=1, ge=1, le=720)
    evaluation_delay_minutes: int = Field(default=15, ge=0, le=1440)
    push_schedule: str = Field(default="manual", min_length=1, max_length=80)
    schedule_timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    applicable_rooms: list[str] = Field(default_factory=list)
    applicable_anchors: list[str] = Field(default_factory=list)
    enabled: bool = True
    push_enabled: bool = False
    push_chat_id: str | None = Field(default=None, max_length=200)
    send_rise: bool = True
    send_fall: bool = True
    rise_limit: int = Field(default=10, ge=1, le=100)
    fall_limit: int = Field(default=10, ge=1, le=100)
    send_empty_summary: bool = False
    allow_force_resend: bool = True
    push_retry_limit: int = Field(default=3, ge=1, le=10)
    cooldown_minutes: int = Field(default=60, ge=0, le=1440)


class HourlyComparisonRulePayload(HourlyComparisonRuleRequest):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None
    updated_by: UUID | None


class StrictResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnchorTrendPeriodPayload(StrictResponseModel):
    start: date
    end: date


class AnchorTrendHourValuesPayload(StrictResponseModel):
    spend: Decimal | None
    amount: Decimal | None
    roi: Decimal | None
    orders: Decimal | None


class AnchorTrendHourDetailPayload(StrictResponseModel):
    hour: str
    current: AnchorTrendHourValuesPayload
    baseline: AnchorTrendHourValuesPayload
    roi_delta: Decimal | None
    spend_difference: Decimal | None


class AnchorTrendCalculationItemPayload(StrictResponseModel):
    rank: int
    room_id: UUID
    room_name: str
    anchor_id: UUID | None
    anchor_name: str
    control_names: list[str]
    trend_type: Literal["rise", "fall", "insufficient"]
    current_amount: Decimal | None
    baseline_amount: Decimal | None
    current_spend: Decimal | None
    baseline_spend: Decimal | None
    spend_growth_rate: Decimal | None
    current_roi: Decimal | None
    baseline_roi: Decimal | None
    roi_growth_rate: Decimal | None
    current_orders: Decimal | None
    baseline_orders: Decimal | None
    current_order_cost: Decimal | None
    baseline_order_cost: Decimal | None
    roi_target: Decimal | None
    roi_target_gap: Decimal | None
    roi_target_reached: bool | None
    primary_status: str
    primary_status_name: str
    reason_codes: list[str]
    reasons: list[str]
    major_rise_hours: list[str]
    major_fall_hours: list[str]
    major_spend_hours: list[str]
    hourly_details: list[AnchorTrendHourDetailPayload]
    current_effective_days: int
    baseline_effective_days: int
    current_effective_hours: int
    baseline_effective_hours: int
    current_coverage_rate: Decimal | None
    baseline_coverage_rate: Decimal | None
    comparison_basis: str
    suggestion: str


class AnchorTrendItemPayload(AnchorTrendCalculationItemPayload):
    item_id: UUID
    event_id: UUID
    push_status: str
    destination_group: str | None


class AnchorTrendEventPayload(StrictResponseModel):
    id: UUID
    rule_id: UUID
    period_days: Literal[1, 3, 5, 7, 15, 30]
    current_period_start: date
    current_period_end: date
    baseline_period_start: date
    baseline_period_end: date
    notification_type: Literal[
        "anchor_rise_summary",
        "anchor_fall_summary",
        "anchor_insufficient_summary",
    ]
    destination_group: str | None
    room_scope: list[UUID]
    anchor_count: int
    dedup_key: str
    push_status: str
    push_attempts: int
    pushed_at: datetime | None
    push_error: str | None
    manual_resend: bool
    source_event_id: UUID | None
    resend_reason: str | None
    operated_by: UUID | None
    created_at: datetime


class AnchorTrendSummaryPayload(StrictResponseModel):
    rise_count: int
    fall_count: int
    insufficient_count: int
    reached_count: int


class AnchorTrendListResponse(StrictResponseModel):
    current_period: AnchorTrendPeriodPayload | None
    baseline_period: AnchorTrendPeriodPayload | None
    rise: list[AnchorTrendItemPayload]
    fall: list[AnchorTrendItemPayload]
    insufficient: list[AnchorTrendItemPayload]
    summary: AnchorTrendSummaryPayload
    events: list[AnchorTrendEventPayload]


class AnchorTrendRecalculateResponse(StrictResponseModel):
    current_period: AnchorTrendPeriodPayload
    baseline_period: AnchorTrendPeriodPayload
    rise: list[AnchorTrendCalculationItemPayload]
    fall: list[AnchorTrendCalculationItemPayload]
    insufficient: list[AnchorTrendCalculationItemPayload]
    summary: AnchorTrendSummaryPayload
    event_ids: dict[Literal["rise", "fall", "insufficient"], UUID]
    data_updated_at: datetime | None


class AnchorTrendDailyDetailPayload(StrictResponseModel):
    period: Literal["current", "baseline"]
    date: date
    spend: Decimal | None
    amount: Decimal | None
    roi: Decimal | None
    orders: Decimal | None


class AnchorTrendRawRecordPayload(StrictResponseModel):
    fact_id: UUID
    period: Literal["current", "baseline"]
    date: date
    natural_hour: str
    anchor: str | None
    control: str | None
    data_status: str
    metrics: dict[str, Decimal | None]


class AnchorTrendValuePairPayload(StrictResponseModel):
    current: Decimal | None
    baseline: Decimal | None


class AnchorTrendItemDetailsPayload(StrictResponseModel):
    item_id: UUID
    daily: list[AnchorTrendDailyDetailPayload]
    hours: list[AnchorTrendHourDetailPayload]
    roi_numerator: AnchorTrendValuePairPayload
    roi_denominator: AnchorTrendValuePairPayload
    raw_records: list[AnchorTrendRawRecordPayload]


class AnchorTrendEventDetailsResponse(StrictResponseModel):
    event: AnchorTrendEventPayload
    items: list[AnchorTrendItemPayload]
    details: list[AnchorTrendItemDetailsPayload]


class AnchorTrendPushResponse(StrictResponseModel):
    event_id: UUID | None = None
    push_status: Literal["sent", "skipped"]
    provider: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None


class DetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    room: str
    base: dict[str, Any]
    metrics: dict[str, Decimal | None]
    raw_payload: dict[str, Any] | None = None
    points: list[dict[str, Any]] = Field(default_factory=list)


class AlertAcknowledgeRequest(BaseModel):
    resolution_note: str = Field(min_length=1, max_length=1000)


class AlertRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rule_type: Literal["roi_surge", "roi_drop", "roi_floor", "anchor_mismatch", "data_delay"]
    metric_key: str | None = None
    comparison_type: str | None = "previous_day"
    operator: str = Field(min_length=1, max_length=12)
    threshold: Decimal
    min_spend: Decimal | None = None
    min_orders: int | None = None
    min_amount: Decimal | None = None
    room_scope: list[str] = Field(default_factory=list)
    anchor_scope: list[str] = Field(default_factory=list)
    control_scope: list[str] = Field(default_factory=list)
    severity: Literal["info", "warning", "critical"] = "warning"
    cooldown_minutes: int = Field(default=60, ge=0, le=1440)
    enabled: bool = True
    push_enabled: bool = True
    system_record_enabled: bool = True
    business_push_enabled: bool = True
    technical_push_enabled: bool = False
    technical_chat_id: str | None = Field(default=None, max_length=200)
    suggestion_template: str = Field(default="", max_length=2000)


class AnchorTrendRecalculateRequest(BaseModel):
    rule_id: UUID | None = None
    period_days: Literal[1, 3, 5, 7, 15, 30]
    end_date: date | None = None
    room_ids: list[UUID] = Field(default_factory=list)
    anchor_names: list[str] = Field(default_factory=list)


class AnchorTrendSendRequest(BaseModel):
    rule_id: UUID
    period: date
    notification_type: Literal["anchor_rise_summary", "anchor_fall_summary"]
    force_resend: bool = False
    resend_reason: str | None = Field(default=None, max_length=1000)


class AnchorTrendTestRequest(BaseModel):
    notification_type: Literal["anchor_rise_summary", "anchor_fall_summary"]
    chat_id: str | None = Field(default=None, max_length=200)
