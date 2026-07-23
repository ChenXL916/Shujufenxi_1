from __future__ import annotations

import csv
import io
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    BusinessKlinePayload,
    DatePeriodPayload,
    HourComparisonResultPayload,
    HourDescriptorPayload,
    HourlyComparisonDetailsResponse,
    HourlyComparisonMetaPayload,
    HourlyComparisonResponse,
    HourlyComparisonRulePayload,
    HourlyComparisonRuleRequest,
    HourlyComparisonSeriesPayload,
    HourlySeriesPointPayload,
    HourPeriodValuesPayload,
    HourStatusPayload,
    MetricOption,
    RoomMetricTargetPayload,
    RoomMetricTargetRequest,
)
from app.auth.dependencies import AccessScope
from app.core.config import get_settings
from app.domain.aggregation import MetricObservation, aggregate_metric
from app.domain.data_freshness import data_is_due, fact_counts_toward_completeness
from app.domain.hourly_comparison import (
    BusinessKline,
    DailyValue,
    DatePeriod,
    HourlyStatusInput,
    TargetCandidate,
    build_business_kline,
    build_periods,
    common_target,
    compare_values,
    evaluate_hourly_status,
    hour_descriptors,
    select_target,
)
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    HourlyComparisonRule,
    HourlyFact,
    HourlyMetric,
    LivePoint,
    RawSourceRecord,
    Room,
    RoomMetricTarget,
    SourceConfig,
)

AggregationMode = Literal["sum", "daily_average"]
ChartType = Literal["line", "business_kline", "bar"]
SeriesDimension = Literal["summary", "room", "anchor", "controller", "room_anchor"]


@dataclass(frozen=True)
class HourlyComparisonFilters:
    end_date: date | None = None
    period_days: int = 7
    custom_start_date: date | None = None
    custom_end_date: date | None = None
    compare_enabled: bool = True
    aggregation_mode: AggregationMode = "sum"
    chart_type: ChartType = "line"
    metric_ids: tuple[str, ...] = ("period_overall_roi", "period_spend")
    room_ids: tuple[uuid.UUID, ...] = ()
    anchor_names: tuple[str, ...] = ()
    anchor_members: tuple[str, ...] = ()
    control_names: tuple[str, ...] = ()
    natural_hours: tuple[str, ...] = ()
    series_dimension: SeriesDimension = "summary"
    include_today: bool = False
    include_in_progress: bool = True
    show_range_band: bool = False


@dataclass(frozen=True)
class SeriesIdentity:
    key: str
    name: str
    dimension: str
    room_id: uuid.UUID | None
    room_name: str | None
    product_category: str | None
    anchor_name: str | None


@dataclass(frozen=True)
class RuleThresholds:
    spend_increase_threshold: Decimal
    spend_decrease_threshold: Decimal
    roi_increase_threshold: Decimal
    roi_decrease_threshold: Decimal
    minimum_spend: Decimal
    minimum_orders: int
    minimum_coverage_rate: Decimal


