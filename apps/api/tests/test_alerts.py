import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.alerts import (
    AlertContext,
    AlertDecision,
    alert_dedup_key,
    comparison_copy,
    evaluate_ratio_rule,
)
from app.integrations.feishu.bot import FeishuAppBotClient, FeishuBotClient
from app.integrations.feishu.client import FeishuError
from app.models.entities import (
    AlertEvent,
    FeishuGroup,
    FeishuGroupRoomScope,
    HourlyFact,
    HourlyMetric,
    Person,
    Room,
    SourceConfig,
    StaffSchedule,
)
from app.services import alert_service as alert_service_module
from app.services.alert_service import AlertService


def context(current: str | None = "3", baseline: str | None = "1.5") -> AlertContext:
    return AlertContext(
        room_id="room-1",
        business_date=date(2026, 7, 8),
        hour_slot="08-09",
        anchor="李晓",
        control="郑荣贵",
        metric_key="period_overall_roi",
        current_value=Decimal(current) if current else None,
        baseline_value=Decimal(baseline) if baseline else None,
        spend=Decimal("100"),
        orders=Decimal("10"),
        amount=Decimal("300"),
    )


def settings_without_bot() -> Settings:
    return Settings(
        app_env="test",
        feishu_app_id="",
        feishu_app_secret="",
        feishu_bot_webhook_url="",
        feishu_bot_secret="",
        feishu_bot_chat_id="",
    )


def test_alert_ratio_threshold_and_zero_baseline() -> None:
    decision = evaluate_ratio_rule(context(), operator=">=", threshold=Decimal("1.5"))
    assert decision.triggered
    assert decision.ratio_percent == Decimal("200")
    assert decision.growth_percent == Decimal("100")
    assert not evaluate_ratio_rule(
        context(baseline="0"), operator=">=", threshold=Decimal("1.5")
    ).triggered


def test_alert_dedup_key_and_copy_are_stable() -> None:
    arguments = ("room-1", date(2026, 7, 8), "08-09", "李晓", "郑荣贵", "roi", "roi_surge")
    assert alert_dedup_key(*arguments) == alert_dedup_key(*arguments)
    assert (
        comparison_copy("ROI", Decimal("3"), Decimal("1.5"), Decimal("200"), Decimal("100"))
        == "当前ROI3，基准1.5；当前值是基准值的200%，较基准提升100%。"
    )


