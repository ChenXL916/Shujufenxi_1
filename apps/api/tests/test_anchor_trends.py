import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AccessScope
from app.core.config import Settings
from app.core.paths import project_root
from app.db.base import Base
from app.domain.anchor_trends import AnchorTrendInput, evaluate_anchor_trend
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    AnchorTrendEvent,
    AnchorTrendItem,
    HourlyComparisonRule,
    HourlyFact,
    HourlyMetric,
    Room,
    RoomMetricTarget,
)
from app.services.anchor_trend_service import AnchorTrendService


def trend_input(
    *,
    current_roi: str = "1.95",
    baseline_roi: str = "1.50",
    current_spend: str = "13000",
    baseline_spend: str = "10000",
    target_roi: str = "1.81",
) -> AnchorTrendInput:
    return AnchorTrendInput(
        current_roi=Decimal(current_roi),
        baseline_roi=Decimal(baseline_roi),
        current_spend=Decimal(current_spend),
        baseline_spend=Decimal(baseline_spend),
        current_orders=Decimal("100"),
        baseline_orders=Decimal("100"),
        target_roi=Decimal(target_roi),
        current_coverage_rate=Decimal("1"),
        baseline_coverage_rate=Decimal("1"),
        current_effective_hours=24,
        baseline_effective_hours=24,
        minimum_spend=Decimal("0"),
        minimum_orders=0,
        minimum_coverage_rate=Decimal("0.80"),
        minimum_effective_hours=1,
        roi_rise_threshold=Decimal("0.30"),
        roi_fall_threshold=Decimal("-0.30"),
        spend_rise_threshold=Decimal("0.30"),
        spend_fall_threshold=Decimal("-0.30"),
    )


def test_anchor_trend_uses_unrounded_thirty_percent_boundaries() -> None:
    below_rise = evaluate_anchor_trend(
        trend_input(
            current_roi="1.29999", baseline_roi="1.00", current_spend="100", baseline_spend="100"
        )
    )
    exact_rise = evaluate_anchor_trend(
        trend_input(
            current_roi="1.30", baseline_roi="1.00", current_spend="100", baseline_spend="100"
        )
    )
    above_fall = evaluate_anchor_trend(
        trend_input(
            current_roi="0.70001", baseline_roi="1.00", current_spend="100", baseline_spend="100"
        )
    )
    exact_fall = evaluate_anchor_trend(
        trend_input(
            current_roi="0.70", baseline_roi="1.00", current_spend="100", baseline_spend="100"
        )
    )

    assert below_rise.primary_code != "roi_rise"
    assert exact_rise.primary_code == "roi_rise"
    assert exact_rise.trend_type == "rise"
    assert above_fall.primary_code != "roi_fall"
    assert exact_fall.primary_code == "roi_fall"
    assert exact_fall.trend_type == "fall"


def test_anchor_trend_zero_baseline_is_not_comparable() -> None:
    result = evaluate_anchor_trend(trend_input(baseline_roi="0"))

    assert result.trend_type == "insufficient"
    assert result.primary_code == "no_comparable_baseline"
    assert result.roi_growth_rate is None


def test_anchor_trend_double_rise_and_efficiency_deterioration_priority() -> None:
    double_rise = evaluate_anchor_trend(
        trend_input(
            current_roi="1.90",
            baseline_roi="1.40",
            current_spend="13000",
            baseline_spend="10000",
        )
    )
    deterioration = evaluate_anchor_trend(
        trend_input(
            current_roi="1.65",
            baseline_roi="1.70",
            current_spend="13500",
            baseline_spend="10000",
        )
    )

    assert double_rise.trend_type == "rise"
    assert double_rise.primary_code == "spend_roi_double_rise"
    assert double_rise.spend_growth_rate == Decimal("0.30")
    assert double_rise.roi_growth_rate == Decimal("1.90") / Decimal("1.40") - Decimal(1)
    assert deterioration.trend_type == "fall"
    assert deterioration.primary_code == "efficiency_deterioration"
    assert "roi_below_target" in deterioration.reason_codes


def test_anchor_trend_rise_below_target_keeps_truthful_target_state() -> None:
    result = evaluate_anchor_trend(
        trend_input(
            current_roi="1.50",
            baseline_roi="1.10",
            current_spend="10000",
            baseline_spend="10000",
            target_roi="1.81",
        )
    )

    assert result.trend_type == "rise"
    assert result.primary_code == "roi_rise"
    assert result.roi_target_reached is False
    assert result.roi_target_gap == Decimal("-0.31")
    assert "roi_below_target" in result.reason_codes


def test_anchor_trend_target_breakthrough_and_breakdown() -> None:
    breakthrough = evaluate_anchor_trend(
        trend_input(
            current_roi="1.90",
            baseline_roi="1.70",
            current_spend="100",
            baseline_spend="100",
            target_roi="1.81",
        )
    )
    breakdown = evaluate_anchor_trend(
        trend_input(
            current_roi="1.70",
            baseline_roi="1.90",
            current_spend="100",
            baseline_spend="100",
            target_roi="1.81",
        )
    )

    assert breakthrough.trend_type == "rise"
    assert breakthrough.primary_code == "roi_target_breakthrough"
    assert breakdown.trend_type == "fall"
    assert breakdown.primary_code == "roi_target_broken"


