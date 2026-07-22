from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.domain.hourly_comparison import compare_values

ZERO = Decimal(0)
TrendType = Literal["rise", "fall", "neutral", "insufficient"]


@dataclass(frozen=True)
class AnchorTrendInput:
    current_roi: Decimal | None
    baseline_roi: Decimal | None
    current_spend: Decimal | None
    baseline_spend: Decimal | None
    current_orders: Decimal | None
    baseline_orders: Decimal | None
    target_roi: Decimal | None
    current_coverage_rate: Decimal | None
    baseline_coverage_rate: Decimal | None
    current_effective_hours: int
    baseline_effective_hours: int
    minimum_spend: Decimal
    minimum_orders: int
    minimum_coverage_rate: Decimal
    minimum_effective_hours: int
    roi_rise_threshold: Decimal = Decimal("0.30")
    roi_fall_threshold: Decimal = Decimal("-0.30")
    spend_rise_threshold: Decimal = Decimal("0.30")
    spend_fall_threshold: Decimal = Decimal("-0.30")
    current_period_complete: bool = True
    baseline_period_complete: bool = True
    data_valid: bool = True


@dataclass(frozen=True)
class AnchorTrendDecision:
    trend_type: TrendType
    primary_code: str
    primary_name: str
    level: str
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    roi_growth_rate: Decimal | None
    spend_growth_rate: Decimal | None
    roi_target_gap: Decimal | None
    roi_target_reached: bool | None
    baseline_roi_target_reached: bool | None


_STATUS_NAMES = {
    "efficiency_deterioration": "消耗上涨、效率下降",
    "roi_target_broken": "ROI跌破目标",
    "roi_fall": "ROI下跌",
    "spend_roi_double_fall": "消耗和ROI双降",
    "below_target_declining": "未达标且继续下跌",
    "spend_roi_double_rise": "消耗和ROI双涨",
    "roi_target_breakthrough": "ROI突破目标",
    "lower_spend_higher_roi": "降耗提效",
    "roi_rise": "ROI上涨",
    "spend_rise": "放量上涨",
    "no_significant_change": "无明显变化",
    "no_comparable_baseline": "无有效可比基准",
    "sample_insufficient": "样本不足",
    "data_incomplete": "数据不完整",
    "invalid_data": "异常数据",
}


def _insufficient(
    code: str,
    reason: str,
    *,
    roi_growth_rate: Decimal | None,
    spend_growth_rate: Decimal | None,
    target_gap: Decimal | None,
    target_reached: bool | None,
    baseline_target_reached: bool | None,
) -> AnchorTrendDecision:
    return AnchorTrendDecision(
        trend_type="insufficient",
        primary_code=code,
        primary_name=_STATUS_NAMES[code],
        level="neutral",
        reason_codes=(code,),
        reasons=(reason,),
        roi_growth_rate=roi_growth_rate,
        spend_growth_rate=spend_growth_rate,
        roi_target_gap=target_gap,
        roi_target_reached=target_reached,
        baseline_roi_target_reached=baseline_target_reached,
    )