def add_fact(session: Session, room: Room, day: int, roi: str, spend: str) -> HourlyFact:
    end = datetime(2026, 7, day, 9)
    fact = HourlyFact(
        room_id=room.id,
        business_date=date(2026, 7, day),
        year=2026,
        month=7,
        hour_slot="08-09",
        hour_order=8,
        hour_start_at=end - timedelta(hours=1),
        hour_end_at=end,
        latest_point_id=None,
        latest_observed_at=end,
        actual_anchor_canonical="李晓",
        actual_anchor_base_names=["李晓"],
        actual_control_canonical="郑荣贵",
        planned_anchor_canonical="李晓",
        planned_anchor_base_names=["李晓"],
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
        "period_overall_roi": roi,
        "period_spend": spend,
        "period_overall_orders": "10",
        "period_overall_amount": "300",
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
    return fact


def test_alert_service_deduplicates_and_acknowledges() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
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
        add_fact(session, room, 7, "1.5", "100")
        add_fact(session, room, 8, "3", "100")
        session.commit()
        service = AlertService(session, Settings(app_env="test"))
        assert service.evaluate_all() == 1
        assert service.evaluate_all() == 0
        event = session.scalar(select(AlertEvent))
        assert event is not None
        assert len(service.list_events()) == 1
        assert len(service.list_rules()) == 5
        service.acknowledge(event.id, "已复核投放", None)
        assert service.get_event(event.id)["acknowledged"] is True
        with pytest.raises(LookupError):
            AlertService(session, Settings(app_env="test"), frozenset({uuid4()})).get_event(
                event.id
            )
        service.delete_rule(event.rule_id)
        assert session.get(event.__class__, event.id) is not None
    engine.dispose()


@pytest.mark.asyncio
async def test_send_card_denies_unknown_destination_without_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider_calls = 0

    class AppBotDouble:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def send(
            self,
            _payload: dict[str, object],
            *,
            idempotency_key: str,
        ) -> dict[str, object]:
            nonlocal provider_calls
            provider_calls += 1
            return {"code": 0, "idempotency_key": idempotency_key}

        async def close(self) -> None:
            return None

    monkeypatch.setattr(alert_service_module, "FeishuAppBotClient", AppBotDouble)
    with Session(engine) as session:
        room = Room(
            name="未授权目标测试直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.commit()
        service = AlertService(
            session,
            Settings(
                app_env="test",
                feishu_app_id="cli_test",
                feishu_app_secret="secret",  # noqa: S106
            ),
        )

        with pytest.raises(ValueError, match="未注册或已禁用"):
            await service.send_card(
                {"msg_type": "interactive", "card": {}},
                idempotency_key="unknown-destination",
                chat_id="oc_unknown_group",
                room_ids=frozenset({room.id}),
            )

        assert provider_calls == 0
    engine.dispose()


@pytest.mark.asyncio
async def test_send_card_allows_registered_destination_with_exact_room_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider_calls = 0

    class AppBotDouble:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def send(
            self,
            _payload: dict[str, object],
            *,
            idempotency_key: str,
        ) -> dict[str, object]:
            nonlocal provider_calls
            provider_calls += 1
            return {"code": 0, "idempotency_key": idempotency_key}

        async def close(self) -> None:
            return None

    monkeypatch.setattr(alert_service_module, "FeishuAppBotClient", AppBotDouble)
    with Session(engine) as session:
        room = Room(
            name="已授权目标测试直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        group = FeishuGroup(
            name="已授权测试群",
            chat_id="oc_authorized_group",
            all_rooms=False,
            enabled=True,
        )
        session.add_all([room, group])
        session.flush()
        session.add(FeishuGroupRoomScope(group_id=group.id, room_id=room.id))
        session.commit()
        service = AlertService(
            session,
            Settings(
                app_env="test",
                feishu_app_id="cli_test",
                feishu_app_secret="secret",  # noqa: S106
            ),
        )

        result = await service.send_card(
            {"msg_type": "interactive", "card": {}},
            idempotency_key="authorized-destination",
            chat_id=group.chat_id,
            room_ids=frozenset({room.id}),
        )

        assert result["mocked"] is False
        assert result["transport"] == "app_bot"
        assert provider_calls == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_evaluation_auto_pushes_and_failed_event_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    calls = 0

    class Bot:
        build_card = staticmethod(FeishuBotClient.build_card)

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def send(self, _payload: dict[str, object]) -> dict[str, int]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise FeishuError("temporary test failure")
            return {"code": 0}

        async def close(self) -> None:
            return None

    monkeypatch.setattr(alert_service_module, "FeishuBotClient", Bot)
    with Session(engine) as session:
        room = Room(
            name="自动推送直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        group = FeishuGroup(
            name="自动推送测试群",
            chat_id="oc_alert_retry_group",
            all_rooms=False,
            enabled=True,
        )
        session.add(group)
        session.flush()
        session.add(FeishuGroupRoomScope(group_id=group.id, room_id=room.id))
        add_fact(session, room, 7, "1.5", "100")
        add_fact(session, room, 8, "3", "100")
        session.commit()
        service = AlertService(
            session,
            Settings(
                app_env="test",
                feishu_bot_webhook_url="https://example.test/hook",
                feishu_bot_chat_id=group.chat_id,
            ),
        )
        monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 7, 9, 8, 5))
        first = await service.evaluate_recent_and_push()
        assert first == {
            "recovered": 0,
            "created": 1,
            "queued": 1,
            "sent": 0,
            "failed": 1,
            "skipped": 0,
        }
        event = session.scalar(select(AlertEvent))
        assert event is not None
        assert event.push_status == "failed"
        assert event.push_attempts == 1

        retry = await service.push_queued_events()
        assert retry == {"queued": 1, "sent": 1, "failed": 0, "skipped": 0}
        session.refresh(event)
        assert event.push_status == "sent"
        assert event.push_attempts == 2
        assert event.message == "当前ROI3，基准1.5；当前值是基准值的200%，较基准提升100%。"

        repeated = await service.evaluate_recent_and_push()
        assert repeated == {
            "recovered": 0,
            "created": 0,
            "queued": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
        }