def test_anchor_trend_incomplete_sample_is_visible_but_not_ranked() -> None:
    data = trend_input()
    result = evaluate_anchor_trend(
        AnchorTrendInput(
            **{
                **data.__dict__,
                "current_coverage_rate": Decimal("0.70"),
            }
        )
    )

    assert result.trend_type == "insufficient"
    assert result.primary_code == "data_incomplete"


def add_trend_fact(
    session: Session,
    room: Room,
    business_date: date,
    *,
    hour: int,
    anchor: str,
    amount: str,
    spend: str,
) -> None:
    hour_end = datetime.combine(business_date, datetime.min.time()) + timedelta(hours=hour + 1)
    fact = HourlyFact(
        room_id=room.id,
        business_date=business_date,
        year=business_date.year,
        month=business_date.month,
        hour_slot=f"{hour:02d}-{hour + 1:02d}",
        hour_order=hour,
        hour_start_at=hour_end - timedelta(hours=1),
        hour_end_at=hour_end,
        latest_point_id=None,
        latest_observed_at=hour_end,
        actual_anchor_canonical=anchor,
        actual_anchor_base_names=[anchor],
        actual_control_canonical="测试场控",
        planned_anchor_canonical=anchor,
        planned_anchor_base_names=[anchor],
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
    for key, value in {
        "period_spend": spend,
        "period_overall_amount": amount,
        "period_overall_roi": "999",
        "period_overall_orders": "10",
    }.items():
        session.add(
            HourlyMetric(
                hourly_fact_id=fact.id,
                metric_key=key,
                numeric_value=Decimal(value),
                value_source="actual",
                quality_status="valid",
            )
        )


def trend_rule(name: str, *, room_ids: list[str] | None = None) -> HourlyComparisonRule:
    return HourlyComparisonRule(
        name=name,
        rule_type="anchor_trend_summary",
        period_days=3,
        spend_increase_threshold=Decimal("0.30"),
        spend_decrease_threshold=Decimal("-0.30"),
        roi_increase_threshold=Decimal("0.30"),
        roi_decrease_threshold=Decimal("-0.30"),
        minimum_spend=Decimal("1"),
        minimum_orders=1,
        minimum_coverage_rate=Decimal("0.80"),
        minimum_effective_hours=1,
        evaluation_delay_minutes=0,
        push_schedule="daily@09:30",
        applicable_rooms=room_ids or [],
        applicable_anchors=[],
        enabled=True,
        push_enabled=True,
        push_chat_id="oc_authorized_group" if room_ids else None,
        send_rise=True,
        send_fall=True,
        rise_limit=10,
        fall_limit=10,
        send_empty_summary=False,
        allow_force_resend=True,
        cooldown_minutes=0,
        created_by=None,
        updated_by=None,
    )


def test_anchor_trend_service_merges_rankings_deduplicates_and_scopes_rooms() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")
    admin = AccessScope(None, "admin", None, True)
    with Session(engine) as session:
        allowed = Room(
            name="柏瑞美-散粉",
            brand="柏瑞美",
            category="散粉",
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        denied = Room(
            name="柏瑞美-妆前乳",
            brand="柏瑞美",
            category="妆前乳",
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add_all([allowed, denied])
        session.flush()
        session.add_all(
            [
                RoomMetricTarget(
                    room_id=allowed.id,
                    room_name=allowed.name,
                    product_category="散粉",
                    metric_code="period_spend",
                    target_value=Decimal("999"),
                    effective_start_date=None,
                    effective_end_date=None,
                    enabled=True,
                    updated_by=None,
                ),
                RoomMetricTarget(
                    room_id=allowed.id,
                    room_name=allowed.name,
                    product_category="散粉",
                    metric_code="period_overall_roi",
                    target_value=Decimal("1.81"),
                    effective_start_date=None,
                    effective_end_date=None,
                    enabled=True,
                    updated_by=None,
                ),
                RoomMetricTarget(
                    room_id=denied.id,
                    room_name=denied.name,
                    product_category="妆前乳",
                    metric_code="period_overall_roi",
                    target_value=Decimal("1.82"),
                    effective_start_date=None,
                    effective_end_date=None,
                    enabled=True,
                    updated_by=None,
                ),
            ]
        )
        all_rooms_rule = trend_rule("主播3天趋势通知测试")
        allowed_only_rule = trend_rule("散粉群3天趋势通知", room_ids=[str(allowed.id)])
        session.add_all([all_rooms_rule, allowed_only_rule])
        for business_date in (date(2026, 7, 10), date(2026, 7, 11), date(2026, 7, 12)):
            for hour in range(5):
                add_trend_fact(
                    session,
                    allowed,
                    business_date,
                    hour=hour,
                    anchor=f"上涨主播{hour + 1}",
                    amount="150",
                    spend="100",
                )
            for hour in range(5, 8):
                add_trend_fact(
                    session,
                    allowed,
                    business_date,
                    hour=hour,
                    anchor=f"下跌主播{hour - 4}",
                    amount="200",
                    spend="100",
                )
            add_trend_fact(
                session,
                denied,
                business_date,
                hour=8,
                anchor="未授权主播",
                amount="100",
                spend="100",
            )
        for business_date in (date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15)):
            for hour in range(5):
                add_trend_fact(
                    session,
                    allowed,
                    business_date,
                    hour=hour,
                    anchor=f"上涨主播{hour + 1}",
                    amount="195",
                    spend="100",
                )
            for hour in range(5, 8):
                add_trend_fact(
                    session,
                    allowed,
                    business_date,
                    hour=hour,
                    anchor=f"下跌主播{hour - 4}",
                    amount="140",
                    spend="100",
                )
            add_trend_fact(
                session,
                denied,
                business_date,
                hour=8,
                anchor="未授权主播",
                amount="150",
                spend="100",
            )
        session.commit()

        service = AnchorTrendService(
            session,
            catalog,
            admin,
            Settings(
                app_env="test",
                feishu_bot_webhook_url="https://example.test/business-group",
            ),
        )
        result = service.recalculate(
            rule_id=all_rooms_rule.id,
            period_days=3,
            end_date=date(2026, 7, 15),
        )

        assert result["current_period"] == {"start": "2026-07-13", "end": "2026-07-15"}
        assert result["baseline_period"] == {"start": "2026-07-10", "end": "2026-07-12"}
        assert len(result["rise"]) == 6
        assert len(result["fall"]) == 3
        allowed_rise = next(item for item in result["rise"] if item["anchor_name"] == "上涨主播1")
        assert allowed_rise["current_roi"] == "1.95"
        assert allowed_rise["baseline_roi"] == "1.5"
        assert allowed_rise["roi_target"] == "1.81000000"
        assert Decimal(allowed_rise["roi_growth_rate"]) == Decimal("0.30")
        assert allowed_rise["major_rise_hours"]
        assert len(result["event_ids"]) == 2

        events = list(session.scalars(select(AnchorTrendEvent)))
        items = list(session.scalars(select(AnchorTrendItem)))
        assert len(events) == 2
        assert len(items) == 9
        themes = {
            event.notification_type: event.message_snapshot["card"]["header"]["template"]
            for event in events
        }
        assert themes == {
            "anchor_rise_summary": "green",
            "anchor_fall_summary": "red",
        }
        serialized = json.dumps([event.message_snapshot for event in events], ensure_ascii=False)
        assert "主播近期数据上涨榜" in serialized
        assert "主播近期数据下跌预警" in serialized

        repeated = service.recalculate(
            rule_id=all_rooms_rule.id,
            period_days=3,
            end_date=date(2026, 7, 15),
        )
        assert repeated["event_ids"] == result["event_ids"]
        assert len(list(session.scalars(select(AnchorTrendEvent)))) == 2
        assert len(list(session.scalars(select(AnchorTrendItem)))) == 9

        scoped = service.recalculate(
            rule_id=allowed_only_rule.id,
            period_days=3,
            end_date=date(2026, 7, 15),
        )
        assert len(scoped["rise"]) == 5
        assert len(scoped["fall"]) == 3
        assert all(item["room_id"] == str(allowed.id) for item in scoped["rise"] + scoped["fall"])

        viewer_service = AnchorTrendService(
            session,
            catalog,
            AccessScope(None, "viewer", frozenset({allowed.id}), False),
            Settings(app_env="test"),
        )
        visible = viewer_service.list_results(period_days=3, end_date=date(2026, 7, 15))
        assert len(visible["rise"]) == 5
        assert len(visible["fall"]) == 3
        assert visible["events"]
        assert all(event["room_scope"] == [str(allowed.id)] for event in visible["events"])
        assert {
            event["notification_type"]: event["anchor_count"] for event in visible["events"]
        } == {"anchor_rise_summary": 5, "anchor_fall_summary": 3}

        rise_event = next(
            event for event in events if event.notification_type == "anchor_rise_summary"
        )
        visible_details = viewer_service.get_event(rise_event.id)
        assert visible_details["event"]["room_scope"] == [str(allowed.id)]
        assert visible_details["event"]["anchor_count"] == 5
        assert all(item["room_id"] == str(allowed.id) for item in visible_details["items"])


def test_anchor_trend_schedule_due_uses_shanghai_daily_and_monday_windows() -> None:
    assert AnchorTrendService._schedule_due("daily@09:30", datetime(2026, 7, 18, 9, 30))
    assert AnchorTrendService._schedule_due("daily@09:30", datetime(2026, 7, 18, 9, 44))
    assert not AnchorTrendService._schedule_due("daily@09:30", datetime(2026, 7, 18, 9, 45))
    assert AnchorTrendService._schedule_due("weekly:1@09:40", datetime(2026, 7, 20, 9, 40))
    assert not AnchorTrendService._schedule_due("weekly:1@09:40", datetime(2026, 7, 21, 9, 40))
    assert not AnchorTrendService._schedule_due("manual", datetime(2026, 7, 20, 9, 40))
