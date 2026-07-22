from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select
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
)
from app.services import alert_service as alert_service_module
from app.services.alert_service import AlertService
from app.services.anchor_trend_service import AnchorTrendService

BASELINE_DATES = (date(2026, 7, 10), date(2026, 7, 11), date(2026, 7, 12))
CURRENT_DATES = (date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15))
END_DATE = CURRENT_DATES[-1]
SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def catalog() -> MetricCatalog:
    return MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")


def settings_without_bot() -> Settings:
    return Settings(
        app_env="test",
        feishu_app_id="",
        feishu_app_secret="",
        feishu_bot_webhook_url="",
        feishu_bot_secret="",
        feishu_bot_chat_id="",
    )


def admin_scope() -> AccessScope:
    return AccessScope(user_id=None, role="admin", room_ids=None, can_export=True)


def add_room(session: Session, name: str) -> Room:
    room = Room(
        name=name,
        brand="测试品牌",
        category="测试品类",
        active=True,
        confirmed=True,
        source_aliases=[],
    )
    session.add(room)
    session.flush()
    return room


def add_rule(
    session: Session,
    name: str,
    *,
    room_ids: tuple[uuid.UUID, ...] = (),
    destination_group: str | None = None,
    minimum_spend: str = "1",
    push_retry_limit: int = 3,
    push_schedule: str = "daily@09:30",
    enabled: bool = True,
    rule_type: str = "anchor_trend_summary",
) -> HourlyComparisonRule:
    rule = HourlyComparisonRule(
        name=name,
        rule_type=rule_type,
        period_days=3,
        spend_increase_threshold=Decimal("0.30"),
        spend_decrease_threshold=Decimal("-0.30"),
        roi_increase_threshold=Decimal("0.30"),
        roi_decrease_threshold=Decimal("-0.30"),
        minimum_spend=Decimal(minimum_spend),
        minimum_orders=1,
        minimum_coverage_rate=Decimal("0.80"),
        minimum_effective_hours=1,
        evaluation_delay_minutes=0,
        push_schedule=push_schedule,
        schedule_timezone="Asia/Shanghai",
        applicable_rooms=[str(room_id) for room_id in room_ids],
        applicable_anchors=[],
        enabled=enabled,
        push_enabled=True,
        push_chat_id=destination_group,
        send_rise=True,
        send_fall=True,
        rise_limit=10,
        fall_limit=10,
        send_empty_summary=False,
        allow_force_resend=True,
        push_retry_limit=push_retry_limit,
        cooldown_minutes=0,
        created_by=None,
        updated_by=None,
    )
    session.add(rule)
    session.flush()
    return rule


def add_fact(
    session: Session,
    room: Room,
    business_date: date,
    *,
    hour: int,
    anchor: str,
    amount: str,
    spend: str,
    orders: str = "10",
) -> HourlyFact:
    hour_start = datetime(
        business_date.year,
        business_date.month,
        business_date.day,
        hour,
        tzinfo=SHANGHAI,
    )
    hour_end = hour_start + timedelta(hours=1)
    fact = HourlyFact(
        room_id=room.id,
        business_date=business_date,
        year=business_date.year,
        month=business_date.month,
        hour_slot=f"{hour:02d}-{hour + 1:02d}",
        hour_order=hour,
        hour_start_at=hour_start,
        hour_end_at=hour_end,
        latest_point_id=None,
        latest_observed_at=hour_end,
        actual_anchor_canonical=anchor,
        actual_anchor_base_names=[anchor],
        actual_control_canonical=f"{anchor}场控",
        planned_anchor_canonical=anchor,
        planned_anchor_base_names=[anchor],
        anchor_schedule_status="scheduled",
        anchor_match_status="matched",
        control_shift_name="测试班次",
        control_is_scheduled=True,
        control_is_rest=False,
        control_may_be_on_duty=True,
        data_status="complete",
    )
    session.add(fact)
    session.flush()
    for metric_key, value in {
        "period_spend": spend,
        "period_overall_amount": amount,
        "period_overall_orders": orders,
        # Deliberately wrong: delivery calculations must recompute ROI from amount/spend.
        "period_overall_roi": "999",
    }.items():
        session.add(
            HourlyMetric(
                hourly_fact_id=fact.id,
                metric_key=metric_key,
                numeric_value=Decimal(value),
                value_source="latest_point",
                quality_status="valid",
            )
        )
    return fact


