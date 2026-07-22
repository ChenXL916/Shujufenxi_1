from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AccessScope, get_access_scope
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import HourlyFact, HourlyMetric, Room, RoomMetricTarget
from app.services import hourly_comparison_service as hourly_comparison_module
from app.services.hourly_comparison_service import HourlyComparisonService


def add_hour(
    session: Session,
    room: Room,
    business_date: date,
    *,
    amount: str,
    spend: str,
    buyers: str = "2",
    viewers: str = "10",
    hour: int = 8,
) -> None:
    end = datetime.combine(business_date, datetime.min.time()) + timedelta(hours=hour + 1)
    fact = HourlyFact(
        room_id=room.id,
        business_date=business_date,
        year=business_date.year,
        month=business_date.month,
        hour_slot=f"{hour:02d}-{hour + 1:02d}",
        hour_order=hour,
        hour_start_at=end - timedelta(hours=1),
        hour_end_at=end,
        latest_point_id=None,
        latest_observed_at=end,
        actual_anchor_canonical="Q-测试主播",
        actual_anchor_base_names=["测试主播"],
        actual_control_canonical="测试场控",
        planned_anchor_canonical="Q-测试主播",
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
        "period_order_count": Decimal("10"),
        "period_buyers": Decimal(buyers),
        "period_viewers": Decimal(viewers),
        "period_gmv": Decimal(amount),
        "period_net_amount": Decimal(amount) - Decimal("10"),
    }
    for metric_key, numeric_value in values.items():
        session.add(
            HourlyMetric(
                hourly_fact_id=fact.id,
                metric_key=metric_key,
                numeric_value=numeric_value,
                value_source="latest_point",
                quality_status="valid",
            )
        )


def add_unassigned_hour(
    session: Session, room: Room, business_date: date, *, hour: int = 8
) -> None:
    end = datetime.combine(business_date, datetime.min.time()) + timedelta(hours=hour + 1)
    session.add(
        HourlyFact(
            room_id=room.id,
            business_date=business_date,
            year=business_date.year,
            month=business_date.month,
            hour_slot=f"{hour:02d}-{hour + 1:02d}",
            hour_order=hour,
            hour_start_at=end - timedelta(hours=1),
            hour_end_at=end,
            latest_point_id=None,
            latest_observed_at=None,
            actual_anchor_canonical=None,
            actual_anchor_base_names=[],
            actual_control_canonical=None,
            planned_anchor_canonical=None,
            planned_anchor_base_names=[],
            anchor_schedule_status="unassigned",
            anchor_match_status="no_schedule",
            control_shift_name=None,
            control_is_scheduled=None,
            control_is_rest=None,
            control_may_be_on_duty=None,
            data_status="missing",
        )
    )