@pytest.mark.asyncio
async def test_recent_evaluation_does_not_backfill_old_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="历史预警保护直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        add_fact(session, room, 7, "1.5", "100")
        add_fact(session, room, 8, "3", "100")
        session.commit()
        service = AlertService(session, Settings(app_env="test"))
        monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 7, 10, 9, 30))
        result = await service.evaluate_recent_and_push()
        assert result == {
            "recovered": 0,
            "created": 0,
            "queued": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
        }
        assert session.scalar(select(AlertEvent)) is None


@pytest.mark.asyncio
async def test_late_actual_recovery_rechecks_roi_even_outside_recent_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="晚到实绩直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        add_fact(session, room, 7, "2", "100")
        end = datetime(2026, 7, 8, 9)
        late_fact = HourlyFact(
            room_id=room.id,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="08-09",
            hour_order=8,
            hour_start_at=end - timedelta(hours=1),
            hour_end_at=end,
            latest_point_id=None,
            latest_observed_at=None,
            actual_anchor_canonical=None,
            actual_anchor_base_names=[],
            actual_control_canonical=None,
            planned_anchor_canonical="李晓",
            planned_anchor_base_names=["李晓"],
            anchor_schedule_status="scheduled",
            anchor_match_status="scheduled_but_missing",
            control_shift_name="早班",
            control_is_scheduled=True,
            control_is_rest=False,
            control_may_be_on_duty=True,
            data_status="missing",
        )
        session.add(late_fact)
        session.commit()

        service = AlertService(session, settings_without_bot())
        assert service.evaluate_all() == 1

        late_fact.data_status = "complete"
        late_fact.latest_observed_at = end
        late_fact.actual_anchor_canonical = "李晓"
        late_fact.actual_anchor_base_names = ["李晓"]
        late_fact.actual_control_canonical = "郑荣贵"
        late_fact.anchor_match_status = "matched"
        for key, value in {
            "period_overall_roi": "1.3",
            "period_spend": "100",
            "period_overall_orders": "10",
            "period_overall_amount": "300",
        }.items():
            session.add(
                HourlyMetric(
                    hourly_fact_id=late_fact.id,
                    metric_key=key,
                    numeric_value=Decimal(value),
                    value_source="actual",
                    quality_status="valid",
                )
            )
        session.commit()

        monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 7, 10, 9, 30))
        result = await service.evaluate_recent_and_push()
        assert result == {
            "recovered": 1,
            "created": 1,
            "queued": 1,
            "sent": 0,
            "failed": 0,
            "skipped": 1,
        }
        active_events = list(
            session.scalars(select(AlertEvent).where(AlertEvent.acknowledged.is_(False)))
        )
        assert len(active_events) == 1
        assert active_events[0].message == (
            "当前ROI1.3，基准2；当前值是基准值的65%，较基准下降35%。"
        )
        card_text = json.dumps(service._event_card(active_events[0]), ensure_ascii=False)
        assert "**当前 ROI：** 1.30" in card_text
        assert "**对比基准（昨日同小时）：** 2.00" in card_text
        assert "**ROI 下降值：** 0.70" in card_text
        assert "**ROI 跌幅：** 35.00%" in card_text


def test_roi_floor_alert_includes_drop_amount_and_percentage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="ROI 底线直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        add_fact(session, room, 7, "2", "100")
        add_fact(session, room, 8, "1.1", "100")
        session.commit()

        service = AlertService(session, Settings(app_env="test"))
        assert service.evaluate_all() == 2
        floor_event = next(
            event for event in session.scalars(select(AlertEvent)) if "ROI 低于底线" in event.title
        )
        assert floor_event.delta_value == Decimal("-0.9")
        assert floor_event.ratio_percent == Decimal("55")
        assert floor_event.growth_percent == Decimal("-45")
        assert floor_event.message == ("当前ROI1.1，基准2；当前值是基准值的55%，较基准下降45%。")
        payload = service.get_event(floor_event.id)
        assert payload["delta_value"] == Decimal("-0.9")
        assert payload["ratio_percent"] == Decimal("55")
        assert payload["growth_percent"] == Decimal("-45")
        card_text = json.dumps(service._event_card(floor_event), ensure_ascii=False)
        assert "**ROI 下降值：** 0.90" in card_text
        assert "**ROI 跌幅：** 45.00%" in card_text


