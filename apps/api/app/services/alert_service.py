from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import utc_now
from app.domain.alerts import (
    AlertContext,
    AlertDecision,
    alert_dedup_key,
    comparison_copy,
    evaluate_ratio_rule,
)
from app.domain.cleaning import normalize_person_name
from app.domain.data_freshness import data_is_due, schedule_expects_data, submission_deadline
from app.integrations.feishu.bot import FeishuAppBotClient, FeishuBotClient
from app.models.entities import (
    AlertEvent,
    AlertRule,
    FeishuGroup,
    FeishuGroupRoomScope,
    HourlyFact,
    HourlyMetric,
    LivePoint,
    Person,
    Room,
    StaffSchedule,
)

DATA_QUALITY_ONLY_RULE_TYPES = frozenset(
    {
        "data_delay",
        "missing_data",
        "unentered_data",
        "delayed_entry",
        "missing_hourly_record",
    }
)


class AlertService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        allowed_room_ids: frozenset[uuid.UUID] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.allowed_room_ids = allowed_room_ids

    def ensure_default_rules(self) -> list[AlertRule]:
        defaults = (
            {
                "name": "ROI 优秀上涨",
                "rule_type": "roi_surge",
                "operator": ">=",
                "threshold": Decimal("1.5"),
                "severity": "info",
            },
            {
                "name": "ROI 暴跌",
                "rule_type": "roi_drop",
                "operator": "<=",
                "threshold": Decimal("-0.3"),
                "severity": "critical",
            },
            {
                "name": "ROI 低于底线",
                "rule_type": "roi_floor",
                "operator": "<",
                "threshold": Decimal("1.2"),
                "severity": "warning",
            },
            {
                "name": "主播排班不一致",
                "rule_type": "anchor_mismatch",
                "operator": "!=",
                "threshold": Decimal(0),
                "severity": "warning",
            },
            {
                "name": "数据延迟",
                "rule_type": "data_delay",
                "operator": ">=",
                "threshold": Decimal(self.settings.data_submission_deadline_hour),
                "severity": "critical",
                "push_enabled": False,
            },
        )
        rules: list[AlertRule] = []
        for item in defaults:
            rule = self.session.scalar(
                select(AlertRule).where(AlertRule.rule_type == item["rule_type"])
            )
            if rule is None:
                rule = AlertRule(
                    name=str(item["name"]),
                    rule_type=str(item["rule_type"]),
                    metric_key="period_overall_roi"
                    if str(item["rule_type"]).startswith("roi_")
                    else None,
                    comparison_type="previous_day",
                    operator=str(item["operator"]),
                    threshold=cast(Decimal, item["threshold"]),
                    min_spend=Decimal("100") if str(item["rule_type"]).startswith("roi_") else None,
                    min_orders=None,
                    min_amount=None,
                    room_scope=[],
                    anchor_scope=[],
                    control_scope=[],
                    severity=str(item["severity"]),
                    cooldown_minutes=60,
                    enabled=True,
                    push_enabled=bool(item.get("push_enabled", True)),
                    suggestion_template="请核对投放、商品、主播状态和数据同步情况。",
                    created_by=None,
                )
                self.session.add(rule)
                self.session.flush()
            elif rule.rule_type == "data_delay":
                rule.operator = str(item["operator"])
                rule.threshold = cast(Decimal, item["threshold"])
                rule.push_enabled = False
            rules.append(rule)
        self.session.commit()
        return rules

    def evaluate_all(self) -> int:
        return len(self.evaluate_event_ids())

    def evaluate_event_ids(
        self, target_fact_ids: frozenset[uuid.UUID] | None = None
    ) -> list[uuid.UUID]:
        rules = [rule for rule in self.ensure_default_rules() if rule.enabled]
        facts = list(self.session.scalars(select(HourlyFact)))
        metrics = list(self.session.scalars(select(HourlyMetric)))
        metric_map: dict[tuple[uuid.UUID, str], Decimal | None] = {
            (metric.hourly_fact_id, metric.metric_key): metric.numeric_value for metric in metrics
        }
        facts_by_key = {(fact.room_id, fact.business_date, fact.hour_slot): fact for fact in facts}
        created: list[AlertEvent] = []
        for fact in facts:
            if not self._can_access(fact.room_id):
                continue
            if target_fact_ids is not None and fact.id not in target_fact_ids:
                continue
            for rule in rules:
                decision, current, baseline = self._decision(fact, rule, metric_map, facts_by_key)
                if not decision.triggered:
                    continue
                event = self._create_event(fact, rule, decision, current, baseline)
                if event is not None:
                    created.append(event)
        self.session.flush()
        event_ids = [event.id for event in created]
        self.session.commit()
        return event_ids

    async def evaluate_and_push(self) -> dict[str, int]:
        recovered = len(self._reconcile_recovered_data_delay_fact_ids())
        event_ids = self.evaluate_event_ids()
        result = await self.push_events(event_ids)
        return {"recovered": recovered, "created": len(event_ids), **result}

    async def evaluate_recent_and_push(self) -> dict[str, int]:
        """Evaluate only recently closed hours so service restarts never backfill old alerts."""
        recovered_fact_ids = self._reconcile_recovered_data_delay_fact_ids()
        target_fact_ids = self._recent_fact_ids() | recovered_fact_ids
        event_ids = self.evaluate_event_ids(target_fact_ids)
        result = await self.push_events(event_ids)
        return {"recovered": len(recovered_fact_ids), "created": len(event_ids), **result}

    def reconcile_recovered_data_delays(self) -> int:
        """Close data-delay alerts after a late but valid hourly point arrives."""
        return len(self._reconcile_recovered_data_delay_fact_ids())

    def _reconcile_recovered_data_delay_fact_ids(self) -> frozenset[uuid.UUID]:
        """Close recovered delays and return only the facts that need ROI re-evaluation."""
        delay_rule_ids = list(
            self.session.scalars(select(AlertRule.id).where(AlertRule.rule_type == "data_delay"))
        )
        if not delay_rule_ids:
            return frozenset()
        recovered_fact_ids: set[uuid.UUID] = set()
        changed = False
        events = list(
            self.session.scalars(
                select(AlertEvent).where(
                    AlertEvent.rule_id.in_(delay_rule_ids),
                    AlertEvent.acknowledged.is_(False),
                )
            )
        )
        for event in events:
            if not self._can_access(event.room_id):
                continue
            fact = self.session.scalar(
                select(HourlyFact).where(
                    HourlyFact.room_id == event.room_id,
                    HourlyFact.business_date == event.business_date,
                    HourlyFact.hour_slot == event.hour_slot,
                )
            )
            if fact is None:
                continue
            if not data_is_due(
                fact.business_date,
                self._local_now(),
                self.settings.data_submission_deadline_hour,
            ):
                event.acknowledged = True
                event.acknowledged_at = utc_now()
                event.resolution_note = "尚未到T+1补录截止时间，系统自动撤销误报"
                changed = True
                continue
            if event.anchor_name is None:
                event.anchor_name = fact.actual_anchor_canonical or fact.planned_anchor_canonical
                changed = changed or event.anchor_name is not None
            if event.control_name is None:
                event.control_name = (
                    fact.actual_control_canonical
                    or "、".join(self._scheduled_control_names(fact.business_date, fact.hour_order))
                    or None
                )
                changed = changed or event.control_name is not None
            baseline = self._previous_day_roi(fact)
            if event.baseline_value != baseline:
                event.baseline_value = baseline
                changed = True
            message = self._data_delay_message(baseline)
            if event.message != message:
                event.message = message
                changed = True
            if fact.data_status != "complete":
                continue
            event.acknowledged = True
            event.acknowledged_at = utc_now()
            event.resolution_note = "实绩已补录，系统自动恢复"
            recovered_fact_ids.add(fact.id)
            changed = True
        if changed:
            self.session.commit()
        return frozenset(recovered_fact_ids)

    async def push_queued_events(self) -> dict[str, int]:
        stale_sending = utc_now() - timedelta(minutes=5)
        event_ids = list(
            self.session.scalars(
                select(AlertEvent.id).where(
                    or_(
                        AlertEvent.push_status == "pending",
                        AlertEvent.push_status == "failed",
                        and_(
                            AlertEvent.push_status == "sending",
                            AlertEvent.pushed_at < stale_sending,
                        ),
                    ),
                    AlertEvent.push_attempts < self.settings.alert_retry_limit,
                )
            )
        )
        return await self.push_events(event_ids)

    async def push_events(self, event_ids: list[uuid.UUID]) -> dict[str, int]:
        sent = 0
        failed = 0
        skipped = 0
        for event_id in event_ids:
            event = self.session.get(AlertEvent, event_id)
            if event is None or event.push_status not in {"pending", "failed", "sending"}:
                skipped += 1
                continue
            try:
                result = await self.push_event(event_id)
                if result.get("mocked"):
                    skipped += 1
                else:
                    sent += 1
            except Exception:
                failed += 1
        return {"queued": len(event_ids), "sent": sent, "failed": failed, "skipped": skipped}

    def list_events(
        self,
        *,
        room_ids: tuple[uuid.UUID, ...] = (),
        anchor_names: tuple[str, ...] = (),
        control_names: tuple[str, ...] = (),
        hour_slots: tuple[str, ...] = (),
        period_days: tuple[int, ...] = (),
        notification_types: tuple[str, ...] = (),
        alert_types: tuple[str, ...] = (),
        pushed: bool | None = None,
        acknowledged: bool | None = None,
    ) -> list[dict[str, Any]]:
        rooms = {room.id: room.name for room in self.session.scalars(select(Room))}
        query = select(AlertEvent)
        if self.allowed_room_ids is not None:
            query = query.where(AlertEvent.room_id.in_(self.allowed_room_ids))
        if room_ids:
            permitted = set(room_ids)
            if self.allowed_room_ids is not None:
                permitted.intersection_update(self.allowed_room_ids)
            if not permitted:
                return []
            query = query.where(AlertEvent.room_id.in_(permitted))
        if anchor_names:
            query = query.where(AlertEvent.anchor_name.in_(anchor_names))
        if control_names:
            query = query.where(AlertEvent.control_name.in_(control_names))
        if hour_slots:
            query = query.where(AlertEvent.hour_slot.in_(hour_slots))
        if period_days:
            query = query.where(AlertEvent.period_days.in_(period_days))
        if notification_types:
            query = query.where(AlertEvent.notification_type.in_(notification_types))
        if alert_types:
            query = query.where(AlertEvent.alert_type.in_(alert_types))
        if pushed is True:
            query = query.where(AlertEvent.push_status == "sent")
        elif pushed is False:
            query = query.where(AlertEvent.push_status != "sent")
        if acknowledged is not None:
            query = query.where(AlertEvent.acknowledged.is_(acknowledged))
        events = list(self.session.scalars(query.order_by(AlertEvent.triggered_at.desc())))
        return [
            self._event_payload(event, rooms.get(event.room_id, "未知直播间")) for event in events
        ]

    def get_event(self, event_id: uuid.UUID) -> dict[str, Any]:
        event = self.session.get(AlertEvent, event_id)
        if event is None or not self._can_access(event.room_id):
            raise LookupError("预警事件不存在")
        room = self.session.get(Room, event.room_id)
        return self._event_payload(event, room.name if room else "未知直播间")

    def list_rules(self) -> list[dict[str, Any]]:
        rules = list(self.session.scalars(select(AlertRule).order_by(AlertRule.created_at)))
        return [self._rule_payload(rule) for rule in rules]

    def create_rule(self, payload: dict[str, Any], user_id: uuid.UUID | None) -> dict[str, Any]:
        rule = AlertRule(**payload, created_by=user_id)
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return self._rule_payload(rule)

    def update_rule(self, rule_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        rule = self.session.get(AlertRule, rule_id)
        if rule is None:
            raise LookupError("预警规则不存在")
        for key, value in payload.items():
            setattr(rule, key, value)
        self.session.commit()
        return self._rule_payload(rule)

    def delete_rule(self, rule_id: uuid.UUID) -> None:
        rule = self.session.get(AlertRule, rule_id)
        if rule is None:
            raise LookupError("预警规则不存在")
        if self.session.scalar(select(AlertEvent.id).where(AlertEvent.rule_id == rule_id)):
            rule.enabled = False
        else:
            self.session.delete(rule)
        self.session.commit()

    @staticmethod
    def _rule_payload(rule: AlertRule) -> dict[str, Any]:
        return {
            column.name: getattr(rule, column.name)
            for column in AlertRule.__table__.columns
            if column.name not in {"created_by"}
        }

    @staticmethod
    def _event_payload(event: AlertEvent, room_name: str) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "triggered_at": event.triggered_at,
            "room_id": str(event.room_id),
            "room_name": room_name,
            "business_date": event.business_date,
            "hour_slot": event.hour_slot,
            "anchor_name": event.anchor_name,
            "control_name": event.control_name,
            "alert_type": event.alert_type,
            "status_code": event.status_code,
            "status_reasons": event.status_reasons,
            "period_days": event.period_days,
            "current_period_start": event.current_period_start,
            "current_period_end": event.current_period_end,
            "comparison_period_start": event.comparison_period_start,
            "comparison_period_end": event.comparison_period_end,
            "metric_key": event.metric_key,
            "current_value": event.current_value,
            "baseline_value": event.baseline_value,
            "delta_value": event.delta_value,
            "ratio_percent": event.ratio_percent,
            "growth_percent": event.growth_percent,
            "current_spend": event.current_spend,
            "baseline_spend": event.baseline_spend,
            "spend_growth_rate": event.spend_growth_rate,
            "current_roi": event.current_roi,
            "baseline_roi": event.baseline_roi,
            "roi_growth_rate": event.roi_growth_rate,
            "roi_target": event.roi_target,
            "roi_target_gap": event.roi_target_gap,
            "roi_target_reached": event.roi_target_reached,
            "notification_type": event.notification_type,
            "message_color": event.message_color,
            "severity": event.severity,
            "title": event.title,
            "message": event.message,
            "suggestion": event.suggestion,
            "push_status": event.push_status,
            "push_attempts": event.push_attempts,
            "pushed_at": event.pushed_at,
            "push_error": event.push_error,
            "acknowledged": event.acknowledged,
            "acknowledged_at": event.acknowledged_at,
            "resolution_note": event.resolution_note,
        }

    def _can_access(self, room_id: uuid.UUID) -> bool:
        return self.allowed_room_ids is None or room_id in self.allowed_room_ids

    def acknowledge(
        self, event_id: uuid.UUID, resolution_note: str, user_id: uuid.UUID | None
    ) -> AlertEvent:
        event = self.session.get(AlertEvent, event_id)
        if event is None or not self._can_access(event.room_id):
            raise LookupError("预警事件不存在")
        event.acknowledged = True
        event.acknowledged_by = user_id
        event.acknowledged_at = utc_now()
        event.resolution_note = resolution_note
        self.session.commit()
        return event

    async def push_event(self, event_id: uuid.UUID) -> dict[str, Any]:
        event = self.session.get(AlertEvent, event_id)
        if event is None or not self._can_access(event.room_id):
            raise LookupError("预警事件不存在")
        rule = self.session.get(AlertRule, event.rule_id)
        if (
            rule is not None and rule.rule_type in DATA_QUALITY_ONLY_RULE_TYPES
        ) or event.alert_type in DATA_QUALITY_ONLY_RULE_TYPES:
            event.push_status = "skipped"
            event.push_error = "数据质量事件仅系统记录，业务群推送已关闭"
            self.session.commit()
            raise ValueError("数据质量事件不得发送到业务运营群")
        if event.push_status == "sent":
            raise ValueError("预警已发送，不能重复推送")
        if event.push_attempts >= self.settings.alert_retry_limit:
            raise ValueError("预警已达到重试上限")
        if event.push_status == "sending" and (
            event.pushed_at is None or event.pushed_at >= utc_now() - timedelta(minutes=5)
        ):
            raise ValueError("预警正在发送")
        payload = self._event_card(event)
        push_configured = (
            bool(
                event.push_chat_id
                and event.push_chat_id.startswith("oc_")
                and self.settings.feishu_app_id
                and self.settings.feishu_app_secret
            )
            if event.push_chat_id
            else self.settings.feishu_bot_configured
        )
        if not push_configured:
            event.push_status = "skipped"
            event.push_error = "未配置对应机器人或应用机器人群，使用 Mock 推送"
            self.session.commit()
            return {"mocked": True, "payload": payload}
        claimed_at = utc_now()
        stale_sending = claimed_at - timedelta(minutes=5)
        claimed_event_id = self.session.scalar(
            update(AlertEvent)
            .where(
                AlertEvent.id == event_id,
                AlertEvent.push_attempts < self.settings.alert_retry_limit,
                or_(
                    AlertEvent.push_status.in_(("pending", "failed")),
                    and_(
                        AlertEvent.push_status == "sending",
                        AlertEvent.pushed_at < stale_sending,
                    ),
                ),
            )
            .values(
                push_status="sending",
                push_attempts=AlertEvent.push_attempts + 1,
                pushed_at=claimed_at,
                push_error=None,
            )
            .returning(AlertEvent.id)
        )
        if claimed_event_id is None:
            self.session.rollback()
            raise ValueError("预警已发送、正在发送或已达到重试上限")
        self.session.commit()
        event = self.session.get(AlertEvent, event_id)
        if event is None:
            raise LookupError("预警事件不存在")
        try:
            result = await self.send_card(
                payload,
                idempotency_key=str(event.id),
                chat_id=event.push_chat_id,
                room_ids=frozenset({event.room_id}),
            )
            event.push_status = "sent"
            event.pushed_at = utc_now()
            event.push_error = None
            self.session.commit()
            return result
        except Exception as exc:
            event.push_status = "failed"
            event.push_error = str(exc)
            self.session.commit()
            raise

    async def push_test_card(self) -> dict[str, Any]:
        return await self.send_card(
            self.test_card(),
            idempotency_key=str(uuid.uuid4()),
            test_payload=True,
        )

    async def send_card(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        chat_id: str | None = None,
        room_ids: frozenset[uuid.UUID] | None = None,
        test_payload: bool = False,
    ) -> dict[str, Any]:
        """Send an audited caller-built card through the configured Feishu transport."""
        if chat_id and not (
            chat_id.startswith("oc_")
            and self.settings.feishu_app_id
            and self.settings.feishu_app_secret
        ):
            return {"mocked": True, "payload": payload}
        if not chat_id and not self.settings.feishu_bot_configured:
            return {"mocked": True, "payload": payload}
        self._authorize_destination(chat_id, room_ids, test_payload=test_payload)
        return await self._send_payload(
            payload,
            idempotency_key=idempotency_key,
            chat_id=chat_id,
        )

    def _authorize_destination(
        self,
        chat_id: str | None,
        room_ids: frozenset[uuid.UUID] | None,
        *,
        test_payload: bool,
    ) -> None:
        destination = chat_id or self.settings.feishu_bot_chat_id
        group = (
            self.session.scalar(
                select(FeishuGroup).where(
                    FeishuGroup.chat_id == destination,
                    FeishuGroup.enabled.is_(True),
                )
            )
            if destination
            else None
        )
        if group is None:
            raise ValueError("飞书目标群未注册或已禁用")
        allowed_room_ids = frozenset(
            self.session.scalars(
                select(FeishuGroupRoomScope.room_id).where(
                    FeishuGroupRoomScope.group_id == group.id
                )
            )
        )
        if not group.all_rooms and not allowed_room_ids:
            raise ValueError("飞书目标群未配置任何直播间范围")
        if test_payload:
            return
        if not room_ids:
            raise ValueError("业务消息缺少可授权的直播间范围")
        if not group.all_rooms and not room_ids.issubset(allowed_room_ids):
            raise ValueError("业务消息包含目标群未授权的直播间")

    async def _send_payload(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        chat_id: str | None = None,
    ) -> dict[str, Any]:
        if chat_id:
            app_bot = FeishuAppBotClient(
                self.settings.feishu_app_id,
                self.settings.feishu_app_secret,
                chat_id,
                max_attempts=self.settings.alert_retry_limit,
            )
            try:
                result = await app_bot.send(payload, idempotency_key=idempotency_key)
                return {"mocked": False, "transport": "app_bot", "result": result}
            finally:
                await app_bot.close()
        if self.settings.feishu_webhook_bot_configured:
            webhook = FeishuBotClient(
                self.settings.feishu_bot_webhook_url,
                self.settings.feishu_bot_secret,
                max_attempts=self.settings.alert_retry_limit,
            )
            try:
                result = await webhook.send(payload)
                return {"mocked": False, "transport": "webhook", "result": result}
            finally:
                await webhook.close()
        if self.settings.feishu_app_bot_configured:
            app_bot = FeishuAppBotClient(
                self.settings.feishu_app_id,
                self.settings.feishu_app_secret,
                self.settings.feishu_bot_chat_id,
                max_attempts=self.settings.alert_retry_limit,
            )
            try:
                result = await app_bot.send(payload, idempotency_key=idempotency_key)
                return {"mocked": False, "transport": "app_bot", "result": result}
            finally:
                await app_bot.close()
        return {"mocked": True, "payload": payload}

    def test_card(self) -> dict[str, Any]:
        return FeishuBotClient.build_card(
            "【直播间小时预警｜模拟测试】",
            [
                "**直播间：** 柏瑞美-散粉",
                "**日期时段：** 2026-07-08 08-09",
                "**当前ROI：** 3.00",
                "**结果：** 当前ROI是昨日同小时的200%，较昨日提升100%。",
                "**建议：** 核对投放和商品承接，确认优秀时段可复制因素。",
            ],
            {"查看预警详情": f"{self.settings.app_base_url}/alerts"},
        )

    def _decision(
        self,
        fact: HourlyFact,
        rule: AlertRule,
        metric_map: dict[tuple[uuid.UUID, str], Decimal | None],
        facts_by_key: dict[tuple[uuid.UUID, Any, str], HourlyFact],
    ) -> tuple[AlertDecision, Decimal | None, Decimal | None]:
        if rule.rule_type == "data_delay":
            delayed = (
                fact.data_status == "missing"
                and schedule_expects_data(fact.anchor_schedule_status)
                and data_is_due(
                    fact.business_date,
                    self._local_now(),
                    self.settings.data_submission_deadline_hour,
                )
            )
            baseline_fact = facts_by_key.get(
                (fact.room_id, fact.business_date - timedelta(days=1), fact.hour_slot)
            )
            baseline = (
                metric_map.get((baseline_fact.id, "period_overall_roi")) if baseline_fact else None
            )
            return AlertDecision(delayed, reason="超过T+1补录截止时间仍无有效实绩"), None, baseline
        if rule.rule_type == "anchor_mismatch":
            mismatch = fact.anchor_match_status in {"mismatched", "off_air_but_live"}
            return AlertDecision(mismatch, reason="实际主播成员集合与计划不一致"), None, None
        if fact.data_status != "complete":
            return AlertDecision(False, reason="无有效实绩"), None, None
        current = metric_map.get((fact.id, "period_overall_roi"))
        spend = metric_map.get((fact.id, "period_spend"))
        orders = metric_map.get((fact.id, "period_overall_orders"))
        amount = metric_map.get((fact.id, "period_overall_amount"))
        baseline_fact = facts_by_key.get(
            (fact.room_id, fact.business_date - timedelta(days=1), fact.hour_slot)
        )
        baseline = (
            metric_map.get((baseline_fact.id, "period_overall_roi")) if baseline_fact else None
        )
        if rule.rule_type == "roi_floor":
            triggered = (
                current is not None
                and current < rule.threshold
                and (spend or Decimal(0)) >= (rule.min_spend or Decimal(0))
            )
            ratio_percent: Decimal | None = None
            growth_percent: Decimal | None = None
            if current is not None and baseline is not None and baseline != Decimal(0):
                ratio = current / baseline
                ratio_percent = ratio * Decimal(100)
                growth_percent = (ratio - Decimal(1)) * Decimal(100)
            return (
                AlertDecision(
                    triggered,
                    ratio_percent=ratio_percent,
                    growth_percent=growth_percent,
                    reason="低于 ROI 底线",
                ),
                current,
                baseline,
            )
        context = AlertContext(
            room_id=str(fact.room_id),
            business_date=fact.business_date,
            hour_slot=fact.hour_slot,
            anchor=fact.actual_anchor_canonical,
            control=fact.actual_control_canonical,
            metric_key="period_overall_roi",
            current_value=current,
            baseline_value=baseline,
            spend=spend,
            orders=orders,
            amount=amount,
        )
        operator: Literal[">=", "<="] = ">=" if rule.rule_type == "roi_surge" else "<="
        return (
            evaluate_ratio_rule(
                context,
                operator=operator,
                threshold=rule.threshold,
                min_spend=rule.min_spend or Decimal(0),
            ),
            current,
            baseline,
        )

    def _create_event(
        self,
        fact: HourlyFact,
        rule: AlertRule,
        decision: AlertDecision,
        current: Decimal | None,
        baseline: Decimal | None,
    ) -> AlertEvent | None:
        anchor_name = fact.actual_anchor_canonical
        control_name = fact.actual_control_canonical
        if rule.rule_type == "data_delay":
            anchor_name = anchor_name or fact.planned_anchor_canonical
            control_name = (
                control_name
                or "、".join(self._scheduled_control_names(fact.business_date, fact.hour_order))
                or None
            )
        metric_key = rule.metric_key or rule.rule_type
        key = alert_dedup_key(
            str(fact.room_id),
            fact.business_date,
            fact.hour_slot,
            anchor_name,
            control_name,
            metric_key,
            rule.rule_type,
        )
        if self.session.scalar(select(AlertEvent).where(AlertEvent.dedup_key == key)):
            return None
        cooldown_since = utc_now() - timedelta(minutes=rule.cooldown_minutes)
        if self.session.scalar(
            select(AlertEvent.id).where(
                AlertEvent.rule_id == rule.id,
                AlertEvent.room_id == fact.room_id,
                AlertEvent.triggered_at >= cooldown_since,
            )
        ):
            return None
        message = decision.reason
        if rule.rule_type == "data_delay":
            message = self._data_delay_message(baseline)
        if (
            current is not None
            and baseline is not None
            and decision.ratio_percent is not None
            and decision.growth_percent is not None
        ):
            message = comparison_copy(
                "ROI",
                current,
                baseline,
                decision.ratio_percent,
                decision.growth_percent,
            )
        data_quality_only = rule.rule_type in DATA_QUALITY_ONLY_RULE_TYPES
        should_push = (
            not data_quality_only and rule.push_enabled and self.settings.feishu_bot_configured
        )
        event = AlertEvent(
            rule_id=rule.id,
            dedup_key=key,
            triggered_at=utc_now(),
            room_id=fact.room_id,
            business_date=fact.business_date,
            hour_slot=fact.hour_slot,
            anchor_name=anchor_name,
            control_name=control_name,
            metric_key=metric_key,
            current_value=current,
            baseline_value=baseline,
            delta_value=(
                current - baseline if current is not None and baseline is not None else None
            ),
            ratio_percent=decision.ratio_percent,
            growth_percent=decision.growth_percent,
            severity=rule.severity,
            title=f"直播间小时预警｜{rule.name}",
            message=message,
            suggestion=rule.suggestion_template,
            push_status="pending" if should_push else "skipped",
            push_attempts=0,
            pushed_at=None,
            push_error=(
                None
                if should_push
                else "数据质量事件仅系统记录，业务群推送已关闭"
                if data_quality_only
                else "规则已关闭推送"
                if not rule.push_enabled
                else "未配置机器人，Mock 模式"
            ),
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None,
            resolution_note=None,
        )
        self.session.add(event)
        return event

    def _previous_day_roi(self, fact: HourlyFact) -> Decimal | None:
        baseline_fact = self.session.scalar(
            select(HourlyFact).where(
                HourlyFact.room_id == fact.room_id,
                HourlyFact.business_date == fact.business_date - timedelta(days=1),
                HourlyFact.hour_slot == fact.hour_slot,
            )
        )
        if baseline_fact is None:
            return None
        return self.session.scalar(
            select(HourlyMetric.numeric_value).where(
                HourlyMetric.hourly_fact_id == baseline_fact.id,
                HourlyMetric.metric_key == "period_overall_roi",
            )
        )

    def _data_delay_message(self, baseline: Decimal | None) -> str:
        deadline = f"{self.settings.data_submission_deadline_hour:02d}:00"
        if baseline is not None:
            return (
                f"截至次日{deadline}当前小时实绩仍未补录，ROI跌幅暂无法计算；"
                f"昨日同小时 ROI {baseline:.2f}。"
            )
        return f"截至次日{deadline}当前小时实绩仍未补录，且昨日同小时也无有效 ROI，跌幅暂无法计算。"

    def _event_card(self, event: AlertEvent) -> dict[str, Any]:
        room = self.session.get(Room, event.room_id)
        event_type = event.alert_type or ""
        if event_type == "hourly_comparison" or event_type.startswith("anchor_"):
            return self._hourly_comparison_event_card(event, room)
        rule = self.session.get(AlertRule, event.rule_id)
        is_data_delay = rule is not None and rule.rule_type == "data_delay"
        is_roi_alert = rule is not None and rule.rule_type.startswith("roi_")
        latest_point = self.session.scalar(
            select(LivePoint)
            .where(LivePoint.room_id == event.room_id, LivePoint.valid.is_(True))
            .order_by(LivePoint.observed_at.desc())
            .limit(1)
        )
        evidence = (
            f"{latest_point.business_date} {latest_point.hour_slot or '时段未知'}"
            if latest_point is not None
            else "尚无有效实绩"
        )
        severity_label = {
            "critical": "严重",
            "warning": "警告",
            "info": "提示",
        }.get(event.severity, event.severity)
        anchor_label = "计划主播" if is_data_delay else "主播"
        control_label = "排班场控" if is_data_delay else "场控"
        metric_lines: list[str] = []
        if is_data_delay:
            metric_lines.extend(
                [
                    "**当前 ROI：** 暂无（超过T+1填报截止仍未补录）",
                    (
                        f"**对比基准（昨日同小时）：** {event.baseline_value:.2f}"
                        if event.baseline_value is not None
                        else "**对比基准（昨日同小时）：** 暂无"
                    ),
                    "**ROI 跌幅：** 暂无法计算（不能将缺失值按 0 计算）",
                ]
            )
        elif rule is not None and is_roi_alert:
            metric_lines.append(
                f"**当前 ROI：** {event.current_value:.2f}"
                if event.current_value is not None
                else "**当前 ROI：** 暂无"
            )
            comparison_label = {
                "previous_day": "昨日同小时",
                "previous_week": "上周同小时",
                "previous_month": "上月同小时",
            }.get(rule.comparison_type or "", "规则基准")
            metric_lines.append(
                f"**对比基准（{comparison_label}）：** {event.baseline_value:.2f}"
                if event.baseline_value is not None
                else f"**对比基准（{comparison_label}）：** 暂无"
            )
            if event.delta_value is not None:
                if event.delta_value < 0:
                    metric_lines.append(f"**ROI 下降值：** {abs(event.delta_value):.2f}")
                elif event.delta_value > 0:
                    metric_lines.append(f"**ROI 提升值：** {event.delta_value:.2f}")
                else:
                    metric_lines.append("**ROI 变化值：** 0.00")
            if event.growth_percent is not None:
                if event.growth_percent < 0:
                    metric_lines.append(f"**ROI 跌幅：** {abs(event.growth_percent):.2f}%")
                elif event.growth_percent > 0:
                    metric_lines.append(f"**ROI 涨幅：** {event.growth_percent:.2f}%")
                else:
                    metric_lines.append("**ROI 涨跌幅：** 0.00%")
        return FeishuBotClient.build_card(
            f"【{event.title}】",
            [
                f"**直播间：** {room.name if room else '未知直播间'}",
                f"**日期时段：** {event.business_date} {event.hour_slot}",
                f"**{anchor_label}：** {event.anchor_name or '无主播排班'}",
                f"**{control_label}：** {event.control_name or '无法从排班确定'}",
                f"**预警级别：** {severity_label}",
                *metric_lines,
                f"**最近有效实绩：** {evidence}",
                f"**结果：** {event.message}",
                f"**建议：** {event.suggestion}",
            ],
            {
                "查看预警详情": f"{self.settings.app_base_url}/alerts?event={event.id}",
                "查看小时趋势": (
                    f"{self.settings.app_base_url}/timeline?start={event.business_date}"
                    f"&end={event.business_date}&hours={event.hour_slot}"
                ),
            },
        )

    def _hourly_comparison_event_card(self, event: AlertEvent, room: Room | None) -> dict[str, Any]:
        context = event.comparison_context or {}

        def text(key: str, default: str = "暂无") -> str:
            value = context.get(key)
            return str(value) if value not in {None, ""} else default

        def period(key: str) -> str:
            value = context.get(key)
            if not isinstance(value, dict):
                return "暂无"
            start = value.get("start")
            end = value.get("end")
            return f"{start} 至 {end}" if start and end else "暂无"

        def money(value: Decimal | None) -> str:
            return f"{value:,.2f}" if value is not None else "无有效可比基准"

        def ratio(value: Decimal | None) -> str:
            return f"{value:.2f}" if value is not None else "无有效可比基准"

        def percentage(value: Decimal | None) -> str:
            return f"{value * Decimal(100):.2f}%" if value is not None else "无有效可比基准"

        category = text("product_category", "ROI")
        reasons = event.status_reasons or [event.message]
        reason_lines = [f"- {reason}" for reason in reasons]
        coverage = text("coverage_rate")
        coverage_copy = (
            f"{Decimal(coverage) * Decimal(100):.2f}%" if coverage != "暂无" else "暂无排班基准"
        )
        overview_url = (
            f"{self.settings.app_base_url}/overview?rooms={event.room_id}"
            f"&hc_period={event.period_days or 1}&hc_end={event.current_period_end}"
            f"&hc_hour={event.hour_slot}"
        )
        target_status = (
            "已达标"
            if event.roi_target_reached is True
            else "未达标"
            if event.roi_target_reached is False
            else "未配置ROI目标"
        )
        theme = "green" if event.message_color == "green" else "red"
        return FeishuBotClient.build_card(
            f"【{event.title}】",
            [
                f"**直播间：** {room.name if room else text('room_name', '未知直播间')}",
                f"**主播：** {event.anchor_name or text('anchor_name', '未知主播')}",
                f"**场控：** {event.control_name or text('control_name', '未知场控')}",
                f"**自然小时：** {event.hour_slot}",
                f"**当前周期：** {period('current_period')}",
                f"**对比周期：** {period('comparison_period')}",
                (
                    f"**当前消耗：** ¥{money(event.current_spend)}；"
                    f"**基准消耗：** ¥{money(event.baseline_spend)}"
                ),
                f"**消耗变化：** {percentage(event.spend_growth_rate)}",
                (
                    f"**当前ROI：** {ratio(event.current_roi)}；"
                    f"**基准ROI：** {ratio(event.baseline_roi)}"
                ),
                f"**ROI变化：** {percentage(event.roi_growth_rate)}",
                (
                    f"**{category} ROI目标：** {ratio(event.roi_target)}；"
                    f"**目标差值：** {ratio(event.roi_target_gap)}；"
                    f"**目标状态：** {target_status}"
                ),
                f"**数据完整率：** {coverage_copy}",
                f"**综合判断：** {event.title}",
                "**全部原因：**",
                *reason_lines,
                f"**建议：** {event.suggestion}",
            ],
            {
                "查看预警详情": f"{self.settings.app_base_url}/alerts?event={event.id}",
                "查看经营总览": overview_url,
                "查看小时趋势": (
                    f"{self.settings.app_base_url}/timeline?start={event.business_date}"
                    f"&end={event.business_date}&rooms={event.room_id}&hours={event.hour_slot}"
                ),
                "查看主播分析": (
                    f"{self.settings.app_base_url}/anchors?start={event.current_period_start}"
                    f"&end={event.current_period_end}&rooms={event.room_id}"
                    f"&anchor={quote(event.anchor_name or '')}"
                ),
            },
            template=theme,
        )

    def _scheduled_control_names(self, business_date: Any, hour_order: int) -> list[str]:
        """Return controllers whose configured shift covers the requested natural hour."""
        rows = list(
            self.session.execute(
                select(Person, StaffSchedule)
                .join(StaffSchedule, StaffSchedule.person_id == Person.id)
                .where(
                    StaffSchedule.role == "场控",
                    StaffSchedule.schedule_date.in_(
                        [business_date, business_date - timedelta(days=1)]
                    ),
                )
            )
        )
        names: set[str] = set()
        for person, schedule in rows:
            if not self._schedule_covers_hour(schedule, business_date, hour_order):
                continue
            normalized = normalize_person_name(person.display_name or person.base_name)
            names.add(normalized.canonical if normalized else person.base_name.lstrip("@"))
        return sorted(names)

    @staticmethod
    def _schedule_covers_hour(schedule: StaffSchedule, business_date: Any, hour_order: int) -> bool:
        if (
            schedule.is_rest
            or not schedule.time_configured
            or schedule.shift_start is None
            or schedule.shift_end is None
        ):
            return False
        start = schedule.shift_start.hour
        end = schedule.shift_end.hour
        if not schedule.crosses_midnight:
            return schedule.schedule_date == business_date and start <= hour_order < end
        if schedule.schedule_date == business_date:
            return hour_order >= start
        return schedule.schedule_date == business_date - timedelta(days=1) and hour_order < end

    def _recent_fact_ids(self) -> frozenset[uuid.UUID]:
        now = self._local_now()
        lookback_minutes = max(
            15,
            self.settings.live_sync_interval_minutes * 3,
            self.settings.alert_delay_minutes + self.settings.live_sync_interval_minutes,
        )
        cutoff = now - timedelta(minutes=lookback_minutes)
        candidates: set[uuid.UUID] = set()
        for fact_id, business_date in self.session.execute(
            select(HourlyFact.id, HourlyFact.business_date)
        ):
            deadline = submission_deadline(
                business_date, self.settings.data_submission_deadline_hour
            )
            if cutoff <= deadline <= now:
                candidates.add(fact_id)
        return frozenset(candidates)

    def _local_now(self) -> datetime:
        return datetime.now(ZoneInfo(self.settings.timezone)).replace(tzinfo=None)

    def _as_local_naive(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(ZoneInfo(self.settings.timezone)).replace(tzinfo=None)

    def _now_for(self, value: Any) -> Any:
        """Compare alert times in the configured business timezone."""
        local_now = datetime.now(ZoneInfo(self.settings.timezone))
        if getattr(value, "tzinfo", None) is None:
            return local_now.replace(tzinfo=None)
        return local_now.astimezone(value.tzinfo)
