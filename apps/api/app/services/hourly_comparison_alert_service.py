from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AccessScope
from app.core.config import Settings
from app.db.base import utc_now
from app.domain.cleaning import normalize_person_name
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    AlertEvent,
    AlertRule,
    HourlyComparisonRule,
    HourlyFact,
    Person,
    Room,
)
from app.services.alert_service import AlertService
from app.services.hourly_comparison_service import (
    HourlyComparisonFilters,
    HourlyComparisonService,
)


@dataclass(frozen=True)
class DueHour:
    business_date: date
    hour_order: int
    hour_slot: str


class HourlyComparisonAlertService:
    """Create one merged event per room/anchor/period/hour and status transition."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        catalog: MetricCatalog,
        allowed_room_ids: frozenset[uuid.UUID] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.catalog = catalog
        self.allowed_room_ids = allowed_room_ids

    @staticmethod
    def latest_due_hour(now: datetime, *, delay_minutes: int) -> DueHour:
        if now.tzinfo is None:
            raise ValueError("小时预警评估时间必须包含时区")
        boundary = (now - timedelta(minutes=delay_minutes)).replace(
            minute=0, second=0, microsecond=0
        )
        if boundary.hour == 0:
            business_date = boundary.date() - timedelta(days=1)
            hour_order = 23
        else:
            business_date = boundary.date()
            hour_order = boundary.hour - 1
        return DueHour(
            business_date=business_date,
            hour_order=hour_order,
            hour_slot=f"{hour_order:02d}-{hour_order + 1:02d}",
        )

    @staticmethod
    def latest_due_business_date(
        now: datetime,
        *,
        submission_hour: int,
        delay_minutes: int,
    ) -> date:
        """Return the newest T+1 business date whose submission window has closed."""
        if now.tzinfo is None:
            raise ValueError("小时预警评估时间必须包含时区")
        deadline = datetime.combine(
            now.date(),
            time(hour=submission_hour),
            tzinfo=now.tzinfo,
        ) + timedelta(minutes=delay_minutes)
        return now.date() - timedelta(days=1 if now >= deadline else 2)

    def evaluate_due_event_ids(self, now: datetime | None = None) -> list[uuid.UUID]:
        local_now = now or datetime.now(ZoneInfo(self.settings.timezone))
        if local_now.tzinfo is None:
            local_now = local_now.replace(tzinfo=ZoneInfo(self.settings.timezone))
        else:
            local_now = local_now.astimezone(ZoneInfo(self.settings.timezone))
        rules = list(
            self.session.scalars(
                select(HourlyComparisonRule)
                .where(HourlyComparisonRule.enabled.is_(True))
                .order_by(HourlyComparisonRule.period_days)
            )
        )
        rooms = list(
            self.session.scalars(
                select(Room)
                .where(Room.active.is_(True), Room.confirmed.is_(True))
                .order_by(Room.name)
            )
        )
        if self.allowed_room_ids is not None:
            rooms = [room for room in rooms if room.id in self.allowed_room_ids]
        event_rule = self._event_rule() if rules and rooms else None
        created: list[AlertEvent] = []
        access = AccessScope(user_id=None, role="admin", room_ids=None, can_export=True)
        for rule in rules:
            scoped_rooms = self._applicable_rooms(rooms, rule.applicable_rooms)
            if not scoped_rooms:
                continue
            due_date = self.latest_due_business_date(
                local_now,
                submission_hour=self.settings.data_submission_deadline_hour,
                delay_minutes=rule.evaluation_delay_minutes,
            )
            filters = HourlyComparisonFilters(
                end_date=due_date,
                period_days=rule.period_days,
                compare_enabled=True,
                aggregation_mode="sum",
                chart_type="line",
                metric_ids=(
                    "period_overall_roi",
                    "period_spend",
                    "period_overall_amount",
                    "period_overall_orders",
                ),
                room_ids=tuple(room.id for room in scoped_rooms),
                natural_hours=(),
                series_dimension="room_anchor",
                include_today=False,
                include_in_progress=False,
            )
            comparison_service = HourlyComparisonService(
                self.session,
                self.catalog,
                access,
                rule_override=rule,
            )
            comparison_service.now = local_now
            response = comparison_service.compare(filters)
            for series in response.series:
                if series.room_id is None or not series.anchor_name:
                    continue
                if not self._anchor_is_applicable(series.anchor_name, rule.applicable_anchors):
                    continue
                for point in series.points:
                    if not self._has_evidence(point):
                        continue
                    event = self._create_event(event_rule, rule, response, series, point)
                    if event is not None:
                        created.append(event)
        self.session.flush()
        event_ids = [event.id for event in created]
        self.session.commit()
        return event_ids

    async def evaluate_due_and_push(self, now: datetime | None = None) -> dict[str, int]:
        event_ids = self.evaluate_due_event_ids(now)
        pushed = await AlertService(self.session, self.settings).push_events(event_ids)
        return {"created": len(event_ids), **pushed}

    def _event_rule(self) -> AlertRule:
        existing = self.session.scalar(
            select(AlertRule).where(AlertRule.rule_type == "hourly_comparison")
        )
        if existing is not None:
            return existing
        rule = AlertRule(
            name="ROI与消耗小时周期综合状态",
            rule_type="hourly_comparison",
            metric_key="period_overall_roi",
            comparison_type="previous_period",
            operator=">=",
            threshold=Decimal(0),
            min_spend=None,
            min_orders=None,
            min_amount=None,
            room_scope=[],
            anchor_scope=[],
            control_scope=[],
            severity="warning",
            cooldown_minutes=0,
            enabled=False,
            push_enabled=False,
            suggestion_template="请结合主播、场控、商品和投流组合复盘该时段。",
            created_by=None,
        )
        self.session.add(rule)
        self.session.flush()
        return rule

    @staticmethod
    def _applicable_rooms(rooms: list[Room], applicable: list[str]) -> list[Room]:
        if not applicable:
            return rooms
        allowed = set(applicable)
        return [room for room in rooms if str(room.id) in allowed or room.name in allowed]

    @staticmethod
    def _anchor_is_applicable(anchor_name: str, applicable: list[str]) -> bool:
        if not applicable:
            return True
        normalized = normalize_person_name(anchor_name)
        candidates = {anchor_name}
        if normalized is not None:
            candidates.update({normalized.canonical, normalized.base_name})
        return bool(candidates.intersection(applicable))

    @staticmethod
    def _has_evidence(point: object) -> bool:
        from app.api.schemas import HourlySeriesPointPayload

        if not isinstance(point, HourlySeriesPointPayload):
            return False
        comparison_samples = point.comparison.effective_samples if point.comparison else 0
        return bool(
            point.current.effective_samples or point.current.expected_samples or comparison_samples
        )

    def _create_event(
        self,
        event_rule: AlertRule | None,
        rule: HourlyComparisonRule,
        response: object,
        series: object,
        point: object,
    ) -> AlertEvent | None:
        if event_rule is None:
            return None
        from app.api.schemas import (
            HourlyComparisonResponse,
            HourlyComparisonSeriesPayload,
            HourlySeriesPointPayload,
        )

        if not isinstance(response, HourlyComparisonResponse):
            raise TypeError("小时预警响应类型错误")
        if not isinstance(series, HourlyComparisonSeriesPayload):
            raise TypeError("小时预警系列类型错误")
        if (
            not isinstance(point, HourlySeriesPointPayload)
            or series.room_id is None
            or not series.anchor_name
        ):
            raise TypeError("小时预警点位类型错误")
        comparison_period = response.comparison_period
        if comparison_period is None:
            return None

        control_name = self._current_control_name(
            room_id=series.room_id,
            anchor_name=series.anchor_name,
            start_date=response.current_period.start,
            end_date=response.current_period.end,
            hour_slot=point.hour,
        )
        anchor_id = self._person_id(series.anchor_name)
        control_id = self._person_id(control_name) if control_name else None
        anchor_identity = str(anchor_id) if anchor_id else series.anchor_name
        base_dedup_key = self._hash_payload(
            {
                "room_id": str(series.room_id),
                "anchor_id": anchor_identity,
                "current_period_start": response.current_period.start.isoformat(),
                "current_period_end": response.current_period.end.isoformat(),
                "natural_hour": point.hour,
                "rule_id": str(rule.id),
            }
        )
        previous = self.session.scalar(
            select(AlertEvent)
            .where(AlertEvent.base_dedup_key == base_dedup_key)
            .order_by(AlertEvent.state_version.desc(), AlertEvent.triggered_at.desc())
            .limit(1)
        )
        if previous is not None and previous.status_code == point.status.code:
            return None
        state_version = previous.state_version + 1 if previous is not None else 0
        alert_type = self._alert_type(point.status.code)
        dedup_key = self._hash_payload(
            {
                "base_dedup_key": base_dedup_key,
                "alert_type": alert_type,
                "status_code": point.status.code,
                "state_version": state_version,
            }
        )
        if self.session.scalar(select(AlertEvent.id).where(AlertEvent.dedup_key == dedup_key)):
            return None

        status_reasons = self._detailed_reasons(point, rule)
        color = self._message_color(point.status.level)
        notification_type = {
            "red": "red_alert",
            "green": "green_excellent",
        }.get(color, "gray_info")
        triggered_at = utc_now()
        cooldown_active = False
        if previous is None and rule.cooldown_minutes > 0:
            cooldown_since = triggered_at - timedelta(minutes=rule.cooldown_minutes)
            cooldown_active = bool(
                self.session.scalar(
                    select(AlertEvent.id).where(
                        AlertEvent.comparison_rule_id == rule.id,
                        AlertEvent.room_id == series.room_id,
                        AlertEvent.anchor_name == series.anchor_name,
                        AlertEvent.status_code == point.status.code,
                        AlertEvent.base_dedup_key != base_dedup_key,
                        AlertEvent.triggered_at >= cooldown_since,
                    )
                )
            )
        push_configured = self._push_configured(rule.push_chat_id)
        should_queue = bool(
            point.status.should_push
            and rule.push_enabled
            and color in {"red", "green"}
            and push_configured
            and not cooldown_active
        )
        push_error = None
        if not should_queue:
            if not rule.push_enabled or not point.status.should_push:
                push_error = "规则或当前状态不允许推送"
            elif cooldown_active:
                push_error = "冷却时间内仅记录事件，不重复推送"
            elif not push_configured:
                push_error = "未配置对应飞书群机器人，Mock 模式"

        current_roi = point.current.roi
        baseline_roi = point.comparison.roi if point.comparison else None
        current_spend = point.current.spend
        baseline_spend = point.comparison.spend if point.comparison else None
        context = {
            "room_name": series.room_name,
            "product_category": series.product_category,
            "anchor_name": series.anchor_name,
            "control_name": control_name,
            "current_roi": self._decimal_text(current_roi),
            "baseline_roi": self._decimal_text(baseline_roi),
            "roi_growth_percentage": self._decimal_text(
                point.comparison_result.roi_growth_percentage
            ),
            "current_spend": self._decimal_text(current_spend),
            "baseline_spend": self._decimal_text(baseline_spend),
            "spend_growth_percentage": self._decimal_text(
                point.comparison_result.spend_growth_percentage
            ),
            "roi_target": self._decimal_text(point.roi_target),
            "roi_target_gap": self._decimal_text(point.comparison_result.roi_target_gap),
            "roi_target_attainment": self._decimal_text(
                point.comparison_result.roi_target_attainment
            ),
            "coverage_rate": self._decimal_text(point.current.coverage_rate),
            "effective_samples": point.current.effective_samples,
            "expected_samples": point.current.expected_samples,
            "target_status": (
                "已达标"
                if point.comparison_result.roi_target_reached is True
                else "未达标"
                if point.comparison_result.roi_target_reached is False
                else "未配置ROI目标"
            ),
            "reason_codes": point.status.reason_codes,
            "rule": {
                "id": str(rule.id),
                "name": rule.name,
                "spend_increase_threshold": str(rule.spend_increase_threshold),
                "spend_decrease_threshold": str(rule.spend_decrease_threshold),
                "roi_increase_threshold": str(rule.roi_increase_threshold),
                "roi_decrease_threshold": str(rule.roi_decrease_threshold),
                "minimum_spend": str(rule.minimum_spend),
                "minimum_orders": rule.minimum_orders,
                "minimum_coverage_rate": str(rule.minimum_coverage_rate),
                "cooldown_minutes": rule.cooldown_minutes,
            },
            "current_period": {
                "start": response.current_period.start.isoformat(),
                "end": response.current_period.end.isoformat(),
            },
            "comparison_period": {
                "start": comparison_period.start.isoformat(),
                "end": comparison_period.end.isoformat(),
            },
        }
        title_prefix = (
            "主播优秀数据"
            if color == "green"
            else "主播数据预警"
            if color == "red"
            else "主播数据状态"
        )
        suggestion = (
            "复盘当前主播、场控、商品和投流组合，判断是否可以复制到其他直播间或时段。"
            if color == "green"
            else "请检查主播话术、商品点击转化、投流计划、场控配合和订单成本。"
            if color == "red"
            else "数据达到规则前置门槛后，系统会自动重新判断。"
        )
        event = AlertEvent(
            rule_id=event_rule.id,
            dedup_key=dedup_key,
            triggered_at=triggered_at,
            room_id=series.room_id,
            business_date=response.current_period.end,
            hour_slot=point.hour,
            anchor_name=series.anchor_name,
            control_name=control_name,
            metric_key="period_overall_roi",
            period_days=rule.period_days,
            current_period_start=response.current_period.start,
            current_period_end=response.current_period.end,
            comparison_period_start=comparison_period.start,
            comparison_period_end=comparison_period.end,
            alert_type=alert_type,
            metric_codes=["period_overall_roi", "period_spend"],
            status_code=point.status.code,
            status_reasons=status_reasons,
            comparison_context=context,
            comparison_rule_id=rule.id,
            anchor_id=anchor_id,
            control_id=control_id,
            current_spend=current_spend,
            baseline_spend=baseline_spend,
            spend_growth_rate=point.comparison_result.spend_growth,
            current_roi=current_roi,
            baseline_roi=baseline_roi,
            roi_growth_rate=point.comparison_result.roi_growth,
            roi_target=point.roi_target,
            roi_target_gap=point.comparison_result.roi_target_gap,
            roi_target_reached=point.comparison_result.roi_target_reached,
            notification_type=notification_type,
            message_color=color,
            push_chat_id=rule.push_chat_id,
            base_dedup_key=base_dedup_key,
            state_version=state_version,
            current_value=current_roi,
            baseline_value=baseline_roi,
            delta_value=point.comparison_result.roi_difference,
            ratio_percent=point.comparison_result.roi_percentage,
            growth_percent=point.comparison_result.roi_growth_percentage,
            severity=point.status.level,
            title=f"{title_prefix}｜{point.status.name}",
            message="；".join(status_reasons),
            suggestion=suggestion,
            push_status="pending" if should_queue else "skipped",
            push_attempts=0,
            pushed_at=None,
            push_error=push_error,
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None,
            resolution_note=None,
        )
        self.session.add(event)
        return event

    def _current_control_name(
        self,
        *,
        room_id: uuid.UUID,
        anchor_name: str,
        start_date: date,
        end_date: date,
        hour_slot: str,
    ) -> str | None:
        names = {
            name
            for name in self.session.scalars(
                select(HourlyFact.actual_control_canonical).where(
                    HourlyFact.room_id == room_id,
                    HourlyFact.business_date >= start_date,
                    HourlyFact.business_date <= end_date,
                    HourlyFact.hour_slot == hour_slot,
                    HourlyFact.actual_anchor_canonical == anchor_name,
                    HourlyFact.data_status == "complete",
                )
            )
            if name
        }
        return "、".join(sorted(names)) or None

    def _person_id(self, name: str) -> uuid.UUID | None:
        normalized = normalize_person_name(name)
        base_name = normalized.base_name if normalized is not None else name
        matches = list(
            self.session.scalars(
                select(Person).where(
                    Person.active.is_(True),
                    or_(Person.display_name == name, Person.base_name == base_name),
                )
            )
        )
        exact = next((person for person in matches if person.display_name == name), None)
        if exact is not None:
            return exact.id
        return matches[0].id if len(matches) == 1 else None

    def _push_configured(self, push_chat_id: str | None) -> bool:
        if not push_chat_id:
            return self.settings.feishu_bot_configured
        return bool(
            push_chat_id.startswith("oc_")
            and self.settings.feishu_app_id
            and self.settings.feishu_app_secret
        )

    @staticmethod
    def _alert_type(status_code: str) -> str:
        return {
            "roi_below_target": "anchor_roi_below_target",
            "improving_below_target": "anchor_roi_below_target",
            "roi_target_reached": "anchor_roi_target_reached",
            "roi_target_breakthrough": "anchor_roi_target_breakthrough",
            "roi_excellent_growth": "anchor_roi_increase",
            "roi_severe_drop": "anchor_roi_decrease",
            "spend_anomaly": "anchor_spend_increase",
            "efficiency_deterioration": "anchor_efficiency_deterioration",
            "excellent_scaling": "anchor_excellent_scaling",
            "scaling_normal": "anchor_scaling_normal",
            "unable_to_judge": "anchor_data_insufficient",
        }.get(status_code, f"anchor_{status_code}")

    @staticmethod
    def _message_color(level: str) -> str:
        if level == "positive":
            return "green"
        if level in {"critical", "warning", "improving"}:
            return "red"
        return "gray"

    @staticmethod
    def _detailed_reasons(
        point: object,
        rule: HourlyComparisonRule,
    ) -> list[str]:
        from app.api.schemas import HourlySeriesPointPayload

        if not isinstance(point, HourlySeriesPointPayload):
            return []
        reasons: list[str] = []
        codes = set(point.status.reason_codes)
        spend_growth = point.comparison_result.spend_growth_percentage
        roi_growth = point.comparison_result.roi_growth_percentage
        if "incomplete_data" in codes:
            current_coverage = (
                point.current.coverage_rate * Decimal(100)
                if point.current.coverage_rate is not None
                else None
            )
            minimum_coverage = rule.minimum_coverage_rate * Decimal(100)
            reasons.append(
                f"数据完整率{current_coverage:.2f}%低于{minimum_coverage:.2f}%"
                if current_coverage is not None
                else f"数据完整率低于{minimum_coverage:.2f}%"
            )
        if "target_not_configured" in codes:
            reasons.append("未配置ROI目标")
        if "no_comparable_baseline" in codes:
            reasons.append("无有效可比基准")
        if "spend_increase" in codes and spend_growth is not None:
            reasons.append(f"消耗较基准上涨{spend_growth:.2f}%")
        if "spend_decrease" in codes and spend_growth is not None:
            reasons.append(f"消耗较基准下降{abs(spend_growth):.2f}%")
        if {"roi_decrease", "roi_severe_decrease"}.intersection(codes) and roi_growth is not None:
            reasons.append(f"ROI较基准下降{abs(roi_growth):.2f}%")
        if "roi_increase" in codes and roi_growth is not None:
            reasons.append(f"ROI较基准上涨{roi_growth:.2f}%")
        if "roi_below_target" in codes and point.current.roi is not None and point.roi_target:
            reasons.append(f"当前ROI {point.current.roi:.2f}低于目标值{point.roi_target:.2f}")
        if "roi_target_reached" in codes and point.current.roi is not None and point.roi_target:
            reasons.append(f"当前ROI {point.current.roi:.2f}达到目标值{point.roi_target:.2f}")
        for reason in point.status.reasons:
            if reason not in reasons and not any(
                token in reason for token in ("上涨达到", "下降达到", "ROI 低于", "ROI 达到")
            ):
                reasons.append(reason)
        return reasons or list(point.status.reasons)

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _hash_payload(value: dict[str, object]) -> str:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