def add_series(
    session: Session,
    room: Room,
    *,
    hour: int,
    anchor: str,
    baseline_amount: str,
    current_amount: str,
    baseline_spend: str = "100",
    current_spend: str = "100",
) -> list[HourlyFact]:
    facts = [
        add_fact(
            session,
            room,
            business_date,
            hour=hour,
            anchor=anchor,
            amount=baseline_amount,
            spend=baseline_spend,
        )
        for business_date in BASELINE_DATES
    ]
    facts.extend(
        add_fact(
            session,
            room,
            business_date,
            hour=hour,
            anchor=anchor,
            amount=current_amount,
            spend=current_spend,
        )
        for business_date in CURRENT_DATES
    )
    return facts


def service_for(
    session: Session,
    catalog: MetricCatalog,
    access: AccessScope | None = None,
) -> AnchorTrendService:
    return AnchorTrendService(
        session,
        catalog,
        access or admin_scope(),
        settings_without_bot(),
    )


def prepare_rise_event(
    session: Session,
    catalog: MetricCatalog,
    *,
    destination_group: str | None = None,
    push_retry_limit: int = 3,
) -> tuple[AnchorTrendService, HourlyComparisonRule, AnchorTrendEvent]:
    room = add_room(session, f"单榜直播间-{uuid.uuid4()}")
    add_series(
        session,
        room,
        hour=8,
        anchor="上涨主播",
        baseline_amount="100",
        current_amount="130",
    )
    rule = add_rule(
        session,
        f"单榜规则-{uuid.uuid4()}",
        room_ids=(room.id,),
        destination_group=destination_group,
        push_retry_limit=push_retry_limit,
    )
    session.commit()
    service = service_for(session, catalog)
    result = service.recalculate(rule_id=rule.id, period_days=3, end_date=END_DATE)
    event = session.get(AnchorTrendEvent, uuid.UUID(result["event_ids"]["rise"]))
    assert event is not None
    return service, rule, event


def trend_input(
    *,
    current_roi: str = "1.30",
    baseline_roi: str = "1.00",
    current_spend: str = "100",
    baseline_spend: str = "100",
) -> AnchorTrendInput:
    return AnchorTrendInput(
        current_roi=Decimal(current_roi),
        baseline_roi=Decimal(baseline_roi),
        current_spend=Decimal(current_spend),
        baseline_spend=Decimal(baseline_spend),
        current_orders=Decimal("10"),
        baseline_orders=Decimal("10"),
        target_roi=None,
        current_coverage_rate=Decimal("1"),
        baseline_coverage_rate=Decimal("1"),
        current_effective_hours=3,
        baseline_effective_hours=3,
        minimum_spend=Decimal("1"),
        minimum_orders=1,
        minimum_coverage_rate=Decimal("0.80"),
        minimum_effective_hours=1,
    )


@pytest.mark.parametrize(
    ("current_roi", "expected_type", "expected_code"),
    [
        ("1.299999", "neutral", "no_significant_change"),
        ("1.30", "rise", "roi_rise"),
        ("0.700001", "neutral", "no_significant_change"),
        ("0.70", "fall", "roi_fall"),
    ],
)
def test_unrounded_positive_and_negative_thirty_percent_boundaries(
    current_roi: str,
    expected_type: str,
    expected_code: str,
) -> None:
    decision = evaluate_anchor_trend(trend_input(current_roi=current_roi))

    assert decision.trend_type == expected_type
    assert decision.primary_code == expected_code


@pytest.mark.parametrize(
    ("baseline_roi", "baseline_spend"),
    [("0", "100"), ("1", "0")],
)
def test_zero_roi_or_spend_baseline_is_not_comparable(
    baseline_roi: str,
    baseline_spend: str,
) -> None:
    decision = evaluate_anchor_trend(
        trend_input(baseline_roi=baseline_roi, baseline_spend=baseline_spend)
    )

    assert decision.trend_type == "insufficient"
    assert decision.primary_code == "no_comparable_baseline"
    assert decision.roi_growth_rate is None or decision.spend_growth_rate is None


