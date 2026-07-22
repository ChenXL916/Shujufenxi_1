from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.metrics import MetricCatalog
from app.models.entities import (
    HourlyComparisonRule,
    MetricDefinition,
    Room,
    RoomMetricTarget,
    ShiftRule,
    User,
)
from app.services.permission_service import seed_permission_reference_data

ROI_TARGETS = (
    ("柏瑞美-散粉", "散粉", Decimal("1.81")),
    ("柏瑞美-妆前乳", "妆前乳", Decimal("1.82")),
    ("Mistine-水散粉", "水散粉", Decimal("2.00")),
)


def seed_reference_data(
    session: Session,
    root: Path,
    dev_admin_email: str,
    *,
    include_permission_test_accounts: bool = False,
    default_feishu_chat_id: str | None = None,
) -> None:
    catalog = MetricCatalog.from_yaml(root / "config" / "metric_seed.yml")
    for order, spec in enumerate(catalog.specs):
        metric = session.scalar(
            select(MetricDefinition).where(MetricDefinition.metric_key == spec.key)
        )
        values = {
            "source_field_name": spec.field,
            "display_name": spec.field,
            "category": spec.category,
            "unit": spec.unit,
            "precision": spec.precision,
            "scope": spec.scope,
            "aggregation_strategy": spec.aggregation,
            "numerator_metric_key": spec.numerator,
            "denominator_metric_key": spec.denominator,
            "chartable": True,
            "comparable": spec.aggregation != "NONE",
            "alertable": spec.alertable,
            "supports_hourly_trend": spec.supports_hourly_trend,
            "supports_kline": spec.supports_kline,
            "is_cumulative": spec.is_cumulative,
            "direction": spec.direction,
            "default_visible": spec.default,
            "enabled": True,
            "sort_order": order,
            "description": f"{spec.scope} 指标，汇总口径 {spec.aggregation}",
        }
        if metric is None:
            session.add(MetricDefinition(metric_key=spec.key, **values))
        else:
            for field, value in values.items():
                setattr(metric, field, value)

    shift_payload = yaml.safe_load((root / "config" / "shift_seed.yml").read_text("utf-8"))
    for item in shift_payload["shifts"]:
        rule = session.scalar(select(ShiftRule).where(ShiftRule.name == item["name"]))
        start = _parse_time(item["start"])
        end = _parse_time(item["end"])
        values = {
            "start_time": start,
            "end_time": end,
            "crosses_midnight": bool(item["crosses_midnight"]),
            "is_rest": bool(item["is_rest"]),
            "enabled": True,
            "notes": "系统初始化班次",
        }
        if rule is None:
            session.add(ShiftRule(name=item["name"], **values))
        else:
            for field, value in values.items():
                setattr(rule, field, value)

    if session.scalar(select(User).where(User.email == dev_admin_email)) is None:
        session.add(
            User(
                feishu_user_id=None,
                name="开发管理员",
                avatar_url=None,
                email=dev_admin_email,
                username="developer",
                password_hash=None,
                status="active",
                role_name="developer",
                active=True,
                last_login_at=None,
            )
        )
    for room_name, category, target_value in ROI_TARGETS:
        room = session.scalar(select(Room).where(Room.name == room_name))
        target = session.scalar(
            select(RoomMetricTarget).where(
                RoomMetricTarget.room_name == room_name,
                RoomMetricTarget.metric_code == "period_overall_roi",
                RoomMetricTarget.effective_start_date.is_(None),
                RoomMetricTarget.effective_end_date.is_(None),
            )
        )
        values = {
            "room_id": room.id if room is not None else None,
            "product_category": category,
            "target_value": target_value,
            "enabled": True,
            "updated_by": None,
        }
        if target is None:
            session.add(
                RoomMetricTarget(
                    room_name=room_name,
                    metric_code="period_overall_roi",
                    effective_start_date=None,
                    effective_end_date=None,
                    **values,
                )
            )
        else:
            for field, value in values.items():
                setattr(target, field, value)
    hourly_rule = session.scalar(
        select(HourlyComparisonRule).where(HourlyComparisonRule.name == "1天小时ROI与消耗周期对比")
    )
    rule_values = {
        "rule_type": "hourly_comparison_legacy",
        "period_days": 1,
        "spend_increase_threshold": Decimal("0.30"),
        "spend_decrease_threshold": Decimal("-0.30"),
        "roi_increase_threshold": Decimal("0.30"),
        "roi_decrease_threshold": Decimal("-0.30"),
        "minimum_spend": Decimal(0),
        "minimum_orders": 0,
        "minimum_coverage_rate": Decimal("0.80"),
        "evaluation_delay_minutes": 15,
        "applicable_rooms": [],
        "applicable_anchors": [],
        "enabled": True,
        "push_enabled": False,
        "created_by": None,
        "updated_by": None,
    }
    if hourly_rule is None:
        session.add(
            HourlyComparisonRule(
                name="1天小时ROI与消耗周期对比",
                **rule_values,
            )
        )
    else:
        for field, value in rule_values.items():
            setattr(hourly_rule, field, value)
    session.commit()
    seed_permission_reference_data(
        session,
        dev_admin_email,
        include_test_accounts=include_permission_test_accounts,
        default_feishu_chat_id=default_feishu_chat_id,
    )


def _parse_time(value: str | None):  # type: ignore[no-untyped-def]
    if value is None:
        return None
    from datetime import time

    hour, minute = (int(part) for part in value.split(":"))
    return time(hour, minute)
