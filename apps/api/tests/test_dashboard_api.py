from datetime import date, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.router as api_router_module
from app.auth.dependencies import AccessScope, get_access_scope
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import (
    AlertEvent,
    AlertRule,
    HourlyFact,
    HourlyMetric,
    LivePoint,
    LivePointMetric,
    Room,
)

EXPECTED_ANALYSIS_DEFAULT_METRICS = [
    "period_gmv",
    "period_paid_amount",
    "period_order_count",
    "period_avg_order_value",
    "period_buyers",
    "period_viewers",
    "period_view_conversion_rate",
    "period_impression_view_rate",
    "period_view_product_impression_rate",
    "period_product_click_rate",
    "period_click_conversion_rate",
    "period_impression_conversion_rate",
    "period_overall_roi",
    "period_overall_amount",
    "period_overall_orders",
    "period_overall_order_cost",
    "period_net_roi",
    "period_net_amount",
    "period_net_orders",
    "period_net_order_cost",
]


def unrestricted_test_access() -> AccessScope:
    return AccessScope(
        user_id=None,
        role="developer",
        room_ids=None,
        can_export=True,
        export_room_ids=None,
        role_codes=frozenset({"developer"}),
        permission_codes=None,
        scope_label="全部直播间",
    )


def test_overview_rejects_reversed_date_range() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_scope] = unrestricted_test_access
    try:
        response = TestClient(app).get(
            "/api/v1/dashboard/overview",
            params={"start_date": "2026-07-15", "end_date": "2026-07-01"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "日期" in response.json()["detail"]


def test_overview_timeline_and_details_follow_hour_axis_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_router_module,
        "load_runtime_settings",
        lambda _session: Settings(app_env="test", _env_file=None),
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        room = Room(
            name="动态测试直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        observed = datetime.fromisoformat("2026-07-08T09:00:00+08:00")
        point = LivePoint(
            raw_source_record_id=uuid4(),
            room_id=room.id,
            observed_at=observed,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="08-09",
            hour_order=8,
            anchor_raw="Q-李昕",
            anchor_canonical="Q-李昕",
            anchor_base_name="李昕",
            anchor_members=["李昕"],
            anchor_note=None,
            control_raw="郑荣贵",
            control_canonical="郑荣贵",
            control_base_name="郑荣贵",
            auto_check_status="正确",
            valid=True,
            invalid_reason=None,
            raw_payload={"时段": "8:00-9:00"},
        )
        session.add(point)
        session.flush()
        session.add(
            LivePointMetric(
                live_point_id=point.id,
                metric_key="period_overall_roi",
                numeric_value=Decimal("3"),
                raw_value="3",
                parse_status="parsed",
            )
        )
        fact = HourlyFact(
            room_id=room.id,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="08-09",
            hour_order=8,
            hour_start_at=observed - timedelta(hours=1),
            hour_end_at=observed,
            latest_point_id=point.id,
            latest_observed_at=observed,
            actual_anchor_canonical="Q-李昕",
            actual_anchor_base_names=["李昕"],
            actual_control_canonical="郑荣贵",
            planned_anchor_canonical=None,
            planned_anchor_base_names=[],
            anchor_schedule_status=None,
            anchor_match_status="no_schedule",
            control_shift_name=None,
            control_is_scheduled=None,
            control_is_rest=None,
            control_may_be_on_duty=None,
            data_status="complete",
        )
        session.add(fact)
        session.flush()
        for key, value in {
            "period_gmv": "300",
            "period_paid_amount": "300",
            "period_spend": "100",
            "period_overall_amount": "300",
            "period_overall_roi": "3",
            "period_net_amount": "250",
            "period_net_roi": "2.5",
            "period_order_count": "10",
            "period_overall_orders": "10",
            "period_overall_order_cost": "10",
            "period_net_orders": "5",
            "period_net_order_cost": "20",
            "period_viewers": "1000",
            "period_buyers": "8",
            "period_impression_view_rate": "0.25",
        }.items():
            session.add(
                HourlyMetric(
                    hourly_fact_id=fact.id,
                    metric_key=key,
                    numeric_value=Decimal(value),
                    value_source="latest_point",
                    quality_status="valid",
                )
            )
        missing_fact = HourlyFact(
            room_id=room.id,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="09-10",
            hour_order=9,
            hour_start_at=observed,
            hour_end_at=observed + timedelta(hours=1),
            latest_point_id=None,
            latest_observed_at=None,
            actual_anchor_canonical=None,
            actual_anchor_base_names=[],
            actual_control_canonical=None,
            planned_anchor_canonical="Q-李昕",
            planned_anchor_base_names=["李昕"],
            anchor_schedule_status="scheduled",
            anchor_match_status="scheduled_but_missing",
            control_shift_name=None,
            control_is_scheduled=None,
            control_is_rest=None,
            control_may_be_on_duty=None,
            data_status="missing",
        )
        off_air_fact = HourlyFact(
            room_id=room.id,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="10-11",
            hour_order=10,
            hour_start_at=observed + timedelta(hours=1),
            hour_end_at=observed + timedelta(hours=2),
            latest_point_id=None,
            latest_observed_at=None,
            actual_anchor_canonical=None,
            actual_anchor_base_names=[],
            actual_control_canonical=None,
            planned_anchor_canonical=None,
            planned_anchor_base_names=[],
            anchor_schedule_status="off_air",
            anchor_match_status="off_air",
            control_shift_name=None,
            control_is_scheduled=None,
            control_is_rest=None,
            control_may_be_on_duty=None,
            data_status="missing",
        )
        future_missing_fact = HourlyFact(
            room_id=room.id,
            business_date=date(2099, 1, 1),
            year=2099,
            month=1,
            hour_slot="08-09",
            hour_order=8,
            hour_start_at=datetime(2099, 1, 1, 8),
            hour_end_at=datetime(2099, 1, 1, 9),
            latest_point_id=None,
            latest_observed_at=None,
            actual_anchor_canonical=None,
            actual_anchor_base_names=[],
            actual_control_canonical=None,
            planned_anchor_canonical="Q-李昕",
            planned_anchor_base_names=["李昕"],
            anchor_schedule_status="scheduled",
            anchor_match_status="scheduled_but_missing",
            control_shift_name=None,
            control_is_scheduled=None,
            control_is_rest=None,
            control_may_be_on_duty=None,
            data_status="missing",
        )
        rule = AlertRule(
            name="测试数据延迟",
            rule_type="data_delay",
            metric_key=None,
            comparison_type=None,
            operator="<",
            threshold=Decimal("0"),
            min_spend=None,
            min_orders=None,
            min_amount=None,
            room_scope=[],
            anchor_scope=[],
            control_scope=[],
            severity="critical",
            cooldown_minutes=60,
            enabled=True,
            push_enabled=False,
            suggestion_template="",
            created_by=None,
        )
        session.add_all([missing_fact, off_air_fact, future_missing_fact, rule])
        session.flush()
        session.add(
            AlertEvent(
                rule_id=rule.id,
                dedup_key="dashboard-overview-active-alert",
                room_id=room.id,
                business_date=date(2026, 7, 8),
                hour_slot="09-10",
                anchor_name=None,
                control_name=None,
                metric_key=None,
                current_value=None,
                baseline_value=None,
                delta_value=None,
                ratio_percent=None,
                growth_percent=None,
                severity="critical",
                title="数据延迟",
                message="当前小时没有实绩",
                suggestion="检查同步",
                push_status="skipped",
                acknowledged=False,
            )
        )
        session.add(
            AlertEvent(
                rule_id=rule.id,
                dedup_key="dashboard-overview-premature-alert",
                room_id=room.id,
                business_date=date(2099, 1, 1),
                hour_slot="08-09",
                anchor_name="Q-李昕",
                control_name=None,
                metric_key=None,
                current_value=None,
                baseline_value=None,
                delta_value=None,
                ratio_percent=None,
                growth_percent=None,
                severity="critical",
                title="旧版数据延迟误报",
                message="当前小时没有实绩",
                suggestion="检查同步",
                push_status="skipped",
                acknowledged=False,
            )
        )
        session.commit()
        fact_id = fact.id
        point_id = point.id

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_scope] = unrestricted_test_access
    client = TestClient(app)
    try:
        options = client.get("/api/v1/filters/options")
        started = perf_counter()
        overview = client.get(
            "/api/v1/dashboard/overview",
            params={"start_date": "2026-07-08", "end_date": "2026-07-08"},
        )
        future_overview = client.get(
            "/api/v1/dashboard/overview",
            params={"start_date": "2099-01-01", "end_date": "2099-01-01"},
        )
        overview_elapsed = perf_counter() - started
        timeline = client.get(
            "/api/v1/charts/timeline",
            params=[
                ("start_date", "2026-07-08"),
                ("end_date", "2026-07-08"),
                ("metric_keys", "period_overall_roi"),
            ],
        )
        detail = client.get(f"/api/v1/hourly-facts/{fact_id}")
        point_detail = client.get(f"/api/v1/live-points/{point_id}")
        point_timeline = client.get(
            "/api/v1/charts/timeline",
            params={
                "grain": "point",
                "start_date": "2026-07-08",
                "end_date": "2026-07-08",
                "metric_keys": "period_overall_roi",
            },
        )
        member_filtered_point_timeline = client.get(
            "/api/v1/charts/timeline",
            params={
                "grain": "point",
                "start_date": "2026-07-08",
                "end_date": "2026-07-08",
                "metric_keys": "period_overall_roi",
                "anchor_members": "不存在的成员",
            },
        )
        latest_overview = client.get("/api/v1/dashboard/overview")
        anchors = client.get(
            "/api/v1/analytics/anchors/summary",
            params={"start_date": "2026-07-08", "end_date": "2026-07-08"},
        )
        default_anchor_hours = client.get(
            "/api/v1/analytics/anchors/hours",
            params={
                "start_date": "2026-07-08",
                "end_date": "2026-07-08",
                "anchor_names": "Q-李昕",
                "hour_slots": "08-09",
            },
        )
        buyer_only_anchors = client.get(
            "/api/v1/analytics/anchors/summary",
            params=[
                ("start_date", "2026-07-08"),
                ("end_date", "2026-07-08"),
                ("metric_keys", "period_buyers"),
            ],
        )
        buyer_only_anchor_hours = client.get(
            "/api/v1/analytics/anchors/hours",
            params=[
                ("start_date", "2026-07-08"),
                ("end_date", "2026-07-08"),
                ("anchor_names", "Q-李昕"),
                ("hour_slots", "08-09"),
                ("metric_keys", "period_buyers"),
                ("page", "1"),
                ("page_size", "20"),
            ],
        )
        pivot = client.get(
            "/api/v1/pivot/anchor-control",
            params={"start_date": "2026-07-08", "end_date": "2026-07-08"},
        )
        comparison = client.get(
            "/api/v1/comparisons",
            params={"start_date": "2026-07-08", "end_date": "2026-07-08"},
        )
        exported = client.post(
            "/api/v1/exports",
            params={
                "start_date": "2026-07-08",
                "end_date": "2026-07-08",
                "file_format": "xlsx",
            },
        )
        empty_filter_params = [
            ("start_date", "2026-07-08"),
            ("end_date", "2026-07-08"),
            ("anchor_names", "不存在的主播"),
            ("control_names", "不存在的场控"),
            ("hour_slots", "09-10"),
        ]
        filtered_anchors = client.get(
            "/api/v1/analytics/anchors/summary", params=empty_filter_params
        )
        filtered_anchor_hours = client.get(
            "/api/v1/analytics/anchors/hours", params=empty_filter_params
        )
        filtered_controls = client.get(
            "/api/v1/analytics/controls/summary", params=empty_filter_params
        )
        filtered_pairings = client.get("/api/v1/analytics/pairings", params=empty_filter_params)
        filtered_comparison = client.get(
            "/api/v1/comparisons",
            params=[
                *empty_filter_params,
                ("comparison_type", "previous_day"),
                ("metric_keys", "period_overall_roi"),
            ],
        )
        filtered_pivot = client.get("/api/v1/pivot/anchor-control", params=empty_filter_params)
        filtered_export = client.post(
            "/api/v1/exports",
            params=[*empty_filter_params, ("file_format", "csv")],
        )
        alert_evaluation = client.post("/api/v1/alerts/evaluate")
        alert_events = client.get("/api/v1/alerts/events")
        alert_test_push = client.post("/api/v1/alerts/test-push")
    finally:
        app.dependency_overrides.clear()

    assert (
        options.status_code
        == overview.status_code
        == timeline.status_code
        == detail.status_code
        == 200
    )
    assert options.json()["rooms"][0]["name"] == "动态测试直播间"
    assert [
        item["key"] for item in options.json()["metrics"] if item["analysis_default"]
    ] == EXPECTED_ANALYSIS_DEFAULT_METRICS
    overview_kpis = overview.json()["kpis"]
    assert [item["metric_key"] for item in overview_kpis] == [
        "period_overall_amount",
        "period_spend",
        "period_overall_roi",
        "period_net_roi",
        "period_order_count",
        "period_overall_order_cost",
        "period_viewers",
        "period_buyers",
    ]
    assert overview_kpis[0]["name"] == "时段整体成交金额"
    assert overview_kpis[-1]["name"] == "时段成交人数"
    assert Decimal(str(overview_kpis[-1]["value"])) == Decimal("8")
    assert Decimal(overview.json()["data_completeness"]) == Decimal("0.5")
    assert overview.json()["active_alerts"] == 1
    assert future_overview.status_code == 200
    assert future_overview.json()["data_completeness"] is None
    assert future_overview.json()["data_submission_deadline_hour"] == 8
    assert future_overview.json()["active_alerts"] == 0
    assert overview_elapsed < 2.0
    assert timeline.json()["groups"][0]["x_items"][0]["label"] == "08-09\nQ-李昕"
    assert detail.json()["base"]["anchor"] == "Q-李昕"
    assert (
        point_detail.status_code == point_timeline.status_code == latest_overview.status_code == 200
    )
    assert point_detail.json()["raw_payload"]["时段"] == "8:00-9:00"
    assert point_timeline.json()["grain"] == "point"
    assert member_filtered_point_timeline.status_code == 200
    assert member_filtered_point_timeline.json()["groups"] == []
    assert anchors.status_code == pivot.status_code == comparison.status_code == 200
    assert anchors.json()[0]["name"] == "Q-李昕"
    assert anchors.json()[0]["valid_hours"] == 1
    assert Decimal(str(anchors.json()[0]["hourly_average_amount"])) == Decimal("300")
    assert Decimal(str(anchors.json()[0]["period_buyers"])) == Decimal("8")
    assert Decimal(str(anchors.json()[0]["period_impression_view_rate"])) == Decimal("0.25")
    assert "period_spend" not in anchors.json()[0]
    assert default_anchor_hours.status_code == 200
    assert default_anchor_hours.json()["metric_keys"] == EXPECTED_ANALYSIS_DEFAULT_METRICS
    default_anchor_hour = default_anchor_hours.json()["items"][0]
    assert Decimal(str(default_anchor_hour["metrics"]["period_impression_view_rate"])) == Decimal(
        "0.25"
    )
    assert "period_spend" not in default_anchor_hour["metrics"]
    assert buyer_only_anchors.status_code == 200
    assert Decimal(str(buyer_only_anchors.json()[0]["period_buyers"])) == Decimal("8")
    assert Decimal(str(buyer_only_anchors.json()[0]["hourly_average_amount"])) == Decimal("300")
    assert "period_overall_amount" not in buyer_only_anchors.json()[0]
    assert buyer_only_anchor_hours.status_code == 200
    assert buyer_only_anchor_hours.json()["total"] == 1
    assert buyer_only_anchor_hours.json()["page"] == 1
    assert buyer_only_anchor_hours.json()["page_size"] == 20
    assert buyer_only_anchor_hours.json()["metric_keys"] == ["period_buyers"]
    anchor_hour = buyer_only_anchor_hours.json()["items"][0]
    assert anchor_hour["business_date"] == "2026-07-08"
    assert anchor_hour["hour_slot"] == "08-09"
    assert anchor_hour["room_name"] == "动态测试直播间"
    assert anchor_hour["anchor_name"] == "Q-李昕"
    assert anchor_hour["control_name"] == "郑荣贵"
    assert Decimal(str(anchor_hour["metrics"]["period_buyers"])) == Decimal("8")
    assert "period_overall_amount" not in anchor_hour["metrics"]
    assert pivot.json()[0]["children"][0]["level"] == "control"
    assert exported.status_code == 200
    assert exported.content.startswith(b"PK")
    assert filtered_anchors.status_code == filtered_controls.status_code == 200
    assert filtered_pairings.status_code == filtered_comparison.status_code == 200
    assert filtered_pivot.status_code == filtered_export.status_code == 200
    assert filtered_anchors.json() == []
    assert filtered_anchor_hours.status_code == 200
    assert filtered_anchor_hours.json()["total"] == 0
    assert filtered_anchor_hours.json()["items"] == []
    assert filtered_controls.json() == []
    assert filtered_pairings.json() == []
    assert filtered_comparison.json()[0]["current_value"] is None
    assert filtered_pivot.json() == []
    assert len(filtered_export.content.decode("utf-8-sig").splitlines()) == 1
    assert (
        alert_evaluation.status_code
        == alert_events.status_code
        == alert_test_push.status_code
        == 200
    )
    assert alert_test_push.json()["mocked"] is True