def test_same_period_rules_and_destination_groups_are_isolated_and_recalculation_deduplicates(
    db_session: Session,
    catalog: MetricCatalog,
) -> None:
    room_a = add_room(db_session, "规则隔离直播间A")
    room_b = add_room(db_session, "规则隔离直播间B")
    add_series(
        db_session,
        room_a,
        hour=8,
        anchor="A群主播",
        baseline_amount="100",
        current_amount="130",
    )
    add_series(
        db_session,
        room_b,
        hour=8,
        anchor="B群主播",
        baseline_amount="200",
        current_amount="260",
    )
    rule_a = add_rule(
        db_session,
        "同周期A群规则",
        room_ids=(room_a.id,),
        destination_group="oc_group_a",
    )
    rule_b = add_rule(
        db_session,
        "同周期B群规则",
        room_ids=(room_b.id,),
        destination_group="oc_group_b",
    )
    db_session.commit()
    service = service_for(db_session, catalog)

    first_a = service.recalculate(rule_id=rule_a.id, period_days=3, end_date=END_DATE)
    first_b = service.recalculate(rule_id=rule_b.id, period_days=3, end_date=END_DATE)
    event_a = db_session.get(AnchorTrendEvent, uuid.UUID(first_a["event_ids"]["rise"]))
    event_b = db_session.get(AnchorTrendEvent, uuid.UUID(first_b["event_ids"]["rise"]))
    assert event_a is not None and event_b is not None
    assert event_a.id != event_b.id
    assert event_a.dedup_key != event_b.dedup_key
    assert (event_a.rule_id, event_a.destination_group, event_a.room_scope) == (
        rule_a.id,
        "oc_group_a",
        [str(room_a.id)],
    )
    assert (event_b.rule_id, event_b.destination_group, event_b.room_scope) == (
        rule_b.id,
        "oc_group_b",
        [str(room_b.id)],
    )

    group_a = service.list_results(
        period_days=3,
        end_date=END_DATE,
        destination_group="oc_group_a",
    )
    group_b = service.list_results(
        period_days=3,
        end_date=END_DATE,
        destination_group="oc_group_b",
    )
    assert {item["room_id"] for item in group_a["rise"]} == {str(room_a.id)}
    assert {item["room_id"] for item in group_b["rise"]} == {str(room_b.id)}
    assert {event["destination_group"] for event in group_a["events"]} == {"oc_group_a"}
    assert {event["destination_group"] for event in group_b["events"]} == {"oc_group_b"}

    repeated_a = service.recalculate(rule_id=rule_a.id, period_days=3, end_date=END_DATE)
    repeated_b = service.recalculate(rule_id=rule_b.id, period_days=3, end_date=END_DATE)
    assert repeated_a["event_ids"] == first_a["event_ids"]
    assert repeated_b["event_ids"] == first_b["event_ids"]
    assert db_session.scalar(select(func.count()).select_from(AnchorTrendEvent)) == 2
    assert db_session.scalar(select(func.count()).select_from(AnchorTrendItem)) == 2


