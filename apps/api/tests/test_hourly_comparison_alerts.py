from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.paths import project_root
from app.db.base import Base
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    AlertEvent,
    HourlyComparisonRule,
    HourlyFact,
    HourlyMetric,
    Room,
    RoomMetricTarget,
)
from app.services.alert_service import AlertService
from app.services.hourly_comparison_alert_service import HourlyComparisonAlertService


def add_fact(session: Session, room: Room, business_date: date, amount: str, spend: str) -> None:
    hour = 8
    end = datetime.combine(business_date, datetime.min.time()) + timedelta(hours=hour + 1)
    fact = HourlyFact(
        room_id=room.id,
        business_date=business_date,
        year=business_date.year,
        month=business_date.month,
        hour_slot="08-09",
        hour_order=hour,
        hour_start_at=end - timedelta(hours=1),
        hour_end_at=end,
        latest_point_id=None,
        latest_observed_at=end,
        actual_anchor_canonical="测试主播",
        actual_anchor_base_names=["测试主播"],
        actual_control_canonical="测试场控",
        planned_anchor_canonical="测试主播",
        planned_anchor_base_names=["测试主播"],
        anchor_schedule_status="scheduled",
        anchor_match_status="matched",
        control_shift_name="早班",
        control_is_scheduled=True,
        control_is_rest=False,
        control_may_be_on_duty=True,
        data_status="complete",
    )
    session.add(fact)
    session.flush()
    values = {
        "period_overall_amount": Decimal(amount),
        "period_spend": Decimal(spend),
        "period_overall_roi": Decimal("999"),
        "period_overall_orders": Decimal("10"),
    }
    for key, value in values.items():
        session.add(
            HourlyMetric(
                hourly_fact_id=fact.id,
                metric_key=key,
                numeric_value=value,
                value_source="actual",
                quality_status="valid",
            )
        )


