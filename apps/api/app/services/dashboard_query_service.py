from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ComparisonPayload,
    DetailResponse,
    FilterOptionsResponse,
    KpiPayload,
    MetricOption,
    OverviewResponse,
    RoomOption,
    TimelineGroup,
    TimelineResponse,
    TimelineSeries,
    XItem,
)
from app.auth.dependencies import AccessScope
from app.core.config import get_settings
from app.domain.aggregation import MetricObservation, aggregate_metric
from app.domain.data_freshness import (
    data_is_due,
    fact_counts_toward_completeness,
    schedule_expects_data,
)
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    AlertEvent,
    AlertRule,
    HourlyFact,
    HourlyMetric,
    LivePoint,
    LivePointMetric,
    Room,
    SourceConfig,
)
from app.services.comparison_service import ComparisonService


@dataclass(frozen=True)
class DashboardFilters:
    start_date: date | None = None
    end_date: date | None = None
    room_ids: tuple[uuid.UUID, ...] = ()
    anchor_names: tuple[str, ...] = ()
    anchor_members: tuple[str, ...] = ()
    control_names: tuple[str, ...] = ()
    hour_slots: tuple[str, ...] = ()


class DashboardQueryService:
    DEFAULT_KPIS = (
        "period_overall_amount",
        "period_spend",
        "period_overall_roi",
        "period_net_roi",
        "period_order_count",
        "period_overall_order_cost",
        "period_viewers",
        "period_buyers",
    )

    def __init__(self, session: Session, catalog: MetricCatalog, access: AccessScope) -> None:
        self.session = session
        self.catalog = catalog
        self.access = access
        self.comparisons = ComparisonService()

    def filter_options(self) -> FilterOptionsResponse:
        rooms = self._rooms()
        allowed = {room.id for room in rooms}
        fact_query = select(HourlyFact).where(HourlyFact.data_status == "complete")
        if allowed:
            fact_query = fact_query.where(HourlyFact.room_id.in_(allowed))
        facts = list(self.session.scalars(fact_query)) if allowed else []
        points = (
            list(
                self.session.scalars(
                    select(LivePoint).where(
                        LivePoint.valid.is_(True), LivePoint.room_id.in_(allowed)
                    )
                )
            )
            if allowed
            else []
        )
        dates = sorted({fact.business_date for fact in facts})
        return FilterOptionsResponse(
            min_date=dates[0] if dates else None,
            max_date=dates[-1] if dates else None,
            months=sorted({item.strftime("%Y-%m") for item in dates}),
            rooms=[RoomOption(id=room.id, name=room.name) for room in rooms],
            anchors=sorted({point.anchor_canonical for point in points if point.anchor_canonical}),
            anchor_members=sorted(
                {member for point in points for member in point.anchor_members if member}
            ),
            controls=sorted(
                {point.control_canonical for point in points if point.control_canonical}
            ),
            hour_slots=[f"{hour:02d}-{hour + 1:02d}" for hour in range(24)],
            metrics=[
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
                    supports_hourly_trend=spec.supports_hourly_trend,
                    supports_kline=spec.supports_kline,
                    supports_alerts=spec.alertable,
                    is_cumulative=spec.is_cumulative,
                )
                for spec in self.catalog.specs
            ],
            comparison_types=["previous_day", "previous_week", "custom", "previous_month"],
        )

    def overview(self, filters: DashboardFilters) -> OverviewResponse:
        facts = self._facts(filters)
        if not facts and not filters.start_date and not filters.end_date:
            latest = self.session.scalar(
                select(func.max(HourlyFact.business_date)).where(
                    HourlyFact.data_status == "complete"
                )
            )
            if latest:
                filters = DashboardFilters(
                    start_date=latest,
                    end_date=latest,
                    room_ids=filters.room_ids,
                    anchor_names=filters.anchor_names,
                    anchor_members=filters.anchor_members,
                    control_names=filters.control_names,
                    hour_slots=filters.hour_slots,
                )
                facts = self._facts(filters)
        observations = self._observations(facts)
        baseline_filters = self._previous_period(filters)
        baseline = self._observations(self._facts(baseline_filters))
        kpis: list[KpiPayload] = []
        for metric_key in self.DEFAULT_KPIS:
            spec = self.catalog.by_key[metric_key]
            current_value = aggregate_metric(metric_key, observations, self.catalog)
            baseline_value = aggregate_metric(metric_key, baseline, self.catalog)
            comparison = self.comparisons.compare(
                current_value,
                baseline_value,
                metric_label=spec.field,
                baseline_label="昨日同小时",
            )
            kpis.append(
                KpiPayload(
                    metric_key=metric_key,
                    name=spec.field,
                    unit=spec.unit,
                    precision=spec.precision,
                    direction=spec.direction,
                    value=current_value,
                    comparison=ComparisonPayload(**comparison.__dict__),
                )
            )
        all_facts = self._facts(filters, complete_only=False)
        settings = get_settings()
        now = datetime.now(ZoneInfo(settings.timezone))
        due_facts = [
            fact
            for fact in all_facts
            if data_is_due(fact.business_date, now, settings.data_submission_deadline_hour)
            and fact_counts_toward_completeness(fact.data_status, fact.anchor_schedule_status)
        ]
        complete = sum(fact.data_status == "complete" for fact in due_facts)
        matched = sum(fact.anchor_match_status == "matched" for fact in facts)
        scheduled = sum(schedule_expects_data(fact.anchor_schedule_status) for fact in facts)
        room_ranking = self._room_ranking(facts)
        return OverviewResponse(
            start_date=filters.start_date,
            end_date=filters.end_date,
            kpis=kpis,
            room_ranking=room_ranking,
            anchor_match_rate=(Decimal(matched) / Decimal(scheduled) if scheduled else None),
            data_completeness=(Decimal(complete) / Decimal(len(due_facts)) if due_facts else None),
            data_submission_deadline_hour=settings.data_submission_deadline_hour,
            active_alerts=self._active_alert_count(filters),
            sync_mode=self._sync_mode(),
        )

    def _sync_mode(self) -> Literal["feishu", "feishu_base_export", "fixture_mock"]:
        source_types = set(
            self.session.scalars(
                select(SourceConfig.source_type).where(
                    SourceConfig.enabled.is_(True),
                    SourceConfig.last_success_at.is_not(None),
                )
            )
        )
        if "feishu_bitable" in source_types:
            return "feishu"
        if "feishu_base_export" in source_types:
            return "feishu_base_export"
        return "fixture_mock"

    def timeline(
        self,
        filters: DashboardFilters,
        grain: Literal["hour", "point"],
        metric_keys: tuple[str, ...],
    ) -> TimelineResponse:
        valid_metrics = tuple(key for key in metric_keys if key in self.catalog.by_key)
        if not valid_metrics:
            valid_metrics = tuple(spec.key for spec in self.catalog.specs if spec.default)[:4]
        return (
            self._hour_timeline(filters, valid_metrics)
            if grain == "hour"
            else self._point_timeline(filters, valid_metrics)
        )

    def hourly_detail(self, fact_id: uuid.UUID) -> DetailResponse:
        fact = self.session.get(HourlyFact, fact_id)
        if fact is None or not self._room_allowed(fact.room_id):
            raise LookupError("小时事实不存在或无权访问")
        room = self.session.get(Room, fact.room_id)
        metric_rows = self.session.scalars(
            select(HourlyMetric).where(HourlyMetric.hourly_fact_id == fact.id)
        )
        points = list(
            self.session.scalars(
                select(LivePoint)
                .where(
                    LivePoint.room_id == fact.room_id,
                    LivePoint.business_date == fact.business_date,
                    LivePoint.hour_slot == fact.hour_slot,
                )
                .order_by(LivePoint.observed_at)
            )
        )
        return DetailResponse(
            id=fact.id,
            room=room.name if room else "未知直播间",
            base={
                "date": fact.business_date,
                "hour_slot": fact.hour_slot,
                "anchor": fact.actual_anchor_canonical,
                "control": fact.actual_control_canonical,
                "planned_anchor": fact.planned_anchor_canonical,
                "anchor_match_status": fact.anchor_match_status,
                "data_status": fact.data_status,
                "latest_observed_at": fact.latest_observed_at,
            },
            metrics={row.metric_key: row.numeric_value for row in metric_rows},
            points=[
                {
                    "id": str(point.id),
                    "observed_at": point.observed_at,
                    "valid": point.valid,
                    "invalid_reason": point.invalid_reason,
                }
                for point in points
            ],
        )

    def point_detail(self, point_id: uuid.UUID) -> DetailResponse:
        point = self.session.get(LivePoint, point_id)
        if point is None or not self._room_allowed(point.room_id):
            raise LookupError("采集点不存在或无权访问")
        room = self.session.get(Room, point.room_id)
        metric_rows = self.session.scalars(
            select(LivePointMetric).where(LivePointMetric.live_point_id == point.id)
        )
        return DetailResponse(
            id=point.id,
            room=room.name if room else "未知直播间",
            base={
                "date": point.business_date,
                "observed_at": point.observed_at,
                "hour_slot": point.hour_slot,
                "anchor": point.anchor_canonical,
                "anchor_note": point.anchor_note,
                "control": point.control_canonical,
                "valid": point.valid,
                "invalid_reason": point.invalid_reason,
            },
            metrics={row.metric_key: row.numeric_value for row in metric_rows},
            raw_payload=point.raw_payload,
        )

    def _facts(self, filters: DashboardFilters, *, complete_only: bool = True) -> list[HourlyFact]:
        query: Select[tuple[HourlyFact]] = select(HourlyFact)
        if complete_only:
            query = query.where(HourlyFact.data_status == "complete")
        allowed = self._effective_room_ids(filters.room_ids)
        if allowed is not None:
            if not allowed:
                return []
            query = query.where(HourlyFact.room_id.in_(allowed))
        if filters.start_date:
            query = query.where(HourlyFact.business_date >= filters.start_date)
        if filters.end_date:
            query = query.where(HourlyFact.business_date <= filters.end_date)
        if filters.anchor_names:
            query = query.where(HourlyFact.actual_anchor_canonical.in_(filters.anchor_names))
        if filters.control_names:
            query = query.where(HourlyFact.actual_control_canonical.in_(filters.control_names))
        if filters.hour_slots:
            query = query.where(HourlyFact.hour_slot.in_(filters.hour_slots))
        facts = list(
            self.session.scalars(query.order_by(HourlyFact.business_date, HourlyFact.hour_order))
        )
        if filters.anchor_members:
            selected = set(filters.anchor_members)
            facts = [fact for fact in facts if selected.intersection(fact.actual_anchor_base_names)]
        return facts

    def _active_alert_count(self, filters: DashboardFilters) -> int:
        query = select(AlertEvent).where(AlertEvent.acknowledged.is_(False))
        allowed = self._effective_room_ids(filters.room_ids)
        if allowed is not None:
            if not allowed:
                return 0
            query = query.where(AlertEvent.room_id.in_(allowed))
        if filters.start_date:
            query = query.where(AlertEvent.business_date >= filters.start_date)
        if filters.end_date:
            query = query.where(AlertEvent.business_date <= filters.end_date)
        if filters.anchor_names:
            query = query.where(AlertEvent.anchor_name.in_(filters.anchor_names))
        if filters.control_names:
            query = query.where(AlertEvent.control_name.in_(filters.control_names))
        if filters.hour_slots:
            query = query.where(AlertEvent.hour_slot.in_(filters.hour_slots))
        events = list(self.session.scalars(query))
        if events:
            rule_types: dict[uuid.UUID, str] = {
                rule_id: rule_type
                for rule_id, rule_type in self.session.execute(
                    select(AlertRule.id, AlertRule.rule_type).where(
                        AlertRule.id.in_({event.rule_id for event in events})
                    )
                )
            }
            settings = get_settings()
            now = datetime.now(ZoneInfo(settings.timezone))
            events = [
                event
                for event in events
                if rule_types.get(event.rule_id) != "data_delay"
                or data_is_due(
                    event.business_date,
                    now,
                    settings.data_submission_deadline_hour,
                )
            ]
        if filters.anchor_members:
            slots = {
                (fact.room_id, fact.business_date, fact.hour_slot)
                for fact in self._facts(filters, complete_only=False)
            }
            events = [
                event
                for event in events
                if (event.room_id, event.business_date, event.hour_slot) in slots
            ]
        return len(events)

    def _observations(self, facts: list[HourlyFact]) -> list[MetricObservation]:
        if not facts:
            return []
        rows = self.session.execute(
            select(HourlyMetric, HourlyFact)
            .join(HourlyFact, HourlyMetric.hourly_fact_id == HourlyFact.id)
            .where(HourlyFact.id.in_([fact.id for fact in facts]))
        )
        return [
            MetricObservation(
                room_id=str(fact.room_id),
                business_date=fact.business_date,
                hour_order=fact.hour_order,
                metric_key=metric.metric_key,
                value=metric.numeric_value,
            )
            for metric, fact in rows
        ]

    def _hour_timeline(
        self, filters: DashboardFilters, metric_keys: tuple[str, ...]
    ) -> TimelineResponse:
        facts = self._facts(filters)
        room_map = {room.id: room.name for room in self._rooms()}
        metrics = (
            list(
                self.session.scalars(
                    select(HourlyMetric).where(
                        HourlyMetric.hourly_fact_id.in_([fact.id for fact in facts]),
                        HourlyMetric.metric_key.in_(metric_keys),
                    )
                )
            )
            if facts
            else []
        )
        values = {(row.hourly_fact_id, row.metric_key): row.numeric_value for row in metrics}
        groups: list[TimelineGroup] = []
        by_room: dict[uuid.UUID, list[HourlyFact]] = defaultdict(list)
        for fact in facts:
            by_room[fact.room_id].append(fact)
        multi_day = len({fact.business_date for fact in facts}) > 1
        for room_id, room_facts in by_room.items():
            x_items = [
                XItem(
                    key=(
                        f"{fact.business_date}|{fact.hour_slot}|"
                        f"{fact.actual_anchor_canonical or '未标记'}"
                    ),
                    fact_id=fact.id,
                    label=(
                        f"{fact.business_date:%m-%d} {fact.hour_slot}\n"
                        f"{fact.actual_anchor_canonical or '未标记'}"
                        if multi_day
                        else f"{fact.hour_slot}\n{fact.actual_anchor_canonical or '未标记'}"
                    ),
                    date=fact.business_date,
                    hour_slot=fact.hour_slot,
                    anchor=fact.actual_anchor_canonical,
                    control=fact.actual_control_canonical,
                    observed_at=fact.latest_observed_at,
                )
                for fact in room_facts
            ]
            series = [
                TimelineSeries(
                    metric_key=key,
                    name=self.catalog.by_key[key].field,
                    unit=self.catalog.by_key[key].unit,
                    axis_group=self.catalog.by_key[key].unit,
                    data=[values.get((fact.id, key)) for fact in room_facts],
                )
                for key in metric_keys
            ]
            groups.append(
                TimelineGroup(
                    group_key=str(room_id),
                    group_label=room_map.get(room_id, "未知直播间"),
                    x_items=x_items,
                    series=series,
                )
            )
        return TimelineResponse(grain="hour", groups=groups)

    def _point_timeline(
        self, filters: DashboardFilters, metric_keys: tuple[str, ...]
    ) -> TimelineResponse:
        query = select(LivePoint).where(LivePoint.valid.is_(True))
        allowed = self._effective_room_ids(filters.room_ids)
        if allowed is not None:
            if not allowed:
                return TimelineResponse(grain="point", groups=[])
            query = query.where(LivePoint.room_id.in_(allowed))
        if filters.start_date:
            query = query.where(LivePoint.business_date >= filters.start_date)
        if filters.end_date:
            query = query.where(LivePoint.business_date <= filters.end_date)
        if filters.anchor_names:
            query = query.where(LivePoint.anchor_canonical.in_(filters.anchor_names))
        if filters.control_names:
            query = query.where(LivePoint.control_canonical.in_(filters.control_names))
        if filters.hour_slots:
            query = query.where(LivePoint.hour_slot.in_(filters.hour_slots))
        points = list(
            self.session.scalars(
                query.order_by(LivePoint.business_date, LivePoint.hour_order, LivePoint.observed_at)
            )
        )
        if filters.anchor_members:
            selected = set(filters.anchor_members)
            points = [
                point for point in points if selected.intersection(point.anchor_members or [])
            ]
        metrics = (
            list(
                self.session.scalars(
                    select(LivePointMetric).where(
                        LivePointMetric.live_point_id.in_([point.id for point in points]),
                        LivePointMetric.metric_key.in_(metric_keys),
                    )
                )
            )
            if points
            else []
        )
        values = {(row.live_point_id, row.metric_key): row.numeric_value for row in metrics}
        room_map = {room.id: room.name for room in self._rooms()}
        by_room: dict[uuid.UUID, list[LivePoint]] = defaultdict(list)
        for point in points:
            by_room[point.room_id].append(point)
        groups: list[TimelineGroup] = []
        for room_id, room_points in by_room.items():
            x_items = [
                XItem(
                    key=f"{point.observed_at.isoformat()}|{point.anchor_canonical or '未标记'}",
                    point_id=point.id,
                    label=f"{point.observed_at:%H:%M}\n{point.anchor_canonical or '未标记'}",
                    date=point.business_date,
                    hour_slot=point.hour_slot,
                    anchor=point.anchor_canonical,
                    control=point.control_canonical,
                    observed_at=point.observed_at,
                )
                for point in room_points
            ]
            groups.append(
                TimelineGroup(
                    group_key=str(room_id),
                    group_label=room_map.get(room_id, "未知直播间"),
                    x_items=x_items,
                    series=[
                        TimelineSeries(
                            metric_key=key,
                            name=self.catalog.by_key[key].field,
                            unit=self.catalog.by_key[key].unit,
                            axis_group=self.catalog.by_key[key].unit,
                            data=[values.get((point.id, key)) for point in room_points],
                        )
                        for key in metric_keys
                    ],
                )
            )
        return TimelineResponse(grain="point", groups=groups)

    def _rooms(self) -> list[Room]:
        query = select(Room).where(Room.active.is_(True)).order_by(Room.sort_order, Room.name)
        if self.access.room_ids is not None:
            query = query.where(Room.id.in_(self.access.room_ids))
        return list(self.session.scalars(query))

    def _room_allowed(self, room_id: uuid.UUID) -> bool:
        return self.access.room_ids is None or room_id in self.access.room_ids

    def _effective_room_ids(self, requested: tuple[uuid.UUID, ...]) -> set[uuid.UUID] | None:
        requested_set = set(requested)
        if self.access.room_ids is None:
            return requested_set or None
        return (
            set(self.access.room_ids).intersection(requested_set)
            if requested_set
            else set(self.access.room_ids)
        )

    def _previous_period(self, filters: DashboardFilters) -> DashboardFilters:
        start = filters.start_date
        end = filters.end_date or start
        if not start or not end:
            return filters
        days = (end - start).days + 1
        return DashboardFilters(
            start_date=start - timedelta(days=days),
            end_date=end - timedelta(days=days),
            room_ids=filters.room_ids,
            anchor_names=filters.anchor_names,
            anchor_members=filters.anchor_members,
            control_names=filters.control_names,
            hour_slots=filters.hour_slots,
        )

    def _room_ranking(self, facts: list[HourlyFact]) -> list[dict[str, Any]]:
        rooms = {room.id: room.name for room in self._rooms()}
        by_room: dict[uuid.UUID, list[HourlyFact]] = defaultdict(list)
        for fact in facts:
            by_room[fact.room_id].append(fact)
        ranking = []
        for room_id, room_facts in by_room.items():
            observations = self._observations(room_facts)
            ranking.append(
                {
                    "room_id": str(room_id),
                    "room_name": rooms.get(room_id, "未知直播间"),
                    "amount": aggregate_metric("period_overall_amount", observations, self.catalog),
                    "roi": aggregate_metric("period_overall_roi", observations, self.catalog),
                    "hours": len(room_facts),
                }
            )
        return sorted(ranking, key=lambda item: item["amount"] or Decimal(0), reverse=True)