@pytest.mark.asyncio
async def test_one_rule_run_sends_at_most_rise_and_fall_cards_and_never_insufficient(
    db_session: Session,
    catalog: MetricCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = add_room(db_session, "两张消息上限直播间")
    add_series(
        db_session,
        room,
        hour=8,
        anchor="边界上涨主播",
        baseline_amount="100",
        current_amount="130",
    )
    add_series(
        db_session,
        room,
        hour=9,
        anchor="边界下跌主播",
        baseline_amount="100",
        current_amount="70",
    )
    add_series(
        db_session,
        room,
        hour=10,
        anchor="样本不足主播",
        baseline_amount="10",
        current_amount="13",
        baseline_spend="10",
        current_spend="10",
    )
    rule = add_rule(
        db_session,
        "两张消息上限规则",
        room_ids=(room.id,),
        destination_group="oc_delivery_group",
        minimum_spend="100",
    )
    db_session.commit()
    send_calls: list[tuple[str, str | None, dict[str, Any]]] = []

    async def fake_send_card(
        _self: AlertService,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        chat_id: str | None = None,
        room_ids: frozenset[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        assert room_ids == frozenset({room.id})
        send_calls.append((idempotency_key, chat_id, payload))
        return {"mocked": False, "transport": "test-double"}

    monkeypatch.setattr(AlertService, "send_card", fake_send_card)
    service = service_for(db_session, catalog)

    result = await service.run_rule(rule, end_date=END_DATE)

    assert set(result["calculation"]["event_ids"]) == {"rise", "fall", "insufficient"}
    assert len(send_calls) == 2
    assert len({call[0] for call in send_calls}) == 2
    assert {call[1] for call in send_calls} == {"oc_delivery_group"}
    assert [item["push_status"] for item in result["sent"]] == ["sent", "sent"]
    events = list(db_session.scalars(select(AnchorTrendEvent)))
    assert {event.notification_type for event in events if event.push_status == "sent"} == {
        "anchor_rise_summary",
        "anchor_fall_summary",
    }
    insufficient = next(
        event for event in events if event.notification_type == "anchor_insufficient_summary"
    )
    assert insufficient.push_status == "skipped"
    assert insufficient.push_attempts == 0
    assert insufficient.message_snapshot == {}
    with pytest.raises(ValueError, match="样本不足"):
        await service.send_event(insufficient.id)
    assert len(send_calls) == 2


@pytest.mark.asyncio
async def test_force_resend_requires_reason_and_creates_a_new_audited_event(
    db_session: Session,
    catalog: MetricCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _rule, source = prepare_rise_event(
        db_session,
        catalog,
        destination_group="oc_force_group",
    )
    provider_calls = 0

    async def fake_send_card(
        _self: AlertService,
        _payload: dict[str, Any],
        *,
        idempotency_key: str,
        chat_id: str | None = None,
        room_ids: frozenset[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        nonlocal provider_calls
        provider_calls += 1
        assert idempotency_key != source.dedup_key
        assert chat_id == "oc_force_group"
        assert room_ids == frozenset(uuid.UUID(value) for value in source.room_scope)
        return {"mocked": False, "transport": "test-double"}

    monkeypatch.setattr(AlertService, "send_card", fake_send_card)
    with pytest.raises(ValueError, match="必须填写原因"):
        await service.force_resend(source.id, reason="   ", operator_id=None)
    assert db_session.scalar(select(func.count()).select_from(AnchorTrendEvent)) == 1

    result = await service.force_resend(
        source.id,
        reason="  群消息丢失，人工复核后重发  ",
        operator_id=None,
    )

    clone = db_session.get(AnchorTrendEvent, uuid.UUID(result["event_id"]))
    assert clone is not None
    assert result["push_status"] == "sent"
    assert provider_calls == 1
    assert clone.id != source.id
    assert clone.dedup_key != source.dedup_key
    assert clone.manual_resend is True
    assert clone.source_event_id == source.id
    assert clone.resend_reason == "群消息丢失，人工复核后重发"
    assert clone.push_status == "sent"
    assert clone.push_attempts == 1
    source_items = list(
        db_session.scalars(select(AnchorTrendItem).where(AnchorTrendItem.event_id == source.id))
    )
    clone_items = list(
        db_session.scalars(select(AnchorTrendItem).where(AnchorTrendItem.event_id == clone.id))
    )
    assert len(source_items) == len(clone_items) == 1
    assert clone_items[0].id != source_items[0].id
    assert clone_items[0].anchor_name == source_items[0].anchor_name


@pytest.mark.asyncio
async def test_destination_group_without_configured_bot_is_skipped_without_transport_attempt(
    db_session: Session,
    catalog: MetricCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _rule, event = prepare_rise_event(
        db_session,
        catalog,
        destination_group="oc_group_without_bot",
    )
    bot_calls: list[tuple[str, str, str]] = []

    class AppBotDouble:
        def __init__(
            self,
            app_id: str,
            app_secret: str,
            chat_id: str,
            **_kwargs: Any,
        ) -> None:
            bot_calls.append((app_id, app_secret, chat_id))

        async def send(
            self,
            _payload: dict[str, Any],
            *,
            idempotency_key: str,
        ) -> dict[str, Any]:
            return {"code": 0, "idempotency_key": idempotency_key}

        async def close(self) -> None:
            return None

    monkeypatch.setattr(alert_service_module, "FeishuAppBotClient", AppBotDouble)

    result = await service.send_event(event.id)

    assert result["push_status"] == "skipped"
    assert bot_calls == []
    db_session.refresh(event)
    assert event.push_status == "skipped"
    assert event.pushed_at is None
    assert "未配置" in (event.push_error or "")


@pytest.mark.asyncio
async def test_failed_delivery_respects_each_rule_retry_limit(
    db_session: Session,
    catalog: MetricCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _rule, event = prepare_rise_event(
        db_session,
        catalog,
        destination_group="oc_retry_group",
        push_retry_limit=2,
    )
    provider_calls = 0

    async def failing_send_card(
        _self: AlertService,
        _payload: dict[str, Any],
        *,
        idempotency_key: str,
        chat_id: str | None = None,
        room_ids: frozenset[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        nonlocal provider_calls
        provider_calls += 1
        assert idempotency_key == event.dedup_key
        assert chat_id == "oc_retry_group"
        assert room_ids == frozenset(uuid.UUID(value) for value in event.room_scope)
        raise RuntimeError("mock delivery outage")

    monkeypatch.setattr(AlertService, "send_card", failing_send_card)

    for expected_attempts in (1, 2):
        with pytest.raises(RuntimeError, match="mock delivery outage"):
            await service.send_event(event.id)
        db_session.refresh(event)
        assert event.push_status == "failed"
        assert event.push_attempts == expected_attempts
        assert event.push_error == "mock delivery outage"

    with pytest.raises(ValueError, match="重试上限"):
        await service.send_event(event.id)
    db_session.refresh(event)
    assert provider_calls == 2
    assert event.push_status == "failed"
    assert event.push_attempts == 2


def test_viewer_scope_cannot_read_unauthorized_room_items_or_live_details(
    db_session: Session,
    catalog: MetricCatalog,
) -> None:
    allowed = add_room(db_session, "已授权趋势直播间")
    denied = add_room(db_session, "未授权趋势直播间")
    add_series(
        db_session,
        allowed,
        hour=8,
        anchor="已授权主播",
        baseline_amount="100",
        current_amount="130",
    )
    denied_facts = add_series(
        db_session,
        denied,
        hour=8,
        anchor="未授权主播",
        baseline_amount="100",
        current_amount="130",
    )
    mixed_rule = add_rule(db_session, "权限混合事件规则")
    denied_rule = add_rule(
        db_session,
        "仅未授权事件规则",
        room_ids=(denied.id,),
    )
    db_session.commit()
    admin_service = service_for(db_session, catalog)
    mixed_result = admin_service.recalculate(
        rule_id=mixed_rule.id,
        period_days=3,
        end_date=END_DATE,
    )
    denied_result = admin_service.recalculate(
        rule_id=denied_rule.id,
        period_days=3,
        end_date=END_DATE,
    )
    viewer = service_for(
        db_session,
        catalog,
        AccessScope(
            user_id=uuid.uuid4(),
            role="viewer",
            room_ids=frozenset({allowed.id}),
            can_export=False,
        ),
    )

    payload = viewer.get_event(uuid.UUID(mixed_result["event_ids"]["rise"]))

    assert {item["room_id"] for item in payload["items"]} == {str(allowed.id)}
    assert len(payload["details"]) == 1
    assert payload["details"][0]["item_id"] == payload["items"][0]["item_id"]
    denied_fact_ids = {str(fact.id) for fact in denied_facts}
    returned_fact_ids = {
        record["fact_id"] for detail in payload["details"] for record in detail["raw_records"]
    }
    assert returned_fact_ids.isdisjoint(denied_fact_ids)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "未授权主播" not in serialized
    assert "未授权趋势直播间" not in serialized

    with pytest.raises(LookupError, match="无权访问"):
        viewer.get_event(uuid.UUID(denied_result["event_ids"]["rise"]))


def test_daily_and_weekly_due_rules_use_shanghai_inclusive_fifteen_minute_windows(
    db_session: Session,
    catalog: MetricCatalog,
) -> None:
    daily = add_rule(db_session, "每日到期规则", push_schedule="daily@09:30")
    weekly = add_rule(db_session, "每周到期规则", push_schedule="weekly:1@09:40")
    add_rule(
        db_session,
        "禁用到期规则",
        push_schedule="daily@09:30",
        enabled=False,
    )
    add_rule(
        db_session,
        "错误类型规则",
        push_schedule="daily@09:30",
        rule_type="hourly_comparison_legacy",
    )
    db_session.commit()
    service = service_for(db_session, catalog)

    def due_at(hour: int, minute: int, *, day: int = 20) -> set[uuid.UUID]:
        # 01:xx UTC is 09:xx Asia/Shanghai.
        return {
            rule.id for rule in service.due_rules(datetime(2026, 7, day, hour, minute, tzinfo=UTC))
        }

    assert due_at(1, 29) == set()
    assert due_at(1, 30) == {daily.id}
    assert due_at(1, 40) == {daily.id, weekly.id}
    assert due_at(1, 44) == {daily.id, weekly.id}
    assert due_at(1, 45) == {weekly.id}
    assert due_at(1, 54) == {weekly.id}
    assert due_at(1, 55) == set()
    assert due_at(1, 40, day=21) == {daily.id}