def test_hourly_comparison_alert_merges_reasons_and_deduplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")
    settings = Settings(
        app_env="test",
        feishu_bot_webhook_url="https://example.test/hook",
        app_base_url="http://dashboard.test",
    )
    now = datetime(2026, 7, 9, 8, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
    with Session(engine) as session:
        room = Room(
            name="柏瑞美-散粉",
            brand="柏瑞美",
            category="散粉",
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        session.add_all(
            [
                RoomMetricTarget(
                    room_id=room.id,
                    room_name=room.name,
                    product_category="散粉",
                    metric_code="period_overall_roi",
                    target_value=Decimal("1.81"),
                    effective_start_date=None,
                    effective_end_date=None,
                    enabled=True,
                    updated_by=None,
                ),
                HourlyComparisonRule(
                    name="默认1天小时对比预警",
                    period_days=1,
                    spend_increase_threshold=Decimal("0.30"),
                    spend_decrease_threshold=Decimal("-0.30"),
                    roi_increase_threshold=Decimal("0.30"),
                    roi_decrease_threshold=Decimal("-0.30"),
                    minimum_spend=Decimal("100"),
                    minimum_orders=0,
                    minimum_coverage_rate=Decimal("0.80"),
                    evaluation_delay_minutes=15,
                    applicable_rooms=[],
                    applicable_anchors=[],
                    enabled=True,
                    push_enabled=True,
                    push_chat_id=None,
                    cooldown_minutes=60,
                    created_by=None,
                    updated_by=None,
                ),
            ]
        )
        add_fact(session, room, date(2026, 7, 7), amount="180", spend="100")
        add_fact(session, room, date(2026, 7, 8), amount="190", spend="130")
        session.commit()

        service = HourlyComparisonAlertService(session, settings, catalog)
        event_ids = service.evaluate_due_event_ids(now)
        assert len(event_ids) == 1
        assert service.evaluate_due_event_ids(now) == []

        event = session.scalar(select(AlertEvent))
        assert event is not None
        assert event.status_code == "efficiency_deterioration"
        assert event.alert_type == "anchor_efficiency_deterioration"
        assert event.period_days == 1
        assert event.current_period_start == event.current_period_end == date(2026, 7, 8)
        assert event.comparison_period_start == event.comparison_period_end == date(2026, 7, 7)
        assert event.hour_slot == "08-09"
        assert event.anchor_name == "测试主播"
        assert event.control_name == "测试场控"
        assert event.metric_codes == ["period_overall_roi", "period_spend"]
        assert event.current_spend == Decimal("130")
        assert event.baseline_spend == Decimal("100")
        assert event.spend_growth_rate == Decimal("0.30")
        assert event.current_roi == Decimal("1.46153846")
        assert event.baseline_roi == Decimal("1.80")
        assert event.roi_target == Decimal("1.81")
        assert event.roi_target_reached is False
        assert event.notification_type == "red_alert"
        assert event.message_color == "red"
        assert event.base_dedup_key
        assert event.state_version == 0
        assert event.push_status == "pending"

        card = AlertService(session, settings)._event_card(event)
        serialized = json.dumps(card, ensure_ascii=False)
        assert "消耗效率恶化" in serialized
        assert "测试主播" in serialized
        assert "测试场控" in serialized
        assert "当前消耗" in serialized
        assert "ROI目标" in serialized
        assert "查看预警详情" in serialized
        assert "查看经营总览" in serialized
        assert "查看小时趋势" in serialized
        assert "查看主播分析" in serialized

        current_fact = session.scalar(
            select(HourlyFact).where(
                HourlyFact.room_id == room.id,
                HourlyFact.business_date == date(2026, 7, 8),
            )
        )
        assert current_fact is not None
        amount_metric = session.scalar(
            select(HourlyMetric).where(
                HourlyMetric.hourly_fact_id == current_fact.id,
                HourlyMetric.metric_key == "period_overall_amount",
            )
        )
        assert amount_metric is not None
        amount_metric.numeric_value = Decimal("247")
        session.commit()

        changed_event_ids = service.evaluate_due_event_ids(now)
        assert len(changed_event_ids) == 1
        events = list(session.scalars(select(AlertEvent).order_by(AlertEvent.state_version)))
        assert len(events) == 2
        assert [item.status_code for item in events] == [
            "efficiency_deterioration",
            "roi_target_breakthrough",
        ]
        assert [item.state_version for item in events] == [0, 1]
        green = events[1]
        assert green.notification_type == "green_excellent"
        assert green.message_color == "green"
        assert green.roi_target_reached is True
        green_card = AlertService(session, settings)._event_card(green)
        assert green_card["card"]["header"]["template"] == "green"
        assert "主播优秀数据" in json.dumps(green_card, ensure_ascii=False)


def test_hourly_comparison_alert_waits_until_t_plus_one_delay_boundary() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")
    with Session(engine) as session:
        service = HourlyComparisonAlertService(session, Settings(app_env="test"), catalog)
        before = datetime(2026, 7, 8, 8, 14, tzinfo=ZoneInfo("Asia/Shanghai"))
        boundary = service.latest_due_business_date(
            before,
            submission_hour=8,
            delay_minutes=15,
        )
        assert boundary == date(2026, 7, 6)
        at_delay = service.latest_due_business_date(
            before + timedelta(minutes=1),
            submission_hour=8,
            delay_minutes=15,
        )
        assert at_delay == date(2026, 7, 7)


def test_incomplete_anchor_period_is_visible_but_never_queued() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")
    now = datetime(2026, 7, 9, 8, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
    with Session(engine) as session:
        room = Room(
            name="柏瑞美-散粉",
            brand="柏瑞美",
            category="散粉",
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        session.add_all(
            [
                RoomMetricTarget(
                    room_id=room.id,
                    room_name=room.name,
                    product_category="散粉",
                    metric_code="period_overall_roi",
                    target_value=Decimal("1.81"),
                    effective_start_date=None,
                    effective_end_date=None,
                    enabled=True,
                    updated_by=None,
                ),
                HourlyComparisonRule(
                    name="默认7天小时对比预警",
                    period_days=7,
                    spend_increase_threshold=Decimal("0.30"),
                    spend_decrease_threshold=Decimal("-0.30"),
                    roi_increase_threshold=Decimal("0.30"),
                    roi_decrease_threshold=Decimal("-0.30"),
                    minimum_spend=Decimal("100"),
                    minimum_orders=0,
                    minimum_coverage_rate=Decimal("0.80"),
                    evaluation_delay_minutes=15,
                    applicable_rooms=[],
                    applicable_anchors=[],
                    enabled=True,
                    push_enabled=True,
                    push_chat_id=None,
                    cooldown_minutes=60,
                    created_by=None,
                    updated_by=None,
                ),
            ]
        )
        for offset in range(14):
            business_date = date(2026, 6, 25) + timedelta(days=offset)
            add_fact(session, room, business_date, amount="180", spend="100")
            if offset in {12, 13}:
                fact = session.scalar(
                    select(HourlyFact).where(
                        HourlyFact.room_id == room.id,
                        HourlyFact.business_date == business_date,
                    )
                )
                assert fact is not None
                fact.data_status = "missing"
                fact.actual_anchor_canonical = None
                fact.actual_anchor_base_names = []
        session.commit()

        event_ids = HourlyComparisonAlertService(
            session,
            Settings(
                app_env="test",
                feishu_bot_webhook_url="https://example.test/hook",
            ),
            catalog,
        ).evaluate_due_event_ids(now)

        assert len(event_ids) == 1
        event = session.get(AlertEvent, event_ids[0])
        assert event is not None
        assert event.status_code == "unable_to_judge"
        assert event.message_color == "gray"
        assert event.notification_type == "gray_info"
        assert event.push_status == "skipped"
        assert "数据完整率71.43%低于80.00%" in event.status_reasons
        assert event.comparison_context["coverage_rate"] == str(Decimal(5) / Decimal(7))
