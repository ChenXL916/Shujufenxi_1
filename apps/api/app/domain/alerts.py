from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from app.domain.aggregation import safe_divide

Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True)
class AlertContext:
    room_id: str
    business_date: date
    hour_slot: str
    anchor: str | None
    control: str | None
    metric_key: str
    current_value: Decimal | None
    baseline_value: Decimal | None
    spend: Decimal | None
    orders: Decimal | None
    amount: Decimal | None
    hour_ended: bool = True
    sync_succeeded: bool = True
    data_valid: bool = True


@dataclass(frozen=True)
class AlertDecision:
    triggered: bool
    ratio_percent: Decimal | None = None
    growth_percent: Decimal | None = None
    reason: str = ""


def evaluate_ratio_rule(
    context: AlertContext,
    *,
    operator: Literal[">=", "<=", "<", ">"],
    threshold: Decimal,
    min_spend: Decimal = Decimal(0),
    min_orders: Decimal = Decimal(0),
    min_amount: Decimal = Decimal(0),
) -> AlertDecision:
    if not context.hour_ended or not context.sync_succeeded or not context.data_valid:
        return AlertDecision(False, reason="小时未结束、同步未成功或数据无效")
    if context.current_value is None or context.baseline_value is None:
        return AlertDecision(False, reason="无有效可比基准")
    if context.baseline_value == Decimal(0):
        return AlertDecision(False, reason="基准值为零，不能计算倍数")
    if (context.spend or Decimal(0)) < min_spend:
        return AlertDecision(False, reason="未达到最小消耗门槛")
    if (context.orders or Decimal(0)) < min_orders:
        return AlertDecision(False, reason="未达到最小订单门槛")
    if (context.amount or Decimal(0)) < min_amount:
        return AlertDecision(False, reason="未达到最小金额门槛")
    ratio = safe_divide(context.current_value, context.baseline_value)
    assert ratio is not None
    growth = ratio - Decimal(1)
    comparisons = {
        ">=": ratio >= threshold,
        "<=": growth <= threshold,
        "<": context.current_value < threshold,
        ">": context.current_value > threshold,
    }
    return AlertDecision(
        comparisons[operator],
        ratio_percent=ratio * Decimal(100),
        growth_percent=growth * Decimal(100),
        reason="达到阈值" if comparisons[operator] else "未达到阈值",
    )


def alert_dedup_key(
    room_id: str,
    business_date: date,
    hour_slot: str,
    anchor: str | None,
    control: str | None,
    metric_key: str,
    rule_type: str,
) -> str:
    payload = "|".join(
        [
            room_id,
            business_date.isoformat(),
            hour_slot,
            anchor or "",
            control or "",
            metric_key,
            rule_type,
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def comparison_copy(
    metric_name: str,
    current: Decimal,
    baseline: Decimal,
    ratio_percent: Decimal,
    growth_percent: Decimal,
) -> str:
    verb = "提升" if growth_percent >= 0 else "下降"
    ratio = _number(ratio_percent)
    growth = _number(abs(growth_percent))
    return (
        f"当前{metric_name}{_number(current)}，基准{_number(baseline)}；"
        f"当前值是基准值的{ratio}%，较基准{verb}{growth}%。"
    )


def _number(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")