@pytest.mark.asyncio
async def test_data_delay_waits_until_t_plus_one_deadline_without_faking_roi_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="延迟基准直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        add_fact(session, room, 7, "2.17", "100")
        end = datetime(2026, 7, 8, 9)
        missing_fact = HourlyFact(
            room_id=room.id,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="08-09",
            hour_order=8,
            hour_start_at=end - timedelta(hours=1),
            hour_end_at=end,
            latest_point_id=None,
            latest_observed_at=None,
            actual_anchor_canonical=None,
            actual_anchor_base_names=[],
            actual_control_canonical=None,
            planned_anchor_canonical="李晓",
            planned_anchor_base_names=["李晓"],
            anchor_schedule_status="scheduled",
            anchor_match_status="scheduled_but_missing",
            control_shift_name="早班",
            control_is_scheduled=True,
            control_is_rest=False,
            control_may_be_on_duty=True,
            data_status="missing",
        )
        session.add(missing_fact)
        session.commit()

        service = AlertService(
            session,
            Settings(
                app_env="test",
                feishu_bot_webhook_url="https://example.test/business-group",
            ),
        )
        monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 7, 9, 7, 59))
        assert service.evaluate_all() == 0

        monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 7, 9, 8, 0))
        assert service.evaluate_all() == 1
        event = session.scalar(select(AlertEvent))
        assert event is not None
        data_delay_rule = next(
            rule for rule in service.ensure_default_rules() if rule.rule_type == "data_delay"
        )
        assert data_delay_rule.push_enabled is False
        assert event.push_status == "skipped"
        assert event.push_error == "数据质量事件仅系统记录，业务群推送已关闭"
        assert event.current_value is None
        assert event.baseline_value == Decimal("2.17")
        assert event.delta_value is None
        assert event.growth_percent is None
        assert event.message == (
            "截至次日08:00当前小时实绩仍未补录，ROI跌幅暂无法计算；昨日同小时 ROI 2.17。"
        )

        # Simulate an alert created by the older version and verify the normal
        # reconciliation pass enriches it without treating it as recovered.
        event.baseline_value = None
        event.message = "排班时段结束后仍无有效实绩"
        session.commit()
        assert service.reconcile_recovered_data_delays() == 0
        session.refresh(event)
        assert event.baseline_value == Decimal("2.17")
        assert event.message == (
            "截至次日08:00当前小时实绩仍未补录，ROI跌幅暂无法计算；昨日同小时 ROI 2.17。"
        )

        card_text = json.dumps(service._event_card(event), ensure_ascii=False)
        assert "**当前 ROI：** 暂无（超过T+1填报截止仍未补录）" in card_text
        assert "**对比基准（昨日同小时）：** 2.17" in card_text
        assert "**ROI 跌幅：** 暂无法计算（不能将缺失值按 0 计算）" in card_text
        assert "100.00%" not in card_text

        event.push_status = "pending"
        event.push_error = None
        session.commit()
        with pytest.raises(ValueError, match="数据质量事件"):
            await service.push_event(event.id)
        session.refresh(event)
        assert event.push_status == "skipped"
        assert event.push_error == "数据质量事件仅系统记录，业务群推送已关闭"


def test_legacy_data_delay_before_t_plus_one_deadline_is_auto_withdrawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="历史误报直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        fact = add_fact(session, room, 8, "1", "100")
        fact.data_status = "missing"
        fact.anchor_schedule_status = "scheduled"
        service = AlertService(session, Settings(app_env="test"))
        delay_rule = next(
            rule for rule in service.ensure_default_rules() if rule.rule_type == "data_delay"
        )
        event = service._create_event(
            fact,
            delay_rule,
            AlertDecision(True, reason="旧版本误报"),
            None,
            None,
        )
        assert event is not None
        session.commit()

        monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 7, 9, 7, 59))
        assert service.reconcile_recovered_data_delays() == 0
        session.refresh(event)
        assert event.acknowledged is True
        assert event.resolution_note == "尚未到T+1补录截止时间，系统自动撤销误报"