def evaluate_anchor_trend(data: AnchorTrendInput) -> AnchorTrendDecision:
    """Evaluate one room+anchor equal-period summary using unrounded Decimals."""
    roi_comparison = compare_values(data.current_roi, data.baseline_roi)
    spend_comparison = compare_values(data.current_spend, data.baseline_spend)
    roi_growth = roi_comparison.growth_rate
    spend_growth = spend_comparison.growth_rate
    target_gap = (
        data.current_roi - data.target_roi
        if data.current_roi is not None and data.target_roi is not None
        else None
    )
    target_reached = (
        data.current_roi >= data.target_roi
        if data.current_roi is not None and data.target_roi is not None
        else None
    )
    baseline_target_reached = (
        data.baseline_roi >= data.target_roi
        if data.baseline_roi is not None and data.target_roi is not None
        else None
    )

    def insufficient(code: str, reason: str) -> AnchorTrendDecision:
        return _insufficient(
            code,
            reason,
            roi_growth_rate=roi_growth,
            spend_growth_rate=spend_growth,
            target_gap=target_gap,
            target_reached=target_reached,
            baseline_target_reached=baseline_target_reached,
        )

    if not data.data_valid:
        return insufficient("invalid_data", "数据被标记为异常，不参与正式榜单")
    if not data.current_period_complete or not data.baseline_period_complete:
        return insufficient("data_incomplete", "当前周期或基准周期尚未完整")
    if (
        data.current_coverage_rate is None
        or data.baseline_coverage_rate is None
        or data.current_coverage_rate < data.minimum_coverage_rate
        or data.baseline_coverage_rate < data.minimum_coverage_rate
    ):
        return insufficient("data_incomplete", "当前周期或基准周期完整率低于规则门槛")
    if (
        data.current_effective_hours < data.minimum_effective_hours
        or data.baseline_effective_hours < data.minimum_effective_hours
    ):
        return insufficient("sample_insufficient", "当前周期或基准周期有效直播小时不足")
    if data.current_spend is None or data.current_spend < data.minimum_spend:
        return insufficient("sample_insufficient", "当前周期消耗未达到最小门槛")
    if data.minimum_orders > 0 and (
        data.current_orders is None or data.current_orders < Decimal(data.minimum_orders)
    ):
        return insufficient("sample_insufficient", "当前周期订单数未达到最小门槛")
    if (
        data.current_roi is None
        or data.baseline_roi is None
        or data.baseline_roi == ZERO
        or data.baseline_spend is None
        or data.baseline_spend == ZERO
        or roi_growth is None
        or spend_growth is None
    ):
        return insufficient("no_comparable_baseline", "无有效可比基准")

    spend_up = spend_growth >= data.spend_rise_threshold
    spend_down = spend_growth <= data.spend_fall_threshold
    roi_up = roi_growth >= data.roi_rise_threshold
    roi_down = roi_growth <= data.roi_fall_threshold
    matches: list[tuple[str, str, Literal["rise", "fall"], str]] = []

    def match(condition: bool, code: str, trend_type: Literal["rise", "fall"], reason: str) -> None:
        if condition:
            matches.append((code, _STATUS_NAMES[code], trend_type, reason))

    # The insertion order is the documented primary-status priority.
    match(
        spend_up and roi_growth < ZERO,
        "efficiency_deterioration",
        "fall",
        "消耗达到上涨阈值但ROI下降",
    )
    match(
        baseline_target_reached is True and target_reached is False,
        "roi_target_broken",
        "fall",
        "ROI由达标跌到未达标",
    )
    match(roi_down, "roi_fall", "fall", "ROI下降达到阈值")
    match(
        spend_down and roi_down,
        "spend_roi_double_fall",
        "fall",
        "消耗和ROI同时下降达到阈值",
    )
    match(
        target_reached is False and roi_growth < ZERO,
        "below_target_declining",
        "fall",
        "当前ROI未达标且趋势继续下降",
    )
    match(
        spend_up and roi_up,
        "spend_roi_double_rise",
        "rise",
        "消耗和ROI同时上涨达到阈值",
    )
    match(
        baseline_target_reached is False and target_reached is True,
        "roi_target_breakthrough",
        "rise",
        "ROI由未达标提升为达标",
    )
    match(
        spend_down and roi_growth > ZERO,
        "lower_spend_higher_roi",
        "rise",
        "消耗下降且ROI上涨",
    )
    match(roi_up, "roi_rise", "rise", "ROI上涨达到阈值")
    match(
        spend_up and roi_growth >= ZERO,
        "spend_rise",
        "rise",
        "消耗上涨达到阈值且ROI未下降",
    )

    if not matches:
        reasons = ["消耗和ROI变化均未达到关注条件"]
        if target_reached is True:
            reasons.append("当前ROI已达到目标")
        elif target_reached is False:
            reasons.append("当前ROI仍未达到目标")
        return AnchorTrendDecision(
            trend_type="neutral",
            primary_code="no_significant_change",
            primary_name=_STATUS_NAMES["no_significant_change"],
            level="neutral",
            reason_codes=("no_significant_change",),
            reasons=tuple(reasons),
            roi_growth_rate=roi_growth,
            spend_growth_rate=spend_growth,
            roi_target_gap=target_gap,
            roi_target_reached=target_reached,
            baseline_roi_target_reached=baseline_target_reached,
        )

    primary_code, primary_name, trend_type, _ = matches[0]
    reason_codes = [item[0] for item in matches]
    reasons = [item[3] for item in matches]
    if target_reached is True:
        reason_codes.append("roi_target_reached")
        reasons.append("当前ROI已达到目标")
    elif target_reached is False:
        reason_codes.append("roi_below_target")
        reasons.append("当前ROI仍未达到目标")
    return AnchorTrendDecision(
        trend_type=trend_type,
        primary_code=primary_code,
        primary_name=primary_name,
        level="positive" if trend_type == "rise" else "critical",
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        reasons=tuple(dict.fromkeys(reasons)),
        roi_growth_rate=roi_growth,
        spend_growth_rate=spend_growth,
        roi_target_gap=target_gap,
        roi_target_reached=target_reached,
        baseline_roi_target_reached=baseline_target_reached,
    )
