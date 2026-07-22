from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AccessScope
from app.core.config import Settings, get_settings
from app.db.base import utc_now
from app.domain.anchor_trends import AnchorTrendInput, evaluate_anchor_trend
from app.domain.metrics import MetricCatalog
from app.integrations.feishu.bot import FeishuBotClient
from app.models.entities import (
    AnchorTrendEvent,
    AnchorTrendItem,
    HourlyComparisonRule,
    HourlyFact,
    HourlyMetric,
    Person,
    PersonAlias,
)
from app.services.alert_service import AlertService
from app.services.hourly_comparison_service import (
    HourlyComparisonFilters,
    HourlyComparisonService,
)

SUPPORTED_PERIOD_DAYS = frozenset({1, 3, 5, 7, 15, 30})
TREND_RULE_TYPE = "anchor_trend_summary"
NOTIFICATION_TYPES = {
    "rise": "anchor_rise_summary",
    "fall": "anchor_fall_summary",
    "insufficient": "anchor_insufficient_summary",
}
DISPLAY_LIMIT_MAX = 10
COMPARISON_BASIS = "等长完整自然日汇总；ROI采用成交金额合计÷消耗合计；完整率门槛控制样本差异"


@dataclass(frozen=True)
class TrendCalculation:
    room_id: uuid.UUID
    room_name: str
    anchor_id: uuid.UUID | None
    anchor_name: str
    control_names: tuple[str, ...]
    trend_type: Literal["rise", "fall", "neutral", "insufficient"]
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
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    major_rise_hours: tuple[str, ...]
    major_fall_hours: tuple[str, ...]
    major_spend_hours: tuple[str, ...]
    hourly_details: tuple[dict[str, Any], ...]
    current_effective_days: int
    baseline_effective_days: int
    current_effective_hours: int
    baseline_effective_hours: int
    current_coverage_rate: Decimal | None
    baseline_coverage_rate: Decimal | None
    suggestion: str