def test_data_delay_uses_schedule_names_and_auto_recovers() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="柏瑞美-散粉",
            brand="柏瑞美",
            category="散粉",
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        source = SourceConfig(
            name="场控排班",
            source_type="feishu_bitable",
            source_role="staff_schedule",
            app_token="schedule-app",  # noqa: S106
            table_id="staff-table",
            view_id=None,
            default_room_name=None,
            schedule_year=2026,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        controller = Person(
            display_name="@陈铭玉",
            base_name="陈铭玉",
            prefix=None,
            primary_role="场控",
            employment_status="在职",
            active=True,
            notes=None,
        )
        session.add_all([room, source, controller])
        session.flush()
        end = datetime(2026, 7, 14, 19)
        fact = HourlyFact(
            room_id=room.id,
            business_date=date(2026, 7, 14),
            year=2026,
            month=7,
            hour_slot="18-19",
            hour_order=18,
            hour_start_at=end - timedelta(hours=1),
            hour_end_at=end,
            latest_point_id=None,
            latest_observed_at=None,
            actual_anchor_canonical=None,
            actual_anchor_base_names=[],
            actual_control_canonical=None,
            planned_anchor_canonical="Q-陈莹",
            planned_anchor_base_names=["陈莹"],
            anchor_schedule_status="scheduled",
            anchor_match_status="scheduled_but_missing",
            control_shift_name=None,
            control_is_scheduled=None,
            control_is_rest=None,
            control_may_be_on_duty=None,
            data_status="missing",
        )
        shift = StaffSchedule(
            source_config_id=source.id,
            source_record_id="staff-1",
            person_id=controller.id,
            schedule_date=date(2026, 7, 14),
            role="场控",
            employment_status="在职",
            shift_raw="12-20",
            shift_name="12-20",
            shift_start=datetime.strptime("12:00", "%H:%M").time(),
            shift_end=datetime.strptime("20:00", "%H:%M").time(),
            crosses_midnight=False,
            is_rest=False,
            time_configured=True,
        )
        session.add_all([fact, shift])
        session.commit()

        service = AlertService(session, Settings(app_env="test"))
        assert service.evaluate_all() == 1
        event = session.scalar(select(AlertEvent))
        assert event is not None
        assert (event.anchor_name, event.control_name) == ("Q-陈莹", "陈铭玉")
        card_text = json.dumps(service._event_card(event), ensure_ascii=False)
        assert "直播间：** 柏瑞美-散粉" in card_text
        assert "计划主播：** Q-陈莹" in card_text
        assert "排班场控：** 陈铭玉" in card_text
        assert "直播间 ID" not in card_text

        event.anchor_name = None
        event.control_name = None
        fact.data_status = "complete"
        fact.actual_anchor_canonical = "Q-陈莹"
        fact.actual_control_canonical = "陈铭玉"
        session.commit()
        assert service.reconcile_recovered_data_delays() == 1
        session.refresh(event)
        assert (event.anchor_name, event.control_name) == ("Q-陈莹", "陈铭玉")
        assert event.acknowledged is True
        assert event.resolution_note == "实绩已补录，系统自动恢复"


def test_alert_rule_crud_and_non_ratio_decisions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="规则测试直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        fact = add_fact(session, room, 8, "1", "100")
        session.commit()
        service = AlertService(session, Settings(app_env="test"))
        rules = service.ensure_default_rules()
        by_type = {rule.rule_type: rule for rule in rules}
        assert by_type["data_delay"].operator == ">="
        assert by_type["data_delay"].threshold == Decimal("8")
        fact.data_status = "missing"
        fact.anchor_schedule_status = "scheduled"
        decision, _, _ = service._decision(fact, by_type["data_delay"], {}, {})
        assert decision.triggered
        fact.data_status = "complete"
        fact.anchor_match_status = "mismatched"
        decision, _, _ = service._decision(fact, by_type["anchor_mismatch"], {}, {})
        assert decision.triggered
        metric_map = {
            (fact.id, "period_overall_roi"): Decimal("1"),
            (fact.id, "period_spend"): Decimal("100"),
        }
        decision, current, _ = service._decision(fact, by_type["roi_floor"], metric_map, {})
        assert decision.triggered and current == Decimal("1")
        payload = {
            "name": "自定义 ROI 底线",
            "rule_type": "roi_floor_custom",
            "metric_key": "period_overall_roi",
            "comparison_type": None,
            "operator": "<",
            "threshold": Decimal("1.1"),
            "min_spend": Decimal("50"),
            "min_orders": None,
            "min_amount": None,
            "room_scope": [],
            "anchor_scope": [],
            "control_scope": [],
            "severity": "warning",
            "cooldown_minutes": 30,
            "enabled": True,
            "push_enabled": False,
            "suggestion_template": "检查投放",
        }
        created = service.create_rule(payload, None)
        rule_id = created["id"]
        updated = service.update_rule(rule_id, {**payload, "name": "已更新规则"})
        assert updated["name"] == "已更新规则"
        service.delete_rule(rule_id)
        with pytest.raises(LookupError):
            service.update_rule(rule_id, payload)


@pytest.mark.asyncio
async def test_feishu_bot_retries_and_signs() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"code": 1})
        return httpx.Response(200, json={"code": 0})

    async def no_sleep(_: float) -> None:
        return None

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FeishuBotClient(
        "https://example.test/hook", "secret", http_client=http, sleep=no_sleep
    )
    result = await client.send(client.build_card("测试", ["结果"], {}))
    assert result["code"] == 0
    assert calls == 2
    assert (
        FeishuBotClient.signature(123, "secret") == "/1VVdZH3KitTHu9FiYl+TZ0EGq/rppGGi7XFsB5aJSA="
    )
    await client.close()