class HourlyComparisonService:
    def __init__(
        self,
        session: Session,
        catalog: MetricCatalog,
        access: AccessScope,
        rule_override: HourlyComparisonRule | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog
        self.access = access
        self.rule_override = rule_override
        settings = get_settings()
        self.timezone = settings.timezone
        self.data_submission_deadline_hour = settings.data_submission_deadline_hour
        self.now = datetime.now(ZoneInfo(self.timezone))

    def compare(self, filters: HourlyComparisonFilters) -> HourlyComparisonResponse:
        filters, latest_complete = self._resolved_filters(filters)
        end_date = filters.custom_end_date or filters.end_date
        if end_date is None:
            end_date = latest_complete or self.now.date() - timedelta(days=1)
        periods = build_periods(
            end_date,
            filters.period_days,
            custom_start_date=filters.custom_start_date,
            compare_enabled=filters.compare_enabled,
        )
        range_start = periods.comparison.start if periods.comparison else periods.current.start
        all_facts = self._facts(filters, range_start, periods.current.end)
        rooms = self._rooms_for_facts(all_facts, filters.room_ids)
        room_map = {room.id: room for room in rooms}
        metric_keys = self._metric_keys(filters.metric_ids)
        metrics_by_fact = self._metrics_by_fact(all_facts, metric_keys)
        targets = self._target_candidates(periods.current.end)
        rule, rule_can_push = self._rule(filters.period_days)
        identities = self._identities(all_facts, filters.series_dimension, room_map)
        data_updated_at = max(
            (fact.latest_observed_at for fact in all_facts if fact.latest_observed_at),
            default=None,
        )
        series = [
            self._series(
                identity,
                all_facts,
                metrics_by_fact,
                room_map,
                targets,
                rule,
                rule_can_push,
                periods.current,
                periods.comparison,
                filters,
                metric_keys,
            )
            for identity in identities
        ]
        current_complete = periods.current.end < self.now.date()
        comparison_payload = (
            DatePeriodPayload(
                start=periods.comparison.start,
                end=periods.comparison.end,
                days=periods.comparison.days,
                complete=periods.comparison.end < self.now.date(),
            )
            if periods.comparison
            else None
        )
        return HourlyComparisonResponse(
            meta=HourlyComparisonMetaPayload(
                timezone=self.timezone,
                generated_at=self.now,
                data_updated_at=data_updated_at,
                period_days=periods.current.days,
                aggregation_mode=filters.aggregation_mode,
                chart_type=filters.chart_type,
                series_dimension=filters.series_dimension,
                compare_enabled=filters.compare_enabled,
                include_today=filters.include_today,
                latest_complete_date=latest_complete,
            ),
            current_period=DatePeriodPayload(
                start=periods.current.start,
                end=periods.current.end,
                days=periods.current.days,
                complete=current_complete,
            ),
            comparison_period=comparison_payload,
            hours=[
                HourDescriptorPayload(key=item.key, label=item.label, sort=item.sort)
                for item in hour_descriptors()
            ],
            metrics=self._metric_options(),
            series=series,
        )

    def details(
        self,
        filters: HourlyComparisonFilters,
        natural_hour: str,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> HourlyComparisonDetailsResponse:
        if natural_hour not in {item.key for item in hour_descriptors()}:
            raise ValueError("自然小时必须是 00-01 至 23-24")
        scoped_filters = replace(filters, natural_hours=(natural_hour,))
        summary_response = self.compare(replace(scoped_filters, series_dimension="summary"))
        room_response = self.compare(replace(scoped_filters, series_dimension="room"))
        current_period = summary_response.current_period
        comparison_period = summary_response.comparison_period
        range_start = comparison_period.start if comparison_period else current_period.start
        facts = self._facts(scoped_filters, range_start, current_period.end)
        room_map = {room.id: room for room in self._rooms_for_facts(facts, filters.room_ids)}
        metric_keys = self._metric_keys(filters.metric_ids)
        metrics_by_fact = self._metrics_by_fact(facts, metric_keys)
        targets = self._target_candidates(current_period.end)
        daily_rows = [
            self._daily_row(
                fact,
                room_map.get(fact.room_id),
                metrics_by_fact,
                targets,
                "current"
                if current_period.start <= fact.business_date <= current_period.end
                else "comparison",
            )
            for fact in facts
            if fact.data_status == "complete"
        ]
        room_rows = [
            self._room_detail_row(item, natural_hour)
            for item in room_response.series
            if item.points
        ]
        summary_points = [
            point
            for item in summary_response.series
            for point in item.points
            if point.hour == natural_hour
        ]
        kline_rows: list[dict[str, object]] = []
        for point in summary_points:
            for metric_name, kline in (
                ("时段整体支付ROI", point.current.roi_ohlc),
                ("时段消耗", point.current.spend_ohlc),
            ):
                kline_rows.append(self._kline_detail_row(metric_name, "current", kline))
            if point.comparison:
                for metric_name, kline in (
                    ("时段整体支付ROI", point.comparison.roi_ohlc),
                    ("时段消耗", point.comparison.spend_ohlc),
                ):
                    kline_rows.append(self._kline_detail_row(metric_name, "comparison", kline))
        raw_records, raw_total = self._raw_records(
            scoped_filters,
            range_start,
            current_period.end,
            page,
            page_size,
            room_map,
        )
        return HourlyComparisonDetailsResponse(
            natural_hour=natural_hour,
            current_period=current_period,
            comparison_period=comparison_period,
            summary=summary_points,
            daily_rows=sorted(daily_rows, key=lambda item: (str(item["date"]), str(item["room"]))),
            room_rows=room_rows,
            kline_rows=kline_rows,
            raw_records=raw_records,
            raw_total=raw_total,
            page=page,
            page_size=page_size,
        )

    def export_csv(self, filters: HourlyComparisonFilters) -> tuple[bytes, str]:
        self.assert_export_allowed(filters)
        filters, _ = self._resolved_filters(filters)
        response = self.compare(filters)
        room_provenance = self._export_room_provenance(filters, response)
        output = io.StringIO(newline="")
        fieldnames = [
            "直播间ID",
            "直播间",
            "系列",
            "自然小时",
            "当前ROI",
            "基准ROI",
            "ROI涨幅",
            "ROI目标",
            "目标差",
            "当前消耗",
            "基准消耗",
            "消耗涨幅",
            "ROI_open",
            "ROI_close",
            "ROI_high",
            "ROI_low",
            "消耗_open",
            "消耗_close",
            "消耗_high",
            "消耗_low",
            "综合状态",
            "状态原因",
            "当前有效样本",
            "基准有效样本",
            "完整率",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in response.series:
            room_ids, room_names = room_provenance[item.series_key]
            for point in item.points:
                row = {
                    "直播间ID": room_ids,
                    "直播间": room_names,
                    "系列": item.series_name,
                    "自然小时": point.hour,
                    "当前ROI": point.current.roi,
                    "基准ROI": point.comparison.roi if point.comparison else None,
                    "ROI涨幅": point.comparison_result.roi_growth,
                    "ROI目标": point.roi_target,
                    "目标差": point.comparison_result.roi_target_gap,
                    "当前消耗": point.current.spend,
                    "基准消耗": point.comparison.spend if point.comparison else None,
                    "消耗涨幅": point.comparison_result.spend_growth,
                    "ROI_open": self._kline_value(point.current.roi_ohlc, "open"),
                    "ROI_close": self._kline_value(point.current.roi_ohlc, "close"),
                    "ROI_high": self._kline_value(point.current.roi_ohlc, "high"),
                    "ROI_low": self._kline_value(point.current.roi_ohlc, "low"),
                    "消耗_open": self._kline_value(point.current.spend_ohlc, "open"),
                    "消耗_close": self._kline_value(point.current.spend_ohlc, "close"),
                    "消耗_high": self._kline_value(point.current.spend_ohlc, "high"),
                    "消耗_low": self._kline_value(point.current.spend_ohlc, "low"),
                    "综合状态": point.status.name,
                    "状态原因": "；".join(point.status.reasons),
                    "当前有效样本": point.current.effective_samples,
                    "基准有效样本": (
                        point.comparison.effective_samples if point.comparison else None
                    ),
                    "完整率": point.current.coverage_rate,
                }
                writer.writerow({key: self._csv_safe(value) for key, value in row.items()})
        filename = (
            f"24hour_roi_spend_{response.current_period.start.isoformat()}_"
            f"{response.current_period.end.isoformat()}.csv"
        )
        return output.getvalue().encode("utf-8-sig"), filename

    def _export_room_provenance(
        self,
        filters: HourlyComparisonFilters,
        response: HourlyComparisonResponse,
    ) -> dict[str, tuple[str, str]]:
        range_start = (
            response.comparison_period.start
            if response.comparison_period is not None
            else response.current_period.start
        )
        facts = self._facts(filters, range_start, response.current_period.end)
        rooms = self._rooms_for_facts(facts, filters.room_ids)
        room_map = {room.id: room for room in rooms}
        identities = {
            identity.key: identity
            for identity in self._identities(facts, filters.series_dimension, room_map)
        }
        provenance: dict[str, tuple[str, str]] = {}
        for series in response.series:
            identity = identities[series.series_key]
            source_ids = sorted(
                {fact.room_id for fact in facts if self._fact_in_identity(fact, identity)},
                key=lambda room_id: (
                    room_map[room_id].name if room_id in room_map else "",
                    str(room_id),
                ),
            )
            provenance[series.series_key] = (
                "、".join(str(room_id) for room_id in source_ids),
                "、".join(
                    room_map[room_id].name if room_id in room_map else "未知直播间"
                    for room_id in source_ids
                ),
            )
        return provenance

    def assert_export_allowed(self, filters: HourlyComparisonFilters) -> None:
        if not self.access.can_export:
            raise PermissionError("当前账号没有导出权限")
        if self.access.export_room_ids is None:
            return
        selected = self._effective_room_ids(filters.room_ids)
        if selected is None or not selected.issubset(self.access.export_room_ids):
            raise PermissionError("所选范围包含无导出权限的直播间")

    @staticmethod
    def _csv_safe(value: object) -> object:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
            return f"'{value}"
        return value

    def list_targets(self) -> list[RoomMetricTargetPayload]:
        rows = list(
            self.session.scalars(
                select(RoomMetricTarget).order_by(
                    RoomMetricTarget.room_name,
                    RoomMetricTarget.product_category,
                    RoomMetricTarget.metric_code,
                )
            )
        )
        return [RoomMetricTargetPayload.model_validate(row) for row in rows]

    def create_target(
        self, payload: RoomMetricTargetRequest, updated_by: uuid.UUID | None
    ) -> RoomMetricTargetPayload:
        self._validate_target(payload)
        row = RoomMetricTarget(**payload.model_dump(), updated_by=updated_by)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return RoomMetricTargetPayload.model_validate(row)

    def update_target(
        self,
        target_id: uuid.UUID,
        payload: RoomMetricTargetRequest,
        updated_by: uuid.UUID | None,
    ) -> RoomMetricTargetPayload:
        self._validate_target(payload)
        row = self.session.get(RoomMetricTarget, target_id)
        if row is None:
            raise LookupError("ROI 目标配置不存在")
        for field, value in payload.model_dump().items():
            setattr(row, field, value)
        row.updated_by = updated_by
        self.session.commit()
        self.session.refresh(row)
        return RoomMetricTargetPayload.model_validate(row)

    def list_rules(self) -> list[HourlyComparisonRulePayload]:
        rows = list(
            self.session.scalars(
                select(HourlyComparisonRule).order_by(HourlyComparisonRule.period_days)
            )
        )
        return [HourlyComparisonRulePayload.model_validate(row) for row in rows]

    def create_rule(
        self, payload: HourlyComparisonRuleRequest, user_id: uuid.UUID | None
    ) -> HourlyComparisonRulePayload:
        self._validate_rule(payload)
        if self.session.scalar(
            select(HourlyComparisonRule.id).where(HourlyComparisonRule.name == payload.name)
        ):
            raise ValueError("规则名称已存在，请使用其他名称")
        row = HourlyComparisonRule(**payload.model_dump(), created_by=user_id, updated_by=user_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return HourlyComparisonRulePayload.model_validate(row)

    def update_rule(
        self,
        rule_id: uuid.UUID,
        payload: HourlyComparisonRuleRequest,
        user_id: uuid.UUID | None,
    ) -> HourlyComparisonRulePayload:
        self._validate_rule(payload)
        row = self.session.get(HourlyComparisonRule, rule_id)
        if row is None:
            raise LookupError("小时周期预警规则不存在")
        duplicate = self.session.scalar(
            select(HourlyComparisonRule.id).where(
                HourlyComparisonRule.name == payload.name,
                HourlyComparisonRule.id != rule_id,
            )
        )
        if duplicate:
            raise ValueError("规则名称已存在，请使用其他名称")
        for field, value in payload.model_dump().items():
            setattr(row, field, value)
        row.updated_by = user_id
        self.session.commit()
        self.session.refresh(row)
        return HourlyComparisonRulePayload.model_validate(row)

    def _resolved_filters(
        self, filters: HourlyComparisonFilters
    ) -> tuple[HourlyComparisonFilters, date | None]:
        self._validate_visible_metrics(filters.metric_ids)
        valid_hours = {descriptor.key for descriptor in hour_descriptors()}
        invalid_hours = sorted(set(filters.natural_hours) - valid_hours)
        if invalid_hours:
            raise ValueError(f"非法自然小时：{', '.join(invalid_hours)}")
        latest = self._latest_complete_date(filters.room_ids)
        if filters.custom_start_date and not filters.custom_end_date:
            raise ValueError("自定义周期必须同时提供开始和结束日期")
        if filters.custom_end_date and not filters.custom_start_date:
            raise ValueError("自定义周期必须同时提供开始和结束日期")
        if filters.custom_start_date and filters.custom_end_date:
            if filters.custom_start_date > filters.custom_end_date:
                raise ValueError("自定义开始日期不能晚于结束日期")
            filters = replace(
                filters,
                end_date=filters.custom_end_date,
                period_days=(filters.custom_end_date - filters.custom_start_date).days + 1,
            )
        elif filters.end_date is None:
            end = self.now.date() if filters.include_today else latest
            filters = replace(filters, end_date=end)
        if filters.period_days not in {1, 3, 5, 7, 15, 30} and not filters.custom_start_date:
            raise ValueError("周期仅支持 1、3、5、7、15、30 天或自定义日期")
        return filters, latest

    def _validate_visible_metrics(self, requested: tuple[str, ...]) -> None:
        visible = list(dict.fromkeys(("period_overall_roi", "period_spend", *requested)))
        if len(visible) > 4:
            raise ValueError("小时比较最多支持4个可见指标（核心2个、附加2个）")
        invalid: list[str] = []
        for key in requested:
            spec = self.catalog.by_key.get(key)
            if spec is None or not spec.supports_hourly_trend or spec.is_cumulative:
                invalid.append(key)
        if invalid:
            raise ValueError(f"指标不支持小时比较：{', '.join(dict.fromkeys(invalid))}")

    def _latest_complete_date(self, requested: tuple[uuid.UUID, ...]) -> date | None:
        allowed = self._effective_room_ids(requested)
        if allowed == set():
            return None
        query = select(func.max(HourlyFact.business_date)).where(
            HourlyFact.data_status == "complete",
            HourlyFact.business_date < self.now.date(),
        )
        if allowed is not None:
            query = query.where(HourlyFact.room_id.in_(allowed))
        return self.session.scalar(query)

    def _facts(
        self,
        filters: HourlyComparisonFilters,
        start_date: date,
        end_date: date,
    ) -> list[HourlyFact]:
        allowed = self._effective_room_ids(filters.room_ids)
        if allowed == set():
            return []
        query: Select[tuple[HourlyFact]] = select(HourlyFact).where(
            HourlyFact.business_date >= start_date,
            HourlyFact.business_date <= end_date,
        )
        if allowed is not None:
            query = query.where(HourlyFact.room_id.in_(allowed))
        if filters.anchor_names:
            query = query.where(HourlyFact.actual_anchor_canonical.in_(filters.anchor_names))
        if filters.control_names:
            query = query.where(HourlyFact.actual_control_canonical.in_(filters.control_names))
        if filters.natural_hours:
            query = query.where(HourlyFact.hour_slot.in_(filters.natural_hours))
        facts = list(
            self.session.scalars(
                query.order_by(HourlyFact.business_date, HourlyFact.hour_order, HourlyFact.room_id)
            )
        )
        if filters.anchor_members:
            selected = set(filters.anchor_members)
            facts = [
                fact for fact in facts if selected.intersection(fact.actual_anchor_base_names or [])
            ]
        return facts

    def _effective_room_ids(self, requested: tuple[uuid.UUID, ...]) -> set[uuid.UUID] | None:
        requested_set = set(requested)
        if self.access.room_ids is None:
            return requested_set or None
        if requested_set:
            return set(self.access.room_ids).intersection(requested_set)
        return set(self.access.room_ids)

    def _rooms_for_facts(
        self, facts: list[HourlyFact], requested: tuple[uuid.UUID, ...]
    ) -> list[Room]:
        room_ids = {fact.room_id for fact in facts}
        allowed = self._effective_room_ids(requested)
        if allowed:
            room_ids.update(allowed)
        if not room_ids:
            return []
        return list(self.session.scalars(select(Room).where(Room.id.in_(room_ids))))

    def _metric_keys(self, requested: tuple[str, ...]) -> tuple[str, ...]:
        selected: list[str] = []
        for key in requested or ("period_overall_roi", "period_spend"):
            if key not in selected:
                selected.append(key)
        for key in ("period_overall_roi", "period_spend", "period_overall_orders"):
            if key not in selected:
                selected.append(key)
        expanded = list(selected)
        index = 0
        while index < len(expanded):
            spec = self.catalog.by_key[expanded[index]]
            for dependency in (spec.numerator, spec.denominator):
                if dependency and dependency not in expanded:
                    expanded.append(dependency)
            index += 1
        return tuple(expanded)

    def _metrics_by_fact(
        self, facts: list[HourlyFact], metric_keys: tuple[str, ...]
    ) -> dict[uuid.UUID, list[HourlyMetric]]:
        result: dict[uuid.UUID, list[HourlyMetric]] = defaultdict(list)
        if not facts:
            return result
        rows = self.session.scalars(
            select(HourlyMetric).where(
                HourlyMetric.hourly_fact_id.in_([fact.id for fact in facts]),
                HourlyMetric.metric_key.in_(metric_keys),
                HourlyMetric.quality_status == "valid",
            )
        )
        for row in rows:
            result[row.hourly_fact_id].append(row)
        return result

    def _identities(
        self,
        facts: list[HourlyFact],
        dimension: SeriesDimension,
        room_map: dict[uuid.UUID, Room],
    ) -> list[SeriesIdentity]:
        if not facts:
            return []
        if dimension == "summary":
            return [SeriesIdentity("summary", "全部直播间", dimension, None, None, None, None)]
        identities: dict[str, SeriesIdentity] = {}
        for fact in facts:
            room = room_map.get(fact.room_id)
            if dimension == "room":
                key = str(fact.room_id)
                identities[key] = SeriesIdentity(
                    key,
                    room.name if room else "未知直播间",
                    dimension,
                    fact.room_id,
                    room.name if room else None,
                    room.category if room else None,
                    None,
                )
            elif dimension == "room_anchor":
                anchor_name = fact.actual_anchor_canonical
                if not anchor_name or anchor_name == "用于计算":
                    continue
                key = f"{fact.room_id}:{anchor_name}"
                room_name = room.name if room else "未知直播间"
                identities[key] = SeriesIdentity(
                    key,
                    f"{room_name}｜{anchor_name}",
                    dimension,
                    fact.room_id,
                    room.name if room else None,
                    room.category if room else None,
                    anchor_name,
                )
            elif dimension == "anchor":
                name = fact.actual_anchor_canonical or "未标记主播"
                identities[name] = SeriesIdentity(name, name, dimension, None, None, None, name)
            else:
                name = fact.actual_control_canonical or "未标记场控"
                identities[name] = SeriesIdentity(name, name, dimension, None, None, None, None)
        ordered = sorted(identities.values(), key=lambda item: item.name)
        return ordered if dimension == "room_anchor" else ordered[:6]

    def _fact_in_identity(self, fact: HourlyFact, identity: SeriesIdentity) -> bool:
        if identity.dimension == "summary":
            return True
        if identity.dimension == "room":
            return fact.room_id == identity.room_id
        if identity.dimension == "room_anchor":
            if fact.room_id != identity.room_id:
                return False
            actual = fact.actual_anchor_canonical
            if actual == identity.anchor_name:
                return True
            return not actual and fact.planned_anchor_canonical == identity.anchor_name
        if identity.dimension == "anchor":
            return (fact.actual_anchor_canonical or "未标记主播") == identity.key
        return (fact.actual_control_canonical or "未标记场控") == identity.key

    def _series(
        self,
        identity: SeriesIdentity,
        facts: list[HourlyFact],
        metrics_by_fact: dict[uuid.UUID, list[HourlyMetric]],
        room_map: dict[uuid.UUID, Room],
        targets: list[TargetCandidate],
        rule: HourlyComparisonRule | None,
        rule_can_push: bool,
        current_period: DatePeriod,
        comparison_period: DatePeriod | None,
        filters: HourlyComparisonFilters,
        metric_keys: tuple[str, ...],
    ) -> HourlyComparisonSeriesPayload:
        current = current_period
        comparison = comparison_period
        identity_facts = [fact for fact in facts if self._fact_in_identity(fact, identity)]
        room_ids = {fact.room_id for fact in identity_facts}
        target_values = [
            select_target(
                room_id=str(room_id),
                room_name=room_map[room_id].name,
                product_category=room_map[room_id].category,
                targets=targets,
            )
            for room_id in room_ids
            if room_id in room_map
        ]
        target = common_target(target_values)
        distinct_targets = {value for value in target_values if value is not None}
        multiple_targets = len(distinct_targets) > 1
        target_message = None
        if multiple_targets:
            target_message = "多目标直播间，汇总图不展示单一目标线"
        elif target is None:
            target_message = "当前直播间未配置ROI目标"
        points = [
            self._point(
                descriptor.key,
                descriptor.label,
                descriptor.sort,
                identity_facts,
                metrics_by_fact,
                current,
                comparison,
                target,
                target_message,
                rule,
                rule_can_push,
                filters,
                metric_keys,
            )
            for descriptor in hour_descriptors()
        ]
        return HourlyComparisonSeriesPayload(
            series_key=identity.key,
            series_name=identity.name,
            dimension=identity.dimension,
            room_id=identity.room_id,
            room_name=identity.room_name,
            product_category=identity.product_category,
            anchor_name=identity.anchor_name,
            roi_target=target,
            multiple_targets=multiple_targets,
            target_message=target_message,
            points=points,
        )

    def _point(
        self,
        hour: str,
        label: str,
        hour_order: int,
        facts: list[HourlyFact],
        metrics_by_fact: dict[uuid.UUID, list[HourlyMetric]],
        current_period: DatePeriod,
        comparison_period: DatePeriod | None,
        target: Decimal | None,
        target_message: str | None,
        rule: HourlyComparisonRule | None,
        rule_can_push: bool,
        filters: HourlyComparisonFilters,
        metric_keys: tuple[str, ...],
    ) -> HourlySeriesPointPayload:
        current_facts = [
            fact
            for fact in facts
            if current_period.start <= fact.business_date <= current_period.end
            and fact.hour_order == hour_order
        ]
        comparison_facts = (
            [
                fact
                for fact in facts
                if comparison_period.start <= fact.business_date <= comparison_period.end
                and fact.hour_order == hour_order
            ]
            if comparison_period
            else []
        )
        current_values = self._period_values(
            current_facts,
            metrics_by_fact,
            current_period,
            hour_order,
            filters,
            metric_keys,
            is_current=True,
        )
        comparison_values = (
            self._period_values(
                comparison_facts,
                metrics_by_fact,
                comparison_period,
                hour_order,
                filters,
                metric_keys,
                is_current=False,
            )
            if comparison_period
            else None
        )
        roi_comparison = compare_values(
            current_values.roi, comparison_values.roi if comparison_values else None
        )
        spend_comparison = compare_values(
            current_values.spend, comparison_values.spend if comparison_values else None
        )
        orders = self._aggregate(
            "period_overall_orders",
            self._valid_facts(current_facts, hour_order, current_period, filters, True),
            metrics_by_fact,
        )
        rule_values = self._rule_values(rule)
        status = evaluate_hourly_status(
            HourlyStatusInput(
                current_roi=current_values.roi,
                baseline_roi=comparison_values.roi if comparison_values else None,
                current_spend=current_values.spend,
                baseline_spend=comparison_values.spend if comparison_values else None,
                target_roi=target,
                coverage_rate=current_values.coverage_rate,
                current_orders=orders,
                minimum_spend=rule_values.minimum_spend,
                minimum_orders=rule_values.minimum_orders,
                minimum_coverage_rate=rule_values.minimum_coverage_rate,
                spend_increase_threshold=rule_values.spend_increase_threshold,
                spend_decrease_threshold=rule_values.spend_decrease_threshold,
                roi_increase_threshold=rule_values.roi_increase_threshold,
                roi_decrease_threshold=rule_values.roi_decrease_threshold,
                is_hour_complete=not current_values.in_progress and not current_values.future,
                is_in_progress=current_values.in_progress,
                data_valid=True,
            )
        )
        should_push = status.should_push and rule_can_push
        target_gap = (
            current_values.roi - target
            if current_values.roi is not None and target is not None
            else None
        )
        target_attainment = (
            current_values.roi / target
            if current_values.roi is not None and target is not None and target != Decimal(0)
            else None
        )
        target_reached = (
            current_values.roi >= target
            if current_values.roi is not None and target is not None
            else None
        )
        return HourlySeriesPointPayload(
            hour=hour,
            label=label,
            sort=hour_order,
            current=current_values,
            comparison=comparison_values,
            comparison_result=HourComparisonResultPayload(
                roi_difference=roi_comparison.difference,
                roi_ratio=roi_comparison.current_to_baseline_ratio,
                roi_percentage=roi_comparison.current_to_baseline_percentage,
                roi_growth=roi_comparison.growth_rate,
                roi_growth_percentage=roi_comparison.growth_percentage,
                spend_difference=spend_comparison.difference,
                spend_ratio=spend_comparison.current_to_baseline_ratio,
                spend_percentage=spend_comparison.current_to_baseline_percentage,
                spend_growth=spend_comparison.growth_rate,
                spend_growth_percentage=spend_comparison.growth_percentage,
                roi_target_gap=target_gap,
                roi_target_attainment=target_attainment,
                roi_target_reached=target_reached,
            ),
            roi_target=target,
            target_message=target_message,
            status=HourStatusPayload(
                code=status.code,
                name=status.name,
                level=status.level,
                reasons=list(status.reasons),
                reason_codes=list(status.reason_codes),
                should_push=should_push,
            ),
        )

    def _period_values(
        self,
        facts: list[HourlyFact],
        metrics_by_fact: dict[uuid.UUID, list[HourlyMetric]],
        period: DatePeriod,
        hour_order: int,
        filters: HourlyComparisonFilters,
        metric_keys: tuple[str, ...],
        *,
        is_current: bool,
    ) -> HourPeriodValuesPayload:
        in_progress = (
            is_current
            and filters.include_today
            and period.end == self.now.date()
            and hour_order == self.now.hour
        )
        future = (
            is_current
            and filters.include_today
            and period.end == self.now.date()
            and hour_order > self.now.hour
        )
        valid_facts = self._valid_facts(facts, hour_order, period, filters, is_current)
        daily: dict[date, list[HourlyFact]] = defaultdict(list)
        for fact in valid_facts:
            daily[fact.business_date].append(fact)
        daily_metric_values: dict[str, list[DailyValue]] = {key: [] for key in metric_keys}
        for business_date, day_facts in daily.items():
            for key in metric_keys:
                value = self._aggregate(key, day_facts, metrics_by_fact)
                if value is not None:
                    daily_metric_values[key].append(DailyValue(business_date, value))
        period_metrics: dict[str, Decimal | None] = {}
        metric_ohlc: dict[str, BusinessKlinePayload | None] = {}
        for key in metric_keys:
            value = self._aggregate(key, valid_facts, metrics_by_fact)
            spec = self.catalog.by_key[key]
            effective_days = len(daily_metric_values[key])
            if (
                filters.aggregation_mode == "daily_average"
                and spec.aggregation == "SUM"
                and value is not None
                and effective_days
            ):
                value /= Decimal(effective_days)
            period_metrics[key] = value
            metric_ohlc[key] = self._kline_payload(build_business_kline(daily_metric_values[key]))
        expected_facts = [
            fact
            for fact in facts
            if data_is_due(
                fact.business_date,
                self.now,
                self.data_submission_deadline_hour,
            )
            and fact_counts_toward_completeness(fact.data_status, fact.anchor_schedule_status)
        ]
        expected_samples = len(expected_facts) if expected_facts else None
        effective_samples = len(valid_facts)
        valid_expected = len([fact for fact in expected_facts if fact in valid_facts])
        coverage_rate = (
            Decimal(valid_expected) / Decimal(expected_samples) if expected_samples else None
        )
        return HourPeriodValuesPayload(
            roi=period_metrics.get("period_overall_roi"),
            spend=period_metrics.get("period_spend"),
            metrics={key: period_metrics.get(key) for key in filters.metric_ids},
            roi_ohlc=metric_ohlc.get("period_overall_roi"),
            spend_ohlc=metric_ohlc.get("period_spend"),
            metric_ohlc={key: metric_ohlc.get(key) for key in filters.metric_ids},
            effective_days=len(daily),
            effective_samples=effective_samples,
            expected_samples=expected_samples,
            coverage_rate=coverage_rate,
            in_progress=in_progress,
            future=future,
        )

    def _valid_facts(
        self,
        facts: list[HourlyFact],
        hour_order: int,
        period: DatePeriod,
        filters: HourlyComparisonFilters,
        is_current: bool,
    ) -> list[HourlyFact]:
        result = [
            fact
            for fact in facts
            if fact.data_status == "complete"
            and fact.actual_anchor_canonical
            and fact.actual_anchor_canonical != "用于计算"
        ]
        if (
            is_current
            and filters.include_today
            and period.end == self.now.date()
            and (
                hour_order > self.now.hour
                or (hour_order == self.now.hour and not filters.include_in_progress)
            )
        ):
            result = [fact for fact in result if fact.business_date < self.now.date()]
        return result

    def _aggregate(
        self,
        metric_key: str,
        facts: list[HourlyFact],
        metrics_by_fact: dict[uuid.UUID, list[HourlyMetric]],
    ) -> Decimal | None:
        observations = [
            MetricObservation(
                room_id=str(fact.room_id),
                business_date=fact.business_date,
                hour_order=fact.hour_order,
                metric_key=metric.metric_key,
                value=metric.numeric_value,
            )
            for fact in facts
            for metric in metrics_by_fact.get(fact.id, [])
        ]
        return aggregate_metric(metric_key, observations, self.catalog)

    def _target_candidates(self, effective_date: date) -> list[TargetCandidate]:
        rows = self.session.scalars(
            select(RoomMetricTarget).where(
                RoomMetricTarget.enabled.is_(True),
                RoomMetricTarget.metric_code == "period_overall_roi",
                (RoomMetricTarget.effective_start_date.is_(None))
                | (RoomMetricTarget.effective_start_date <= effective_date),
                (RoomMetricTarget.effective_end_date.is_(None))
                | (RoomMetricTarget.effective_end_date >= effective_date),
            )
        )
        return [
            TargetCandidate(
                room_id=str(row.room_id) if row.room_id else None,
                room_name=row.room_name,
                product_category=row.product_category,
                target_value=row.target_value,
            )
            for row in rows
        ]

    def _rule(self, period_days: int) -> tuple[HourlyComparisonRule | None, bool]:
        if self.rule_override is not None:
            rule = self.rule_override if self.rule_override.period_days == period_days else None
            return rule, bool(rule and rule.enabled and rule.push_enabled)
        rule = self.session.scalar(
            select(HourlyComparisonRule)
            .where(
                HourlyComparisonRule.period_days == period_days,
                HourlyComparisonRule.enabled.is_(True),
            )
            .order_by(HourlyComparisonRule.created_at)
            .limit(1)
        )
        return rule, bool(rule and rule.push_enabled)

    @staticmethod
    def _rule_values(rule: HourlyComparisonRule | None) -> RuleThresholds:
        return RuleThresholds(
            spend_increase_threshold=(rule.spend_increase_threshold if rule else Decimal("0.30")),
            spend_decrease_threshold=(rule.spend_decrease_threshold if rule else Decimal("-0.30")),
            roi_increase_threshold=(rule.roi_increase_threshold if rule else Decimal("0.30")),
            roi_decrease_threshold=(rule.roi_decrease_threshold if rule else Decimal("-0.30")),
            minimum_spend=rule.minimum_spend if rule else Decimal(0),
            minimum_orders=rule.minimum_orders if rule else 0,
            minimum_coverage_rate=(rule.minimum_coverage_rate if rule else Decimal("0.80")),
        )

    def _daily_row(
        self,
        fact: HourlyFact,
        room: Room | None,
        metrics_by_fact: dict[uuid.UUID, list[HourlyMetric]],
        targets: list[TargetCandidate],
        period_type: str,
    ) -> dict[str, object]:
        values = {
            key: self._aggregate(key, [fact], metrics_by_fact)
            for key in (
                "period_overall_amount",
                "period_spend",
                "period_overall_roi",
                "period_order_count",
                "period_overall_order_cost",
            )
            if key in self.catalog.by_key
        }
        target = select_target(
            room_id=str(fact.room_id),
            room_name=room.name if room else "",
            product_category=room.category if room else None,
            targets=targets,
        )
        roi = values.get("period_overall_roi")
        return {
            "period_type": period_type,
            "date": fact.business_date,
            "room": room.name if room else "未知直播间",
            "anchor": fact.actual_anchor_canonical,
            "controller": fact.actual_control_canonical,
            "planned_anchor": fact.planned_anchor_canonical,
            "schedule_match": fact.anchor_match_status,
            "period_overall_amount": values.get("period_overall_amount"),
            "period_spend": values.get("period_spend"),
            "period_overall_roi": roi,
            "period_order_count": values.get("period_order_count"),
            "period_overall_order_cost": values.get("period_overall_order_cost"),
            "roi_target": target,
            "roi_target_reached": roi >= target if roi is not None and target is not None else None,
            "data_status": fact.data_status,
            "latest_observed_at": fact.latest_observed_at,
        }

    @staticmethod
    def _room_detail_row(
        series: HourlyComparisonSeriesPayload, natural_hour: str
    ) -> dict[str, object]:
        point = next(item for item in series.points if item.hour == natural_hour)
        return {
            "room_id": series.room_id,
            "room": series.room_name,
            "product_category": series.product_category,
            "roi_target": point.roi_target,
            "current_roi": point.current.roi,
            "baseline_roi": point.comparison.roi if point.comparison else None,
            "roi_growth": point.comparison_result.roi_growth,
            "current_spend": point.current.spend,
            "baseline_spend": point.comparison.spend if point.comparison else None,
            "spend_growth": point.comparison_result.spend_growth,
            "status": point.status.name,
            "effective_days": point.current.effective_days,
            "coverage_rate": point.current.coverage_rate,
        }

    @staticmethod
    def _kline_detail_row(
        metric_name: str, period_type: str, kline: BusinessKlinePayload | None
    ) -> dict[str, object]:
        if kline is None:
            return {"metric": metric_name, "period_type": period_type}
        return {
            "metric": metric_name,
            "period_type": period_type,
            **kline.model_dump(),
        }

    def _raw_records(
        self,
        filters: HourlyComparisonFilters,
        start_date: date,
        end_date: date,
        page: int,
        page_size: int,
        room_map: dict[uuid.UUID, Room],
    ) -> tuple[list[dict[str, object]], int]:
        allowed = self._effective_room_ids(filters.room_ids)
        if allowed == set():
            return [], 0
        query = (
            select(LivePoint, RawSourceRecord, SourceConfig)
            .join(RawSourceRecord, RawSourceRecord.id == LivePoint.raw_source_record_id)
            .join(SourceConfig, SourceConfig.id == RawSourceRecord.source_config_id)
            .where(
                LivePoint.business_date >= start_date,
                LivePoint.business_date <= end_date,
            )
        )
        if allowed is not None:
            query = query.where(LivePoint.room_id.in_(allowed))
        if filters.natural_hours:
            query = query.where(LivePoint.hour_slot.in_(filters.natural_hours))
        if filters.anchor_names:
            query = query.where(LivePoint.anchor_canonical.in_(filters.anchor_names))
        if filters.control_names:
            query = query.where(LivePoint.control_canonical.in_(filters.control_names))
        if filters.anchor_members:
            query = query.where(
                or_(
                    *(
                        LivePoint.anchor_members.contains([member])
                        for member in filters.anchor_members
                    )
                )
            )
        total = (
            self.session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
            or 0
        )
        selected = list(
            self.session.execute(
                query.order_by(LivePoint.observed_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return (
            [
                {
                    "id": str(point.id),
                    "observed_at": point.observed_at,
                    "business_date": point.business_date,
                    "room": room_map[point.room_id].name
                    if point.room_id in room_map
                    else "未知直播间",
                    "hour": point.hour_slot,
                    "anchor": point.anchor_canonical,
                    "controller": point.control_canonical,
                    "raw_payload": raw.raw_fields,
                    "source_name": source.name,
                    "source_role": source.source_role,
                    "source_base": "[REDACTED]",
                    "source_table": "[REDACTED]",
                    "source_record_id": raw.source_record_id,
                    "source_modified_at": raw.source_modified_at,
                    "sync_time": raw.last_seen_at,
                    "source_deleted": raw.is_deleted,
                    "valid": point.valid,
                    "invalid_reason": point.invalid_reason,
                    "updated_at": point.updated_at,
                }
                for point, raw, source in selected
            ],
            total,
        )

    def _metric_options(self) -> list[MetricOption]:
        return [
            MetricOption(
                key=spec.key,
                name=spec.field,
                category=spec.category,
                unit=spec.unit,
                precision=spec.precision,
                scope=spec.scope,
                aggregation=spec.aggregation,
                numerator=spec.numerator,
                denominator=spec.denominator,
                direction=spec.direction,
                default_visible=spec.default,
                analysis_default=spec.analysis_default,
                supports_hourly_trend=spec.supports_hourly_trend,
                supports_kline=spec.supports_kline,
                supports_alerts=spec.alertable,
                is_cumulative=spec.is_cumulative,
            )
            for spec in self.catalog.specs
            if spec.supports_hourly_trend and not spec.is_cumulative
        ]

    @staticmethod
    def _kline_payload(kline: BusinessKline | None) -> BusinessKlinePayload | None:
        if kline is None:
            return None
        return BusinessKlinePayload(
            open=kline.open,
            close=kline.close,
            high=kline.high,
            low=kline.low,
            average=kline.average,
            median=kline.median,
            total=kline.total,
            effective_days=kline.effective_days,
            first_date=kline.first_date,
            last_date=kline.last_date,
            high_date=kline.high_date,
            low_date=kline.low_date,
        )

    @staticmethod
    def _kline_value(
        kline: BusinessKlinePayload | None, field: Literal["open", "close", "high", "low"]
    ) -> Decimal | None:
        return getattr(kline, field) if kline else None

    @staticmethod
    def _validate_target(payload: RoomMetricTargetRequest) -> None:
        if not any((payload.room_id, payload.room_name, payload.product_category)):
            raise ValueError("直播间ID、直播间名称和产品品类至少填写一项")
        if payload.target_value <= 0:
            raise ValueError("ROI目标必须大于0")
        if (
            payload.effective_start_date
            and payload.effective_end_date
            and payload.effective_start_date > payload.effective_end_date
        ):
            raise ValueError("目标生效开始日期不能晚于结束日期")

    @staticmethod
    def _validate_rule(payload: HourlyComparisonRuleRequest) -> None:
        if payload.spend_increase_threshold < 0 or payload.roi_increase_threshold < 0:
            raise ValueError("上涨阈值不能小于0")
        if payload.roi_decrease_threshold > 0:
            raise ValueError("ROI下降阈值必须小于或等于0")
        if payload.spend_decrease_threshold > 0:
            raise ValueError("消耗下降阈值必须小于或等于0")
        if payload.minimum_spend < 0:
            raise ValueError("最小消耗不能小于0")
        if not Decimal(0) <= payload.minimum_coverage_rate <= Decimal(1):
            raise ValueError("最低完整率必须在0到1之间")
        if not re.fullmatch(
            r"(?:manual|daily@(?:[01]\d|2[0-3]):[0-5]\d|weekly:[1-7]@(?:[01]\d|2[0-3]):[0-5]\d)",
            payload.push_schedule,
        ):
            raise ValueError("任务时刻仅支持 manual、daily@HH:MM 或 weekly:1-7@HH:MM")