class AnchorTrendService:
    def __init__(
        self,
        session: Session,
        catalog: MetricCatalog,
        access: AccessScope,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog
        self.access = access
        self.settings = settings or get_settings()
        self.timezone = ZoneInfo(self.settings.timezone)

    def latest_complete_date(self, now: datetime | None = None) -> date:
        local_now = now.astimezone(self.timezone) if now else datetime.now(self.timezone)
        candidate = local_now.date() - timedelta(days=1)
        if local_now.hour < self.settings.data_submission_deadline_hour:
            candidate -= timedelta(days=1)
        return candidate

    def calculate(
        self,
        rule: HourlyComparisonRule,
        *,
        end_date: date | None = None,
        room_ids: tuple[uuid.UUID, ...] = (),
        anchor_names: tuple[str, ...] = (),
        minimum_coverage_rate: Decimal | None = None,
    ) -> tuple[Any, list[TrendCalculation]]:
        self._validate_period(rule.period_days)
        effective_end = end_date or self.latest_complete_date()
        effective_room_ids, impossible_scope = self._effective_room_ids(rule, room_ids)
        if impossible_scope:
            return self._empty_response(rule, effective_end), []
        rule_anchor_names = tuple(str(value) for value in (rule.applicable_anchors or []))
        effective_anchor_names = anchor_names or rule_anchor_names
        if anchor_names and rule_anchor_names:
            allowed_anchor_names = set(rule_anchor_names)
            effective_anchor_names = tuple(
                name for name in anchor_names if name in allowed_anchor_names
            )
            if not effective_anchor_names:
                return self._empty_response(rule, effective_end), []
        response = HourlyComparisonService(
            self.session,
            self.catalog,
            self.access,
            rule_override=rule,
        ).compare(
            HourlyComparisonFilters(
                end_date=effective_end,
                period_days=rule.period_days,
                metric_ids=(
                    "period_overall_roi",
                    "period_spend",
                    "period_overall_amount",
                    "period_overall_orders",
                ),
                room_ids=effective_room_ids,
                anchor_names=effective_anchor_names,
                series_dimension="room_anchor",
                include_today=False,
                include_in_progress=False,
            )
        )
        controls = self._control_names(
            response.comparison_period.start
            if response.comparison_period
            else response.current_period.start,
            response.current_period.end,
            effective_room_ids,
        )
        person_ids = self._anchor_person_ids()
        coverage_threshold = minimum_coverage_rate or rule.minimum_coverage_rate
        calculations = [
            self._aggregate_series(
                series,
                rule,
                controls,
                person_ids,
                coverage_threshold,
                response.current_period.complete,
                bool(response.comparison_period and response.comparison_period.complete),
            )
            for series in response.series
            if series.room_id is not None and series.room_name and series.anchor_name
        ]
        return response, calculations

    def _empty_response(self, rule: HourlyComparisonRule, end_date: date) -> Any:
        return HourlyComparisonService(
            self.session,
            self.catalog,
            self.access,
            rule_override=rule,
        ).compare(
            HourlyComparisonFilters(
                end_date=end_date,
                period_days=rule.period_days,
                room_ids=(uuid.UUID(int=0),),
                anchor_names=("__no_authorized_anchor__",),
                series_dimension="room_anchor",
                include_in_progress=False,
            )
        )

    def recalculate(
        self,
        *,
        rule_id: uuid.UUID | None = None,
        period_days: int = 3,
        end_date: date | None = None,
        room_ids: tuple[uuid.UUID, ...] = (),
        anchor_names: tuple[str, ...] = (),
        minimum_coverage_rate: Decimal | None = None,
        operator_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        rule = self._rule(rule_id=rule_id, period_days=period_days)
        response, calculations = self.calculate(
            rule,
            end_date=end_date,
            room_ids=room_ids,
            anchor_names=anchor_names,
            minimum_coverage_rate=minimum_coverage_rate,
        )
        grouped = {
            trend_type: [item for item in calculations if item.trend_type == trend_type]
            for trend_type in ("rise", "fall", "insufficient")
        }
        grouped["rise"].sort(
            key=lambda item: (item.roi_growth_rate is not None, item.roi_growth_rate or Decimal(0)),
            reverse=True,
        )
        grouped["fall"].sort(
            key=lambda item: (item.roi_growth_rate is None, item.roi_growth_rate or Decimal(0))
        )
        grouped["insufficient"].sort(key=lambda item: (item.room_name, item.anchor_name))
        event_ids: dict[str, uuid.UUID] = {}
        for trend_type, items in grouped.items():
            if not items:
                continue
            event = self._persist_summary_event(
                rule,
                trend_type,
                items,
                current_start=response.current_period.start,
                current_end=response.current_period.end,
                baseline_start=response.comparison_period.start,
                baseline_end=response.comparison_period.end,
                data_updated_at=response.meta.data_updated_at,
                operated_by=operator_id,
            )
            event_ids[trend_type] = event.id
        self.session.commit()
        return self._response_payload(
            response.current_period.start,
            response.current_period.end,
            response.comparison_period.start,
            response.comparison_period.end,
            grouped,
            event_ids,
            response.meta.data_updated_at,
        )

    def list_results(
        self,
        *,
        period_days: int = 3,
        end_date: date | None = None,
        room_ids: tuple[uuid.UUID, ...] = (),
        anchor_ids: tuple[uuid.UUID, ...] = (),
        anchor_names: tuple[str, ...] = (),
        control_names: tuple[str, ...] = (),
        trend_type: str = "all",
        roi_target_status: str | None = None,
        pushed: bool | None = None,
        destination_group: str | None = None,
        minimum_coverage_rate: Decimal | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_period(period_days)
        allowed_room_ids = self._authorized_room_ids(room_ids)
        event_query = select(AnchorTrendEvent).where(AnchorTrendEvent.period_days == period_days)
        if end_date is not None:
            event_query = event_query.where(AnchorTrendEvent.current_period_end == end_date)
        else:
            latest = self.session.scalar(
                select(func.max(AnchorTrendEvent.current_period_end)).where(
                    AnchorTrendEvent.period_days == period_days
                )
            )
            if latest is not None:
                event_query = event_query.where(AnchorTrendEvent.current_period_end == latest)
        if destination_group:
            event_query = event_query.where(AnchorTrendEvent.destination_group == destination_group)
        if pushed is True:
            event_query = event_query.where(AnchorTrendEvent.push_status == "sent")
        elif pushed is False:
            event_query = event_query.where(AnchorTrendEvent.push_status != "sent")
        events = list(
            self.session.scalars(event_query.order_by(AnchorTrendEvent.created_at.desc()))
        )
        latest_by_type: dict[str, AnchorTrendEvent] = {}
        for event in events:
            latest_by_type.setdefault(event.notification_type, event)
        event_ids = [event.id for event in latest_by_type.values()]
        items_query = select(AnchorTrendItem).where(
            AnchorTrendItem.event_id.in_(event_ids or [uuid.UUID(int=0)])
        )
        if allowed_room_ids is not None:
            items_query = items_query.where(
                AnchorTrendItem.room_id.in_(allowed_room_ids or [uuid.UUID(int=0)])
            )
        if anchor_ids:
            items_query = items_query.where(AnchorTrendItem.anchor_id.in_(anchor_ids))
        if anchor_names:
            items_query = items_query.where(AnchorTrendItem.anchor_name.in_(anchor_names))
        if trend_type in {"rise", "fall", "insufficient"}:
            items_query = items_query.where(AnchorTrendItem.trend_type == trend_type)
        if roi_target_status == "reached":
            items_query = items_query.where(AnchorTrendItem.roi_target_reached.is_(True))
        elif roi_target_status == "not_reached":
            items_query = items_query.where(AnchorTrendItem.roi_target_reached.is_(False))
        if minimum_coverage_rate is not None:
            items_query = items_query.where(
                AnchorTrendItem.current_coverage_rate >= minimum_coverage_rate,
                AnchorTrendItem.baseline_coverage_rate >= minimum_coverage_rate,
            )
        items = list(
            self.session.scalars(
                items_query.order_by(AnchorTrendItem.rank, AnchorTrendItem.anchor_name)
            )
        )
        if control_names:
            controls = set(control_names)
            items = [item for item in items if controls.intersection(item.control_names or [])]
        item_payloads = [
            self._stored_item_payload(item, latest_by_type)
            for item in items[: max(1, min(limit, 1000))]
        ]
        rise = [item for item in item_payloads if item["trend_type"] == "rise"]
        fall = [item for item in item_payloads if item["trend_type"] == "fall"]
        insufficient = [item for item in item_payloads if item["trend_type"] == "insufficient"]
        visible_items_by_event: dict[uuid.UUID, list[AnchorTrendItem]] = {}
        for item in items:
            visible_items_by_event.setdefault(item.event_id, []).append(item)
        visible_events = [
            event
            for event in latest_by_type.values()
            if self.access.room_ids is None or event.id in visible_items_by_event
        ]
        representative = next(iter(visible_events), None)
        return {
            "current_period": self._period_payload(
                representative.current_period_start if representative else None,
                representative.current_period_end if representative else end_date,
            ),
            "baseline_period": self._period_payload(
                representative.baseline_period_start if representative else None,
                representative.baseline_period_end if representative else None,
            ),
            "rise": rise,
            "fall": fall,
            "insufficient": insufficient,
            "summary": {
                "rise_count": len(rise),
                "fall_count": len(fall),
                "insufficient_count": len(insufficient),
                "reached_count": sum(item["roi_target_reached"] is True for item in item_payloads),
            },
            "events": [
                self._event_payload(
                    event,
                    visible_items=(
                        visible_items_by_event.get(event.id, [])
                        if self.access.room_ids is not None
                        else None
                    ),
                )
                for event in visible_events
            ],
        }

    def get_event(self, event_id: uuid.UUID) -> dict[str, Any]:
        event = self.session.get(AnchorTrendEvent, event_id)
        if event is None:
            raise LookupError("主播趋势事件不存在")
        items_query = select(AnchorTrendItem).where(AnchorTrendItem.event_id == event.id)
        if self.access.room_ids is not None:
            items_query = items_query.where(
                AnchorTrendItem.room_id.in_(self.access.room_ids or [uuid.UUID(int=0)])
            )
        items = list(
            self.session.scalars(
                items_query.order_by(AnchorTrendItem.rank, AnchorTrendItem.anchor_name)
            )
        )
        if not items and self.access.room_ids is not None:
            raise LookupError("主播趋势事件不存在或无权访问")
        return {
            "event": self._event_payload(
                event,
                visible_items=items if self.access.room_ids is not None else None,
            ),
            "items": [
                self._stored_item_payload(item, {event.notification_type: event}) for item in items
            ],
            "details": [self._live_item_details(event, item) for item in items],
        }

    def find_event(
        self,
        *,
        rule_id: uuid.UUID,
        period: date,
        notification_type: str,
    ) -> AnchorTrendEvent:
        event = self.session.scalar(
            select(AnchorTrendEvent)
            .where(
                AnchorTrendEvent.rule_id == rule_id,
                AnchorTrendEvent.current_period_end == period,
                AnchorTrendEvent.notification_type == notification_type,
                AnchorTrendEvent.manual_resend.is_(False),
            )
            .order_by(AnchorTrendEvent.created_at.desc())
        )
        if event is None:
            raise LookupError("指定规则、周期和通知类型的趋势事件不存在，请先重算")
        return event

    async def send_summary(
        self,
        *,
        rule_id: uuid.UUID,
        period: date,
        notification_type: str,
        force_resend: bool,
        resend_reason: str | None,
        operator_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        event = self.find_event(
            rule_id=rule_id,
            period=period,
            notification_type=notification_type,
        )
        if force_resend:
            return await self.force_resend(
                event.id,
                reason=resend_reason or "",
                operator_id=operator_id,
            )
        return await self.send_event(event.id)

    async def send_event(self, event_id: uuid.UUID) -> dict[str, Any]:
        event = self.session.get(AnchorTrendEvent, event_id)
        if event is None:
            raise LookupError("主播趋势事件不存在")
        if event.notification_type == NOTIFICATION_TYPES["insufficient"]:
            raise ValueError("样本不足事件不得发送到业务群")
        rule = self.session.get(HourlyComparisonRule, event.rule_id)
        retry_limit = rule.push_retry_limit if rule is not None else self.settings.alert_retry_limit
        claimed_id = self.session.scalar(
            update(AnchorTrendEvent)
            .where(
                AnchorTrendEvent.id == event_id,
                AnchorTrendEvent.push_status.in_(["pending", "failed", "skipped"]),
                AnchorTrendEvent.push_attempts < retry_limit,
            )
            .values(
                push_status="sending",
                push_attempts=AnchorTrendEvent.push_attempts + 1,
                push_error=None,
            )
            .returning(AnchorTrendEvent.id)
        )
        if claimed_id is None:
            self.session.rollback()
            raise ValueError("趋势榜已发送、正在发送或已达到重试上限")
        self.session.commit()
        event = self.session.get(AnchorTrendEvent, event_id)
        if event is None:
            raise LookupError("主播趋势事件不存在")
        authoritative_room_ids = frozenset(
            self.session.scalars(
                select(AnchorTrendItem.room_id).where(AnchorTrendItem.event_id == event.id)
            )
        )
        try:
            result = await AlertService(self.session, self.settings, None).send_card(
                event.message_snapshot,
                idempotency_key=event.dedup_key,
                chat_id=event.destination_group,
                room_ids=authoritative_room_ids,
            )
            if result.get("mocked") is True:
                event.push_status = "skipped"
                event.push_error = "未配置可用的飞书机器人，消息未真实发送"
                self.session.commit()
                return {
                    "event_id": str(event.id),
                    "push_status": "skipped",
                    "provider": result,
                }
            event.push_status = "sent"
            event.pushed_at = utc_now()
            event.push_error = None
            self.session.commit()
            return {"event_id": str(event.id), "push_status": "sent", "provider": result}
        except Exception as exc:
            event.push_status = "failed"
            event.push_error = str(exc)
            self.session.commit()
            raise

    async def force_resend(
        self,
        event_id: uuid.UUID,
        *,
        reason: str,
        operator_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        source = self.session.get(AnchorTrendEvent, event_id)
        if source is None:
            raise LookupError("主播趋势事件不存在")
        rule = self.session.get(HourlyComparisonRule, source.rule_id)
        if rule is None or not rule.allow_force_resend:
            raise ValueError("该规则不允许强制重新发送")
        if not reason.strip():
            raise ValueError("强制重新发送必须填写原因")
        source_items = list(
            self.session.scalars(
                select(AnchorTrendItem).where(AnchorTrendItem.event_id == source.id)
            )
        )
        forced_key = self._dedup_key(
            rule.id,
            source.period_days,
            source.current_period_start,
            source.current_period_end,
            source.destination_group,
            source.notification_type,
            suffix=f"force:{uuid.uuid4()}",
        )
        clone = AnchorTrendEvent(
            rule_id=source.rule_id,
            period_days=source.period_days,
            current_period_start=source.current_period_start,
            current_period_end=source.current_period_end,
            baseline_period_start=source.baseline_period_start,
            baseline_period_end=source.baseline_period_end,
            notification_type=source.notification_type,
            destination_group=source.destination_group,
            room_scope=list(source.room_scope or []),
            anchor_count=source.anchor_count,
            message_snapshot=dict(source.message_snapshot or {}),
            dedup_key=forced_key,
            push_status="pending",
            push_attempts=0,
            manual_resend=True,
            source_event_id=source.id,
            resend_reason=reason.strip(),
            operated_by=operator_id,
        )
        self.session.add(clone)
        self.session.flush()
        for item in source_items:
            self.session.add(self._clone_item(item, clone.id))
        self.session.commit()
        return await self.send_event(clone.id)

    async def run_rule(
        self, rule: HourlyComparisonRule, *, end_date: date | None = None
    ) -> dict[str, Any]:
        result = self.recalculate(rule_id=rule.id, period_days=rule.period_days, end_date=end_date)
        sent: list[dict[str, Any]] = []
        for trend_type in ("rise", "fall"):
            event_id = result["event_ids"].get(trend_type)
            if event_id is None:
                continue
            event = self.session.get(AnchorTrendEvent, uuid.UUID(event_id))
            if event is None or event.push_status != "pending":
                continue
            sent.append(await self.send_event(event.id))
        return {"calculation": result, "sent": sent}

    def due_rules(self, now: datetime | None = None) -> list[HourlyComparisonRule]:
        local_now = now.astimezone(self.timezone) if now else datetime.now(self.timezone)
        rules = list(
            self.session.scalars(
                select(HourlyComparisonRule).where(
                    HourlyComparisonRule.rule_type == TREND_RULE_TYPE,
                    HourlyComparisonRule.enabled.is_(True),
                )
            )
        )
        return [rule for rule in rules if self._schedule_due(rule.push_schedule, local_now)]

    @staticmethod
    def _schedule_due(schedule: str, now: datetime) -> bool:
        if schedule.startswith("daily@"):
            hour, minute = (int(value) for value in schedule.removeprefix("daily@").split(":"))
            return now.hour == hour and minute <= now.minute < minute + 15
        if schedule.startswith("weekly:"):
            weekday_part, clock = schedule.removeprefix("weekly:").split("@", 1)
            hour, minute = (int(value) for value in clock.split(":"))
            return (
                now.isoweekday() == int(weekday_part)
                and now.hour == hour
                and minute <= now.minute < minute + 15
            )
        return False

    def _aggregate_series(
        self,
        series: Any,
        rule: HourlyComparisonRule,
        controls: dict[tuple[uuid.UUID, str], tuple[str, ...]],
        person_ids: dict[str, uuid.UUID],
        coverage_threshold: Decimal,
        current_complete: bool,
        baseline_complete: bool,
    ) -> TrendCalculation:
        current_spend = self._sum_points(series.points, "current", "period_spend")
        baseline_spend = self._sum_points(series.points, "comparison", "period_spend")
        current_amount = self._sum_points(series.points, "current", "period_overall_amount")
        baseline_amount = self._sum_points(series.points, "comparison", "period_overall_amount")
        current_orders = self._sum_points(series.points, "current", "period_overall_orders")
        baseline_orders = self._sum_points(series.points, "comparison", "period_overall_orders")
        current_roi = self._ratio(current_amount, current_spend)
        baseline_roi = self._ratio(baseline_amount, baseline_spend)
        current_order_cost = self._ratio(current_spend, current_orders)
        baseline_order_cost = self._ratio(baseline_spend, baseline_orders)
        current_effective_hours = sum(point.current.effective_samples for point in series.points)
        baseline_effective_hours = sum(
            point.comparison.effective_samples for point in series.points if point.comparison
        )
        current_expected = sum(point.current.expected_samples or 0 for point in series.points)
        baseline_expected = sum(
            point.comparison.expected_samples or 0 for point in series.points if point.comparison
        )
        current_coverage = self._ratio(Decimal(current_effective_hours), Decimal(current_expected))
        baseline_coverage = self._ratio(
            Decimal(baseline_effective_hours), Decimal(baseline_expected)
        )
        current_days = max((point.current.effective_days for point in series.points), default=0)
        baseline_days = max(
            (point.comparison.effective_days for point in series.points if point.comparison),
            default=0,
        )
        decision = evaluate_anchor_trend(
            AnchorTrendInput(
                current_roi=current_roi,
                baseline_roi=baseline_roi,
                current_spend=current_spend,
                baseline_spend=baseline_spend,
                current_orders=current_orders,
                baseline_orders=baseline_orders,
                target_roi=series.roi_target,
                current_coverage_rate=current_coverage,
                baseline_coverage_rate=baseline_coverage,
                current_effective_hours=current_effective_hours,
                baseline_effective_hours=baseline_effective_hours,
                minimum_spend=rule.minimum_spend,
                minimum_orders=rule.minimum_orders,
                minimum_coverage_rate=coverage_threshold,
                minimum_effective_hours=rule.minimum_effective_hours,
                roi_rise_threshold=rule.roi_increase_threshold,
                roi_fall_threshold=rule.roi_decrease_threshold,
                spend_rise_threshold=rule.spend_increase_threshold,
                spend_fall_threshold=rule.spend_decrease_threshold,
                current_period_complete=current_complete,
                baseline_period_complete=baseline_complete,
            )
        )
        hourly_details = self._hourly_details(series.points)
        rise_hours = tuple(
            row["hour"]
            for row in sorted(
                (row for row in hourly_details if self._decimal(row.get("roi_delta")) > Decimal(0)),
                key=lambda row: self._decimal(row.get("roi_delta")),
                reverse=True,
            )[:3]
        )
        fall_hours = tuple(
            row["hour"]
            for row in sorted(
                (row for row in hourly_details if self._decimal(row.get("roi_delta")) < Decimal(0)),
                key=lambda row: self._decimal(row.get("roi_delta")),
            )[:3]
        )
        spend_hours = tuple(
            row["hour"]
            for row in sorted(
                hourly_details,
                key=lambda row: abs(self._decimal(row.get("spend_difference"))),
                reverse=True,
            )[:3]
            if self._decimal(row.get("spend_difference")) != Decimal(0)
        )
        room_id = series.room_id
        anchor_name = series.anchor_name
        return TrendCalculation(
            room_id=room_id,
            room_name=series.room_name,
            anchor_id=person_ids.get(anchor_name),
            anchor_name=anchor_name,
            control_names=controls.get((room_id, anchor_name), ()),
            trend_type=decision.trend_type,
            current_amount=current_amount,
            baseline_amount=baseline_amount,
            current_spend=current_spend,
            baseline_spend=baseline_spend,
            spend_growth_rate=decision.spend_growth_rate,
            current_roi=current_roi,
            baseline_roi=baseline_roi,
            roi_growth_rate=decision.roi_growth_rate,
            current_orders=current_orders,
            baseline_orders=baseline_orders,
            current_order_cost=current_order_cost,
            baseline_order_cost=baseline_order_cost,
            roi_target=series.roi_target,
            roi_target_gap=decision.roi_target_gap,
            roi_target_reached=decision.roi_target_reached,
            primary_status=decision.primary_code,
            primary_status_name=decision.primary_name,
            reason_codes=decision.reason_codes,
            reasons=decision.reasons,
            major_rise_hours=rise_hours,
            major_fall_hours=fall_hours,
            major_spend_hours=spend_hours,
            hourly_details=tuple(hourly_details),
            current_effective_days=current_days,
            baseline_effective_days=baseline_days,
            current_effective_hours=current_effective_hours,
            baseline_effective_hours=baseline_effective_hours,
            current_coverage_rate=current_coverage,
            baseline_coverage_rate=baseline_coverage,
            suggestion=self._suggestion(decision.primary_code),
        )

    def _persist_summary_event(
        self,
        rule: HourlyComparisonRule,
        trend_type: str,
        items: list[TrendCalculation],
        *,
        current_start: date,
        current_end: date,
        baseline_start: date,
        baseline_end: date,
        data_updated_at: datetime | None,
        operated_by: uuid.UUID | None,
    ) -> AnchorTrendEvent:
        notification_type = NOTIFICATION_TYPES[trend_type]
        destination = rule.push_chat_id or self.settings.feishu_bot_chat_id or None
        dedup_key = self._dedup_key(
            rule.id,
            rule.period_days,
            current_start,
            current_end,
            destination,
            notification_type,
        )
        existing = self.session.scalar(
            select(AnchorTrendEvent).where(AnchorTrendEvent.dedup_key == dedup_key)
        )
        if existing is not None:
            return existing
        limit = rule.rise_limit if trend_type == "rise" else rule.fall_limit
        card = (
            self.build_summary_card(
                trend_type,
                items[: min(max(limit, 1), DISPLAY_LIMIT_MAX)],
                period_days=rule.period_days,
                current_start=current_start,
                current_end=current_end,
                baseline_start=baseline_start,
                baseline_end=baseline_end,
                data_updated_at=data_updated_at,
                total_count=len(items),
            )
            if trend_type in {"rise", "fall"}
            else {}
        )
        send_enabled = rule.push_enabled and (
            (trend_type == "rise" and rule.send_rise) or (trend_type == "fall" and rule.send_fall)
        )
        event = AnchorTrendEvent(
            rule_id=rule.id,
            period_days=rule.period_days,
            current_period_start=current_start,
            current_period_end=current_end,
            baseline_period_start=baseline_start,
            baseline_period_end=baseline_end,
            notification_type=notification_type,
            destination_group=destination,
            room_scope=sorted({str(item.room_id) for item in items}),
            anchor_count=len(items),
            message_snapshot=card,
            dedup_key=dedup_key,
            push_status="pending" if send_enabled and items else "skipped",
            push_error=None if send_enabled and items else "规则关闭该榜单业务群推送或样本不足",
            operated_by=operated_by,
        )
        try:
            with self.session.begin_nested():
                self.session.add(event)
                self.session.flush()
                for rank, calculation in enumerate(items, start=1):
                    self.session.add(self._item_from_calculation(event.id, rank, calculation))
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(AnchorTrendEvent).where(AnchorTrendEvent.dedup_key == dedup_key)
            )
            if existing is None:
                raise
            return existing
        return event

    @staticmethod
    def build_summary_card(
        trend_type: str,
        items: list[TrendCalculation],
        *,
        period_days: int,
        current_start: date,
        current_end: date,
        baseline_start: date,
        baseline_end: date,
        data_updated_at: datetime | None,
        total_count: int,
    ) -> dict[str, Any]:
        rise = trend_type == "rise"
        title = (
            f"【主播近期数据上涨榜｜最近{period_days}天】"
            if rise
            else f"【主播近期数据下跌预警｜最近{period_days}天】"
        )
        lines = [
            f"**当前周期：** {current_start:%m月%d日}—{current_end:%m月%d日}",
            f"**对比周期：** {baseline_start:%m月%d日}—{baseline_end:%m月%d日}",
            "",
        ]
        for rank, item in enumerate(items, start=1):
            target_status = (
                "已达标"
                if item.roi_target_reached is True
                else (
                    "仍未达标"
                    if rise and item.roi_target_reached is False
                    else ("未达标" if item.roi_target_reached is False else "目标未配置")
                )
            )
            hours = item.major_rise_hours if rise else item.major_fall_hours
            label = "主要上涨时段" if rise else "主要下跌时段"
            roi_line = (
                f"当前ROI：{AnchorTrendService._number(item.current_roi)} ｜ "
                f"基准ROI：{AnchorTrendService._number(item.baseline_roi)} ｜ "
                f"ROI变化：{AnchorTrendService._percent(item.roi_growth_rate)}"
            )
            spend_line = (
                f"当前消耗：¥{AnchorTrendService._money(item.current_spend)} ｜ "
                f"基准消耗：¥{AnchorTrendService._money(item.baseline_spend)} ｜ "
                f"消耗变化：{AnchorTrendService._percent(item.spend_growth_rate)}"
            )
            target_line = (
                f"ROI目标：{AnchorTrendService._number(item.roi_target)} ｜ "
                f"目标状态：**{target_status}** ｜ "
                f"目标差值：{AnchorTrendService._signed_number(item.roi_target_gap)}"
            )
            contribution_hours = "、".join(hours) if hours else "暂无有效可比小时"
            status_line = (
                f"综合状态：**{item.primary_status_name}** ｜ {label}：{contribution_hours}"
            )
            block = [
                f"**{rank}. {item.anchor_name}｜{item.room_name}**",
                roi_line,
                spend_line,
                target_line,
                status_line,
            ]
            if not rise:
                block.append(f"建议：{item.suggestion}")
            lines.extend(["\n".join(block), "---"])
        reached = sum(item.roi_target_reached is True for item in items)
        not_reached = sum(item.roi_target_reached is False for item in items)
        if rise:
            lines.append(
                f"本次上涨主播：{total_count} ｜ 展示：{len(items)} ｜ "
                f"已达标：{reached} ｜ 未达标但上涨：{not_reached}"
            )
        else:
            inefficient = sum(item.primary_status == "efficiency_deterioration" for item in items)
            lines.append(
                f"本次下跌主播：{total_count} ｜ 展示：{len(items)} ｜ "
                f"未达标：{not_reached} ｜ 放量降效：{inefficient}"
            )
        lines.append(
            f"数据更新时间：{data_updated_at.isoformat() if data_updated_at else '暂无来源时间'}"
        )
        return FeishuBotClient.build_card(
            title,
            lines,
            {
                "查看完整榜单": "/alerts",
                "查看主播分析": "/anchors",
                "查看经营总览": "/overview",
            },
            template="green" if rise else "red",
        )

    def _live_item_details(self, event: AnchorTrendEvent, item: AnchorTrendItem) -> dict[str, Any]:
        facts = list(
            self.session.scalars(
                select(HourlyFact).where(
                    HourlyFact.room_id == item.room_id,
                    HourlyFact.actual_anchor_canonical == item.anchor_name,
                    HourlyFact.business_date.between(
                        event.baseline_period_start, event.current_period_end
                    ),
                    HourlyFact.data_status == "complete",
                )
            )
        )
        metrics_by_fact: dict[uuid.UUID, dict[str, Decimal | None]] = {}
        fact_ids = [fact.id for fact in facts]
        if fact_ids:
            rows = self.session.execute(
                select(
                    HourlyMetric.hourly_fact_id,
                    HourlyMetric.metric_key,
                    HourlyMetric.numeric_value,
                ).where(
                    HourlyMetric.hourly_fact_id.in_(fact_ids),
                    HourlyMetric.metric_key.in_(
                        ["period_spend", "period_overall_amount", "period_overall_orders"]
                    ),
                    HourlyMetric.quality_status == "valid",
                )
            )
            for fact_id, metric_key, value in rows:
                metrics_by_fact.setdefault(fact_id, {})[metric_key] = value
        daily: dict[tuple[str, date], dict[str, Decimal]] = {}
        raw: list[dict[str, Any]] = []
        for fact in sorted(facts, key=lambda value: (value.business_date, value.hour_order)):
            period = (
                "current"
                if event.current_period_start <= fact.business_date <= event.current_period_end
                else "baseline"
            )
            values = metrics_by_fact.get(fact.id, {})
            key = (period, fact.business_date)
            aggregate = daily.setdefault(
                key,
                {"spend": Decimal(0), "amount": Decimal(0), "orders": Decimal(0)},
            )
            aggregate["spend"] += values.get("period_spend") or Decimal(0)
            aggregate["amount"] += values.get("period_overall_amount") or Decimal(0)
            aggregate["orders"] += values.get("period_overall_orders") or Decimal(0)
            raw.append(
                {
                    "fact_id": str(fact.id),
                    "period": period,
                    "date": fact.business_date.isoformat(),
                    "natural_hour": fact.hour_slot,
                    "anchor": fact.actual_anchor_canonical,
                    "control": fact.actual_control_canonical,
                    "data_status": fact.data_status,
                    "metrics": {
                        name: str(value) if value is not None else None
                        for name, value in values.items()
                    },
                }
            )
        daily_rows = []
        for (period, day), day_values in sorted(daily.items(), key=lambda value: value[0]):
            daily_rows.append(
                {
                    "period": period,
                    "date": day.isoformat(),
                    "spend": str(day_values["spend"]),
                    "amount": str(day_values["amount"]),
                    "roi": self._json_decimal(
                        self._ratio(day_values["amount"], day_values["spend"])
                    ),
                    "orders": str(day_values["orders"]),
                }
            )
        return {
            "item_id": str(item.id),
            "daily": daily_rows,
            "hours": item.hourly_details or [],
            "roi_numerator": {
                "current": self._json_decimal(item.current_amount),
                "baseline": self._json_decimal(item.baseline_amount),
            },
            "roi_denominator": {
                "current": self._json_decimal(item.current_spend),
                "baseline": self._json_decimal(item.baseline_spend),
            },
            "raw_records": raw,
        }

    def _effective_room_ids(
        self,
        rule: HourlyComparisonRule,
        requested: tuple[uuid.UUID, ...],
    ) -> tuple[tuple[uuid.UUID, ...], bool]:
        rule_rooms = {uuid.UUID(value) for value in (rule.applicable_rooms or []) if value}
        requested_rooms = set(requested)
        constrained = bool(rule_rooms or requested_rooms or self.access.room_ids is not None)
        effective = requested_rooms or rule_rooms
        if requested_rooms and rule_rooms:
            effective &= rule_rooms
        if self.access.room_ids is not None:
            effective = (
                (effective & set(self.access.room_ids)) if effective else set(self.access.room_ids)
            )
        return tuple(sorted(effective, key=str)), constrained and not effective

    def _authorized_room_ids(
        self, requested: tuple[uuid.UUID, ...]
    ) -> tuple[uuid.UUID, ...] | None:
        if self.access.room_ids is None:
            return requested or None
        allowed = set(self.access.room_ids)
        return (
            tuple(room_id for room_id in requested if room_id in allowed)
            if requested
            else tuple(allowed)
        )

    def _control_names(
        self,
        start: date,
        end: date,
        room_ids: tuple[uuid.UUID, ...],
    ) -> dict[tuple[uuid.UUID, str], tuple[str, ...]]:
        statement = select(
            HourlyFact.room_id,
            HourlyFact.actual_anchor_canonical,
            HourlyFact.actual_control_canonical,
        ).where(
            HourlyFact.business_date.between(start, end),
            HourlyFact.data_status == "complete",
            HourlyFact.actual_anchor_canonical.is_not(None),
            HourlyFact.actual_control_canonical.is_not(None),
        )
        if room_ids:
            statement = statement.where(HourlyFact.room_id.in_(room_ids))
        if self.access.room_ids is not None:
            statement = statement.where(
                HourlyFact.room_id.in_(self.access.room_ids or [uuid.UUID(int=0)])
            )
        result: dict[tuple[uuid.UUID, str], set[str]] = {}
        for room_id, anchor_name, control_name in self.session.execute(statement):
            result.setdefault((room_id, anchor_name), set()).add(control_name)
        return {key: tuple(sorted(values)) for key, values in result.items()}

    def _anchor_person_ids(self) -> dict[str, uuid.UUID]:
        result: dict[str, uuid.UUID] = {}
        for person in self.session.scalars(select(Person).where(Person.active.is_(True))):
            result[person.display_name] = person.id
            result.setdefault(person.base_name, person.id)
        for alias, person_id in self.session.execute(
            select(PersonAlias.alias, PersonAlias.person_id)
        ):
            result.setdefault(alias, person_id)
        return result

    @staticmethod
    def _sum_points(points: list[Any], period: str, metric_key: str) -> Decimal | None:
        values: list[Decimal] = []
        for point in points:
            payload = point.current if period == "current" else point.comparison
            if payload is None:
                continue
            value = payload.metrics.get(metric_key)
            if value is not None:
                values.append(value)
        return sum(values, Decimal(0)) if values else None

    @staticmethod
    def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def _hourly_details(points: list[Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for point in points:
            comparison = point.comparison
            current_roi = point.current.roi
            baseline_roi = comparison.roi if comparison else None
            current_spend = point.current.spend
            baseline_spend = comparison.spend if comparison else None
            result.append(
                {
                    "hour": point.hour,
                    "current": {
                        "spend": AnchorTrendService._json_decimal(current_spend),
                        "amount": AnchorTrendService._json_decimal(
                            point.current.metrics.get("period_overall_amount")
                        ),
                        "roi": AnchorTrendService._json_decimal(current_roi),
                        "orders": AnchorTrendService._json_decimal(
                            point.current.metrics.get("period_overall_orders")
                        ),
                    },
                    "baseline": {
                        "spend": AnchorTrendService._json_decimal(baseline_spend),
                        "amount": AnchorTrendService._json_decimal(
                            comparison.metrics.get("period_overall_amount") if comparison else None
                        ),
                        "roi": AnchorTrendService._json_decimal(baseline_roi),
                        "orders": AnchorTrendService._json_decimal(
                            comparison.metrics.get("period_overall_orders") if comparison else None
                        ),
                    },
                    "roi_delta": AnchorTrendService._json_decimal(
                        current_roi - baseline_roi
                        if current_roi is not None and baseline_roi is not None
                        else None
                    ),
                    "spend_difference": AnchorTrendService._json_decimal(
                        current_spend - baseline_spend
                        if current_spend is not None and baseline_spend is not None
                        else None
                    ),
                }
            )
        return result

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value)) if value not in {None, ""} else Decimal(0)

    @staticmethod
    def _dedup_key(
        rule_id: uuid.UUID,
        period_days: int,
        current_start: date,
        current_end: date,
        destination: str | None,
        notification_type: str,
        *,
        suffix: str = "",
    ) -> str:
        raw = "|".join(
            [
                str(rule_id),
                str(period_days),
                current_start.isoformat(),
                current_end.isoformat(),
                destination or "__default_group__",
                notification_type,
                suffix,
            ]
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _item_from_calculation(
        event_id: uuid.UUID,
        rank: int,
        item: TrendCalculation,
    ) -> AnchorTrendItem:
        return AnchorTrendItem(
            event_id=event_id,
            rank=rank,
            room_id=item.room_id,
            room_name=item.room_name,
            anchor_id=item.anchor_id,
            anchor_name=item.anchor_name,
            control_names=list(item.control_names),
            trend_type=item.trend_type,
            current_amount=item.current_amount,
            baseline_amount=item.baseline_amount,
            current_spend=item.current_spend,
            baseline_spend=item.baseline_spend,
            spend_growth_rate=item.spend_growth_rate,
            current_roi=item.current_roi,
            baseline_roi=item.baseline_roi,
            roi_growth_rate=item.roi_growth_rate,
            current_orders=item.current_orders,
            baseline_orders=item.baseline_orders,
            current_order_cost=item.current_order_cost,
            baseline_order_cost=item.baseline_order_cost,
            roi_target=item.roi_target,
            roi_target_gap=item.roi_target_gap,
            roi_target_reached=item.roi_target_reached,
            primary_status=item.primary_status,
            primary_status_name=item.primary_status_name,
            reason_codes=list(item.reason_codes),
            reasons=list(item.reasons),
            major_rise_hours=list(item.major_rise_hours),
            major_fall_hours=list(item.major_fall_hours),
            major_spend_hours=list(item.major_spend_hours),
            hourly_details=list(item.hourly_details),
            current_effective_days=item.current_effective_days,
            baseline_effective_days=item.baseline_effective_days,
            current_effective_hours=item.current_effective_hours,
            baseline_effective_hours=item.baseline_effective_hours,
            current_coverage_rate=item.current_coverage_rate,
            baseline_coverage_rate=item.baseline_coverage_rate,
            comparison_basis=COMPARISON_BASIS,
            suggestion=item.suggestion,
        )

    @staticmethod
    def _clone_item(item: AnchorTrendItem, event_id: uuid.UUID) -> AnchorTrendItem:
        return AnchorTrendItem(
            event_id=event_id,
            rank=item.rank,
            room_id=item.room_id,
            room_name=item.room_name,
            anchor_id=item.anchor_id,
            anchor_name=item.anchor_name,
            control_names=list(item.control_names or []),
            trend_type=item.trend_type,
            current_amount=item.current_amount,
            baseline_amount=item.baseline_amount,
            current_spend=item.current_spend,
            baseline_spend=item.baseline_spend,
            spend_growth_rate=item.spend_growth_rate,
            current_roi=item.current_roi,
            baseline_roi=item.baseline_roi,
            roi_growth_rate=item.roi_growth_rate,
            current_orders=item.current_orders,
            baseline_orders=item.baseline_orders,
            current_order_cost=item.current_order_cost,
            baseline_order_cost=item.baseline_order_cost,
            roi_target=item.roi_target,
            roi_target_gap=item.roi_target_gap,
            roi_target_reached=item.roi_target_reached,
            primary_status=item.primary_status,
            primary_status_name=item.primary_status_name,
            reason_codes=list(item.reason_codes or []),
            reasons=list(item.reasons or []),
            major_rise_hours=list(item.major_rise_hours or []),
            major_fall_hours=list(item.major_fall_hours or []),
            major_spend_hours=list(item.major_spend_hours or []),
            hourly_details=list(item.hourly_details or []),
            current_effective_days=item.current_effective_days,
            baseline_effective_days=item.baseline_effective_days,
            current_effective_hours=item.current_effective_hours,
            baseline_effective_hours=item.baseline_effective_hours,
            current_coverage_rate=item.current_coverage_rate,
            baseline_coverage_rate=item.baseline_coverage_rate,
            comparison_basis=item.comparison_basis,
            suggestion=item.suggestion,
        )

    @staticmethod
    def _suggestion(primary_code: str) -> str:
        if primary_code == "efficiency_deterioration":
            return "检查主播话术、投流计划、商品点击转化和场控配合。"
        if primary_code in {"roi_target_broken", "below_target_declining"}:
            return "优先复盘目标差距、低效时段和商品转化链路。"
        if primary_code in {"roi_fall", "spend_roi_double_fall"}:
            return "复盘主要下跌时段，并核查投流、话术、货盘和场控协同。"
        return "结合24小时贡献明细复盘异常时段。"

    def _rule(
        self,
        *,
        rule_id: uuid.UUID | None,
        period_days: int,
    ) -> HourlyComparisonRule:
        if rule_id is not None:
            rule = self.session.get(HourlyComparisonRule, rule_id)
            if rule is None or rule.rule_type != TREND_RULE_TYPE:
                raise LookupError("主播趋势规则不存在")
            return rule
        self._validate_period(period_days)
        rule = self.session.scalar(
            select(HourlyComparisonRule)
            .where(
                HourlyComparisonRule.rule_type == TREND_RULE_TYPE,
                HourlyComparisonRule.period_days == period_days,
            )
            .order_by(HourlyComparisonRule.enabled.desc(), HourlyComparisonRule.created_at)
        )
        if rule is None:
            raise LookupError(f"尚未配置{period_days}天主播趋势规则")
        return rule

    @staticmethod
    def _validate_period(period_days: int) -> None:
        if period_days not in SUPPORTED_PERIOD_DAYS:
            raise ValueError("统计周期仅支持1、3、5、7、15、30天")

    @staticmethod
    def _response_payload(
        current_start: date,
        current_end: date,
        baseline_start: date,
        baseline_end: date,
        grouped: dict[str, list[TrendCalculation]],
        event_ids: dict[str, uuid.UUID],
        data_updated_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "current_period": {"start": current_start.isoformat(), "end": current_end.isoformat()},
            "baseline_period": {
                "start": baseline_start.isoformat(),
                "end": baseline_end.isoformat(),
            },
            "rise": [
                AnchorTrendService._calculation_payload(item, rank)
                for rank, item in enumerate(grouped["rise"], 1)
            ],
            "fall": [
                AnchorTrendService._calculation_payload(item, rank)
                for rank, item in enumerate(grouped["fall"], 1)
            ],
            "insufficient": [
                AnchorTrendService._calculation_payload(item, rank)
                for rank, item in enumerate(grouped["insufficient"], 1)
            ],
            "summary": {
                "rise_count": len(grouped["rise"]),
                "fall_count": len(grouped["fall"]),
                "insufficient_count": len(grouped["insufficient"]),
                "reached_count": sum(
                    item.roi_target_reached is True
                    for values in grouped.values()
                    for item in values
                ),
            },
            "event_ids": {key: str(value) for key, value in event_ids.items()},
            "data_updated_at": data_updated_at.isoformat() if data_updated_at else None,
        }

    @staticmethod
    def _calculation_payload(item: TrendCalculation, rank: int) -> dict[str, Any]:
        return {
            "rank": rank,
            "room_id": str(item.room_id),
            "room_name": item.room_name,
            "anchor_id": str(item.anchor_id) if item.anchor_id else None,
            "anchor_name": item.anchor_name,
            "control_names": list(item.control_names),
            "trend_type": item.trend_type,
            "current_amount": AnchorTrendService._json_decimal(item.current_amount),
            "baseline_amount": AnchorTrendService._json_decimal(item.baseline_amount),
            "current_spend": AnchorTrendService._json_decimal(item.current_spend),
            "baseline_spend": AnchorTrendService._json_decimal(item.baseline_spend),
            "spend_growth_rate": AnchorTrendService._json_decimal(item.spend_growth_rate),
            "current_roi": AnchorTrendService._json_decimal(item.current_roi),
            "baseline_roi": AnchorTrendService._json_decimal(item.baseline_roi),
            "roi_growth_rate": AnchorTrendService._json_decimal(item.roi_growth_rate),
            "current_orders": AnchorTrendService._json_decimal(item.current_orders),
            "baseline_orders": AnchorTrendService._json_decimal(item.baseline_orders),
            "current_order_cost": AnchorTrendService._json_decimal(item.current_order_cost),
            "baseline_order_cost": AnchorTrendService._json_decimal(item.baseline_order_cost),
            "roi_target": AnchorTrendService._json_decimal(item.roi_target),
            "roi_target_gap": AnchorTrendService._json_decimal(item.roi_target_gap),
            "roi_target_reached": item.roi_target_reached,
            "primary_status": item.primary_status,
            "primary_status_name": item.primary_status_name,
            "reason_codes": list(item.reason_codes),
            "reasons": list(item.reasons),
            "major_rise_hours": list(item.major_rise_hours),
            "major_fall_hours": list(item.major_fall_hours),
            "major_spend_hours": list(item.major_spend_hours),
            "hourly_details": list(item.hourly_details),
            "current_effective_days": item.current_effective_days,
            "baseline_effective_days": item.baseline_effective_days,
            "current_effective_hours": item.current_effective_hours,
            "baseline_effective_hours": item.baseline_effective_hours,
            "current_coverage_rate": AnchorTrendService._json_decimal(item.current_coverage_rate),
            "baseline_coverage_rate": AnchorTrendService._json_decimal(item.baseline_coverage_rate),
            "comparison_basis": COMPARISON_BASIS,
            "suggestion": item.suggestion,
        }

    @staticmethod
    def _stored_item_payload(
        item: AnchorTrendItem,
        events: dict[str, AnchorTrendEvent],
    ) -> dict[str, Any]:
        event = next((value for value in events.values() if value.id == item.event_id), None)
        return {
            "item_id": str(item.id),
            "event_id": str(item.event_id),
            "rank": item.rank,
            "room_id": str(item.room_id),
            "room_name": item.room_name,
            "anchor_id": str(item.anchor_id) if item.anchor_id else None,
            "anchor_name": item.anchor_name,
            "control_names": item.control_names or [],
            "trend_type": item.trend_type,
            "current_amount": AnchorTrendService._json_decimal(item.current_amount),
            "baseline_amount": AnchorTrendService._json_decimal(item.baseline_amount),
            "current_spend": AnchorTrendService._json_decimal(item.current_spend),
            "baseline_spend": AnchorTrendService._json_decimal(item.baseline_spend),
            "spend_growth_rate": AnchorTrendService._json_decimal(item.spend_growth_rate),
            "current_roi": AnchorTrendService._json_decimal(item.current_roi),
            "baseline_roi": AnchorTrendService._json_decimal(item.baseline_roi),
            "roi_growth_rate": AnchorTrendService._json_decimal(item.roi_growth_rate),
            "current_orders": AnchorTrendService._json_decimal(item.current_orders),
            "baseline_orders": AnchorTrendService._json_decimal(item.baseline_orders),
            "current_order_cost": AnchorTrendService._json_decimal(item.current_order_cost),
            "baseline_order_cost": AnchorTrendService._json_decimal(item.baseline_order_cost),
            "roi_target": AnchorTrendService._json_decimal(item.roi_target),
            "roi_target_gap": AnchorTrendService._json_decimal(item.roi_target_gap),
            "roi_target_reached": item.roi_target_reached,
            "primary_status": item.primary_status,
            "primary_status_name": item.primary_status_name,
            "reason_codes": item.reason_codes or [],
            "reasons": item.reasons or [],
            "major_rise_hours": item.major_rise_hours or [],
            "major_fall_hours": item.major_fall_hours or [],
            "major_spend_hours": item.major_spend_hours or [],
            "hourly_details": item.hourly_details or [],
            "current_effective_days": item.current_effective_days,
            "baseline_effective_days": item.baseline_effective_days,
            "current_effective_hours": item.current_effective_hours,
            "baseline_effective_hours": item.baseline_effective_hours,
            "current_coverage_rate": AnchorTrendService._json_decimal(item.current_coverage_rate),
            "baseline_coverage_rate": AnchorTrendService._json_decimal(item.baseline_coverage_rate),
            "comparison_basis": item.comparison_basis,
            "suggestion": item.suggestion,
            "push_status": event.push_status if event else "unknown",
            "destination_group": event.destination_group if event else None,
        }

    @staticmethod
    def _event_payload(
        event: AnchorTrendEvent,
        *,
        visible_items: list[AnchorTrendItem] | None = None,
    ) -> dict[str, Any]:
        room_scope = (
            sorted({str(item.room_id) for item in visible_items})
            if visible_items is not None
            else event.room_scope or []
        )
        anchor_count = len(visible_items) if visible_items is not None else event.anchor_count
        return {
            "id": str(event.id),
            "rule_id": str(event.rule_id),
            "period_days": event.period_days,
            "current_period_start": event.current_period_start.isoformat(),
            "current_period_end": event.current_period_end.isoformat(),
            "baseline_period_start": event.baseline_period_start.isoformat(),
            "baseline_period_end": event.baseline_period_end.isoformat(),
            "notification_type": event.notification_type,
            "destination_group": event.destination_group,
            "room_scope": room_scope,
            "anchor_count": anchor_count,
            "dedup_key": event.dedup_key,
            "push_status": event.push_status,
            "push_attempts": event.push_attempts,
            "pushed_at": event.pushed_at.isoformat() if event.pushed_at else None,
            "push_error": event.push_error,
            "manual_resend": event.manual_resend,
            "source_event_id": str(event.source_event_id) if event.source_event_id else None,
            "resend_reason": event.resend_reason,
            "operated_by": str(event.operated_by) if event.operated_by else None,
            "created_at": event.created_at.isoformat(),
        }

    @staticmethod
    def _period_payload(start: date | None, end: date | None) -> dict[str, str] | None:
        if start is None or end is None:
            return None
        return {"start": start.isoformat(), "end": end.isoformat()}

    @staticmethod
    def _json_decimal(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _number(value: Decimal | None) -> str:
        return f"{value:.2f}" if value is not None else "无有效值"

    @staticmethod
    def _signed_number(value: Decimal | None) -> str:
        return f"{value:+.2f}" if value is not None else "未配置"

    @staticmethod
    def _money(value: Decimal | None) -> str:
        return f"{value:,.2f}" if value is not None else "无有效值"

    @staticmethod
    def _percent(value: Decimal | None) -> str:
        return f"{value * Decimal(100):+.2f}%" if value is not None else "无有效可比基准"