@pytest.mark.asyncio
async def test_feishu_app_bot_sends_idempotent_card_to_chat() -> None:
    message_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal message_calls
        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "tenant-token"})
        assert request.url.path.endswith("/im/v1/messages")
        assert request.url.params["receive_id_type"] == "chat_id"
        assert request.headers["Authorization"] == "Bearer tenant-token"
        body = json.loads(request.content)
        assert body["receive_id"] == "oc_test"
        assert body["msg_type"] == "interactive"
        assert body["uuid"] == "event-id"
        assert json.loads(body["content"])["header"]["template"] == "red"
        message_calls += 1
        if message_calls == 1:
            return httpx.Response(500, json={"code": 1})
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_test"}})

    async def no_sleep(_: float) -> None:
        return None

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FeishuAppBotClient(
        "cli_test",
        "app-secret",
        "oc_test",
        http_client=http,
        max_attempts=2,
        sleep=no_sleep,
    )
    payload = FeishuBotClient.build_card("测试", ["结果"], {})
    result = await client.send(payload, idempotency_key="event-id")
    assert result["code"] == 0
    assert message_calls == 2
    await client.close()


@pytest.mark.asyncio
async def test_alert_mock_push_and_missing_event() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="Mock 推送直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        add_fact(session, room, 7, "1.5", "100")
        add_fact(session, room, 8, "3", "100")
        session.commit()
        service = AlertService(session, settings_without_bot())
        assert service.evaluate_all() == 1
        event = session.scalar(select(AlertEvent))
        assert event is not None
        event.push_status = "pending"
        session.commit()
        result = await service.push_event(event.id)
        assert result["mocked"] is True
        with pytest.raises(LookupError):
            await service.push_event(uuid4())


@pytest.mark.asyncio
async def test_sent_alert_cannot_be_pushed_again() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="重推保护直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        add_fact(session, room, 7, "1.5", "100")
        add_fact(session, room, 8, "3", "100")
        session.commit()
        service = AlertService(session, Settings(app_env="test"))
        assert service.evaluate_all() == 1
        event = session.scalar(select(AlertEvent))
        assert event is not None
        event.push_status = "sent"
        session.commit()

        with pytest.raises(ValueError, match="已发送"):
            await service.push_event(event.id)