def build_client() -> tuple[TestClient, UUID, UUID]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
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
        unassigned = Room(
            name="未排班直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add_all([allowed, denied, unassigned])
        session.flush()
        session.add_all(
            [
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
        for day, amount, spend, buyers, viewers in (
            (10, "140", "100", "1", "10"),
            (11, "280", "200", "9", "30"),
            (12, "70", "50", "2", "20"),
            (13, "165", "100", "1", "10"),
            (14, "410", "200", "9", "30"),
            (15, "95", "50", "3", "10"),
        ):
            add_hour(
                session,
                allowed,
                date(2026, 7, day),
                amount=amount,
                spend=spend,
                buyers=buyers,
                viewers=viewers,
            )
            add_hour(session, denied, date(2026, 7, day), amount="182", spend="100")
            add_unassigned_hour(session, unassigned, date(2026, 7, day))
        session.commit()
        allowed_id = allowed.id
        denied_id = denied.id

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_scope] = lambda: AccessScope(
        user_id=None,
        role="developer",
        role_codes=frozenset({"developer"}),
        permission_codes=None,
        room_ids=None,
        export_room_ids=None,
        can_export=True,
        scope_label="全部直播间",
    )
    return TestClient(app), allowed_id, denied_id


def test_hourly_comparison_returns_fixed_24_hours_and_recomputed_roi() -> None:
    client, allowed_id, _ = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(allowed_id),
                "series_dimension": "room",
            },
        )
        daily_average = client.get(
            "/api/v1/overview/hourly-comparison",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(allowed_id),
                "series_dimension": "room",
                "aggregation_mode": "daily_average",
            },
        )
        no_comparison = client.get(
            "/api/v1/overview/hourly-comparison",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(allowed_id),
                "compare_enabled": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == daily_average.status_code == no_comparison.status_code == 200
    payload = response.json()
    assert payload["current_period"] == {
        "start": "2026-07-13",
        "end": "2026-07-15",
        "days": 3,
        "complete": True,
    }
    assert payload["comparison_period"]["start"] == "2026-07-10"
    assert len(payload["hours"]) == 24
    assert payload["hours"][0]["key"] == "00-01"
    assert payload["hours"][-1] == {
        "key": "23-24",
        "label": "23:00-24:00",
        "sort": 23,
    }
    assert len(payload["series"]) == 1
    points = payload["series"][0]["points"]
    assert len(points) == 24
    assert points[0]["current"]["roi"] is None
    eight = points[8]
    assert Decimal(str(eight["current"]["roi"])) == Decimal("670") / Decimal("350")
    assert Decimal(str(eight["current"]["spend"])) == Decimal("350")
    assert Decimal(str(eight["comparison"]["roi"])) == Decimal("1.4")
    roi_ohlc = eight["current"]["roi_ohlc"]
    for field, expected in {
        "open": "1.65",
        "close": "1.9",
        "high": "2.05",
        "low": "1.65",
        "average": str(Decimal("5.6") / Decimal("3")),
        "median": "1.9",
        "total": "5.6",
    }.items():
        assert Decimal(str(roi_ohlc[field])) == Decimal(expected)
    assert roi_ohlc["effective_days"] == 3
    assert roi_ohlc["first_date"] == "2026-07-13"
    assert roi_ohlc["last_date"] == "2026-07-15"
    assert roi_ohlc["high_date"] == "2026-07-14"
    assert roi_ohlc["low_date"] == "2026-07-13"
    assert Decimal(str(eight["roi_target"])) == Decimal("1.81")
    assert eight["status"]["code"] == "roi_excellent_growth"
    assert Decimal(str(eight["current"]["coverage_rate"])) == Decimal("1")
    assert Decimal(str(daily_average.json()["series"][0]["points"][8]["current"]["spend"])) == (
        Decimal("350") / Decimal("3")
    )
    assert no_comparison.json()["comparison_period"] is None
    assert no_comparison.json()["series"][0]["points"][8]["comparison"] is None


def test_hourly_comparison_returns_view_conversion_ratio_of_sums() -> None:
    client, allowed_id, _ = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(allowed_id),
                "metric_ids": "period_view_conversion_rate",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert "period_view_conversion_rate" in {item["key"] for item in payload["metrics"]}
    point = payload["series"][0]["points"][8]
    assert Decimal(str(point["current"]["metrics"]["period_view_conversion_rate"])) == (
        Decimal("13") / Decimal("50")
    )
    assert Decimal(str(point["comparison"]["metrics"]["period_view_conversion_rate"])) == (
        Decimal("12") / Decimal("60")
    )


def test_room_anchor_dimension_never_merges_same_anchor_across_rooms() -> None:
    client, allowed_id, denied_id = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "series_dimension": "room_anchor",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    series_by_room = {item["room_id"]: item for item in response.json()["series"]}
    assert set(series_by_room) == {str(allowed_id), str(denied_id)}
    assert {item["anchor_name"] for item in series_by_room.values()} == {"Q-测试主播"}
    allowed_point = series_by_room[str(allowed_id)]["points"][8]
    denied_point = series_by_room[str(denied_id)]["points"][8]
    assert Decimal(str(allowed_point["current"]["roi"])) == Decimal("670") / Decimal("350")
    assert Decimal(str(denied_point["current"]["roi"])) == Decimal("1.82")
    assert Decimal(str(allowed_point["roi_target"])) == Decimal("1.81")
    assert Decimal(str(denied_point["roi_target"])) == Decimal("1.82")


def test_hourly_comparison_excludes_unassigned_facts_from_coverage_denominator() -> None:
    client, _, _ = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "series_dimension": "summary",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    point = response.json()["series"][0]["points"][8]["current"]
    assert point["effective_samples"] == 6
    assert point["expected_samples"] == 6
    assert Decimal(str(point["coverage_rate"])) == Decimal("1")


def test_hourly_comparison_rejects_unknown_metric_id() -> None:
    client, _, _ = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params={"metric_ids": "unknown_metric"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "unknown_metric" in response.json()["detail"]


def test_hourly_comparison_rejects_more_than_four_visible_metrics() -> None:
    client, _, _ = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params=[
                ("metric_ids", "period_overall_roi"),
                ("metric_ids", "period_spend"),
                ("metric_ids", "period_order_count"),
                ("metric_ids", "period_viewers"),
                ("metric_ids", "period_buyers"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "4" in response.json()["detail"]


def test_hourly_comparison_rejects_invalid_natural_hour() -> None:
    client, _, _ = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params={"natural_hours": "99-00"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "99-00" in response.json()["detail"]


def test_hourly_comparison_ignores_missing_data_before_t_plus_one_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BeforeDeadline(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            value = cls(2026, 7, 16, 7, 59)
            return value.replace(tzinfo=tz) if tz is not None else value

    monkeypatch.setattr(hourly_comparison_module, "datetime", BeforeDeadline)
    client, _, _ = build_client()
    try:
        response = client.get(
            "/api/v1/overview/hourly-comparison",
            params={"end_date": "2026-07-15", "period_days": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    current = response.json()["series"][0]["points"][8]["current"]
    assert current["expected_samples"] is None
    assert current["coverage_rate"] is None


def test_hourly_comparison_export_includes_room_provenance() -> None:
    client, allowed_id, _ = build_client()
    try:
        exported = client.post(
            "/api/v1/overview/hourly-comparison/export",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(allowed_id),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert rows
    assert set(rows[0]) >= {"直播间ID", "直播间"}
    assert {row["直播间ID"] for row in rows} == {str(allowed_id)}
    assert {row["直播间"] for row in rows} == {"柏瑞美-散粉"}


def test_hourly_comparison_details_export_targets_and_permissions() -> None:
    client, allowed_id, denied_id = build_client()
    try:
        details = client.get(
            "/api/v1/overview/hourly-comparison/details",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "natural_hour": "08-09",
                "room_ids": str(allowed_id),
            },
        )
        exported = client.post(
            "/api/v1/overview/hourly-comparison/export",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(allowed_id),
            },
        )
        targets = client.get("/api/v1/settings/room-metric-targets")
        created = client.post(
            "/api/v1/settings/room-metric-targets",
            json={
                "room_id": str(allowed_id),
                "room_name": "柏瑞美-散粉",
                "product_category": "散粉",
                "metric_code": "period_net_roi",
                "target_value": "1.70",
                "effective_start_date": "2026-07-01",
                "effective_end_date": None,
                "enabled": True,
            },
        )
        updated = client.put(
            f"/api/v1/settings/room-metric-targets/{created.json()['id']}",
            json={**created.json(), "target_value": "1.75"},
        )
        created_rule = client.post(
            "/api/v1/settings/hourly-comparison-rules",
            json={
                "name": "3天周期总结",
                "period_days": 3,
                "spend_increase_threshold": "0.30",
                "roi_increase_threshold": "0.30",
                "roi_decrease_threshold": "-0.30",
                "minimum_spend": "100",
                "minimum_orders": 1,
                "minimum_coverage_rate": "0.80",
                "evaluation_delay_minutes": 15,
                "applicable_rooms": [],
                "enabled": True,
                "push_enabled": False,
            },
        )
        updated_rule = client.put(
            f"/api/v1/settings/hourly-comparison-rules/{created_rule.json()['id']}",
            json={**created_rule.json(), "spend_increase_threshold": "0.35"},
        )

        app.dependency_overrides[get_access_scope] = lambda: AccessScope(
            user_id=None,
            role="viewer",
            room_ids=frozenset({allowed_id}),
            can_export=False,
            permission_codes=frozenset({"dashboard.view"}),
        )
        denied_query = client.get(
            "/api/v1/overview/hourly-comparison",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(denied_id),
                "series_dimension": "room",
            },
        )
        denied_details = client.get(
            "/api/v1/overview/hourly-comparison/details",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "natural_hour": "08-09",
                "room_ids": str(denied_id),
            },
        )
        denied_export = client.post(
            "/api/v1/overview/hourly-comparison/export",
            params={"end_date": "2026-07-15", "period_days": 3},
        )
        denied_target_settings = client.get("/api/v1/settings/room-metric-targets")
        denied_rule_settings = client.get("/api/v1/settings/hourly-comparison-rules")
        app.dependency_overrides[get_access_scope] = lambda: AccessScope(
            user_id=None,
            role="viewer",
            room_ids=frozenset({allowed_id, denied_id}),
            can_export=True,
            export_room_ids=frozenset({allowed_id}),
            permission_codes=frozenset({"dashboard.view", "dashboard.export"}),
        )
        room_scoped_denied_export = client.post(
            "/api/v1/overview/hourly-comparison/export",
            params={
                "end_date": "2026-07-15",
                "period_days": 3,
                "room_ids": str(denied_id),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert details.status_code == 200
    assert len(details.json()["daily_rows"]) == 6
    assert details.json()["natural_hour"] == "08-09"
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert len(exported.content.decode("utf-8-sig").splitlines()) == 25
    assert targets.status_code == 200 and len(targets.json()) == 2
    assert created.status_code == 201
    assert updated.status_code == 200
    assert Decimal(str(updated.json()["target_value"])) == Decimal("1.75")
    assert created_rule.status_code == 201
    assert updated_rule.status_code == 200
    assert Decimal(str(updated_rule.json()["spend_increase_threshold"])) == Decimal("0.35")
    assert denied_query.status_code == 403
    assert denied_details.status_code == 403
    assert denied_export.status_code == 403
    assert denied_target_settings.status_code == 403
    assert denied_rule_settings.status_code == 403
    assert room_scoped_denied_export.status_code == 403
    assert HourlyComparisonService._csv_safe('=HYPERLINK("https://evil")').startswith("'=")


def test_anchor_trend_api_recalculate_detail_send_and_permissions() -> None:
    client, allowed_id, denied_id = build_client()
    try:
        create_rule = client.post(
            "/api/v1/settings/hourly-comparison-rules",
            json={
                "name": "API主播3天趋势通知",
                "rule_type": "anchor_trend_summary",
                "period_days": 3,
                "minimum_effective_hours": 1,
                "push_schedule": "manual",
                "schedule_timezone": "Asia/Shanghai",
                "applicable_rooms": [str(allowed_id)],
                "push_enabled": True,
                "send_rise": True,
                "send_fall": True,
                "rise_limit": 10,
                "fall_limit": 10,
                "allow_force_resend": True,
                "push_retry_limit": 3,
            },
        )
        assert create_rule.status_code == 201, create_rule.text
        rule_id = create_rule.json()["id"]

        recalculate = client.post(
            "/api/v1/alerts/anchor-trends/recalculate",
            json={
                "rule_id": rule_id,
                "period_days": 3,
                "end_date": "2026-07-15",
            },
        )
        assert recalculate.status_code == 200, recalculate.text
        calculation = recalculate.json()
        assert len(calculation["rise"]) == 1
        assert calculation["fall"] == []
        assert calculation["rise"][0]["room_id"] == str(allowed_id)
        assert calculation["rise"][0]["room_id"] != str(denied_id)
        event_id = calculation["event_ids"]["rise"]

        listing = client.get(
            "/api/v1/alerts/anchor-trends",
            params={"period_days": 3, "end_date": "2026-07-15"},
        )
        assert listing.status_code == 200, listing.text
        assert len(listing.json()["rise"]) == 1

        detail = client.get(f"/api/v1/alerts/anchor-trends/{event_id}")
        assert detail.status_code == 200, detail.text
        details = detail.json()["details"][0]
        assert len(details["hours"]) == 24
        assert details["daily"]
        assert details["raw_records"]
        assert Decimal(details["roi_numerator"]["current"]) == Decimal("670")
        assert Decimal(details["roi_denominator"]["current"]) == Decimal("350")

        send = client.post(
            "/api/v1/alerts/anchor-trends/send",
            json={
                "rule_id": rule_id,
                "period": "2026-07-15",
                "notification_type": "anchor_rise_summary",
            },
        )
        assert send.status_code == 200, send.text
        assert send.json()["push_status"] == "skipped"

        force = client.post(
            "/api/v1/alerts/anchor-trends/send",
            json={
                "rule_id": rule_id,
                "period": "2026-07-15",
                "notification_type": "anchor_rise_summary",
                "force_resend": True,
                "resend_reason": "API权限与审计回归测试",
            },
        )
        assert force.status_code == 200, force.text
        assert force.json()["event_id"] != event_id
        assert force.json()["push_status"] == "skipped"

        app.dependency_overrides[get_access_scope] = lambda: AccessScope(
            user_id=None,
            role="viewer",
            room_ids=frozenset({allowed_id}),
            can_export=False,
        )
        forbidden = client.post(
            "/api/v1/alerts/anchor-trends/send",
            json={
                "rule_id": rule_id,
                "period": "2026-07-15",
                "notification_type": "anchor_rise_summary",
                "force_resend": True,
                "resend_reason": "普通用户不得发送",
            },
        )
        assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_anchor_trend_routes_publish_strict_response_models() -> None:
    schema = app.openapi()
    expected_models = {
        ("/api/v1/alerts/anchor-trends", "get"): "AnchorTrendListResponse",
        ("/api/v1/alerts/anchor-trends/recalculate", "post"): ("AnchorTrendRecalculateResponse"),
        ("/api/v1/alerts/anchor-trends/{event_id}", "get"): ("AnchorTrendEventDetailsResponse"),
        ("/api/v1/alerts/anchor-trends/send", "post"): "AnchorTrendPushResponse",
        ("/api/v1/alerts/anchor-trends/test-push", "post"): "AnchorTrendPushResponse",
    }

    for (path, method), model_name in expected_models.items():
        response_schema = schema["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema == {"$ref": f"#/components/schemas/{model_name}"}
        assert schema["components"]["schemas"][model_name]["additionalProperties"] is False
