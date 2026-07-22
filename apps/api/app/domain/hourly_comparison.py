from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

ALLOWED_PERIOD_DAYS = frozenset({1, 3, 5, 7, 15, 30})
ZERO = Decimal(0)
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class DatePeriod:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class ComparisonPeriods:
    current: DatePeriod
    comparison: DatePeriod | None


@dataclass(frozen=True)
class HourDescriptor:
    key: str
    label: str
    sort: int


@dataclass(frozen=True)
class ComparisonResult:
    current: Decimal | None
    baseline: Decimal | None
    difference: Decimal | None
    current_to_baseline_ratio: Decimal | None
    current_to_baseline_percentage: Decimal | None
    growth_rate: Decimal | None
    growth_percentage: Decimal | None


@dataclass(frozen=True)
class DailyValue:
    business_date: date
    value: Decimal | None


@dataclass(frozen=True)
class BusinessKline:
    open: Decimal
    close: Decimal
    high: Decimal
    low: Decimal
    average: Decimal
    median: Decimal
    total: Decimal
    effective_days: int
    first_date: date
    last_date: date
    high_date: date
    low_date: date


@dataclass(frozen=True)
class TargetCandidate:
    room_id: str | None
    room_name: str | None
    product_category: str | None
    target_value: Decimal


@dataclass(frozen=True)
class HourlyStatusInput:
    current_roi: Decimal | None
    baseline_roi: Decimal | None
    current_spend: Decimal | None
    baseline_spend: Decimal | None
    target_roi: Decimal | None
    coverage_rate: Decimal | None
    minimum_coverage_rate: Decimal
    minimum_spend: Decimal
    current_orders: Decimal | None
    minimum_orders: int
    is_hour_complete: bool
    is_in_progress: bool
    data_valid: bool
    spend_increase_threshold: Decimal = Decimal("0.30")
    spend_decrease_threshold: Decimal = Decimal("-0.30")
    roi_increase_threshold: Decimal = Decimal("0.30")
    roi_decrease_threshold: Decimal = Decimal("-0.30")


@dataclass(frozen=True)
class HourlyStatus:
    code: str
    name: str
    level: str
    reasons: tuple[str, ...]
    reason_codes: tuple[str, ...]
    should_push: bool
    roi_growth: Decimal | None
    spend_growth: Decimal | None
    roi_target_gap: Decimal | None
    roi_target_attainment: Decimal | None
    roi_target_reached: bool | None


def build_periods(
    end_date: date,
    period_days: int | None = 7,
    *,
    custom_start_date: date | None = None,
    compare_enabled: bool = True,
) -> ComparisonPeriods:
    if custom_start_date is not None:
        if custom_start_date > end_date:
            raise ValueError("自定义开始日期不能晚于结束日期")
        current = DatePeriod(custom_start_date, end_date)
    else:
        if period_days not in ALLOWED_PERIOD_DAYS:
            raise ValueError("周期仅支持 1、3、5、7、15、30 天或自定义日期")
        assert period_days is not None
        current = DatePeriod(end_date - timedelta(days=period_days - 1), end_date)
    if not compare_enabled:
        return ComparisonPeriods(current=current, comparison=None)
    comparison_end = current.start - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=current.days - 1)
    return ComparisonPeriods(
        current=current,
        comparison=DatePeriod(comparison_start, comparison_end),
    )


def hour_descriptors() -> tuple[HourDescriptor, ...]:
    return tuple(
        HourDescriptor(
            key=f"{hour:02d}-{hour + 1:02d}",
            label=f"{hour:02d}:00-{hour + 1:02d}:00",
            sort=hour,
        )
        for hour in range(24)
    )


def ratio_of_sums(
    numerators: Iterable[Decimal | None], denominators: Iterable[Decimal | None]
) -> Decimal | None:
    numerator_values = [value for value in numerators if value is not None]
    denominator_values = [value for value in denominators if value is not None]
    if not numerator_values or not denominator_values:
        return None
    denominator = sum(denominator_values, ZERO)
    if denominator == ZERO:
        return None
    return sum(numerator_values, ZERO) / denominator


def compare_values(current: Decimal | None, baseline: Decimal | None) -> ComparisonResult:
    if current is None or baseline is None:
        return ComparisonResult(current, baseline, None, None, None, None, None)
    difference = current - baseline
    if baseline == ZERO:
        return ComparisonResult(current, baseline, difference, None, None, None, None)
    ratio = current / baseline
    growth = ratio - Decimal(1)
    return ComparisonResult(
        current=current,
        baseline=baseline,
        difference=difference,
        current_to_baseline_ratio=ratio,
        current_to_baseline_percentage=ratio * HUNDRED,
        growth_rate=growth,
        growth_percentage=growth * HUNDRED,
    )


def build_business_kline(values: Iterable[DailyValue]) -> BusinessKline | None:
    valid = sorted(
        (item for item in values if item.value is not None),
        key=lambda item: item.business_date,
    )
    if not valid:
        return None
    numeric_values = [item.value for item in valid if item.value is not None]
    total = sum(numeric_values, ZERO)
    high_item = max(valid, key=lambda item: item.value if item.value is not None else ZERO)
    low_item = min(valid, key=lambda item: item.value if item.value is not None else ZERO)
    return BusinessKline(
        open=numeric_values[0],
        close=numeric_values[-1],
        high=high_item.value if high_item.value is not None else ZERO,
        low=low_item.value if low_item.value is not None else ZERO,
        average=total / Decimal(len(numeric_values)),
        median=median(numeric_values),
        total=total,
        effective_days=len(numeric_values),
        first_date=valid[0].business_date,
        last_date=valid[-1].business_date,
        high_date=high_item.business_date,
        low_date=low_item.business_date,
    )


def infer_product_category(room_name: str) -> str | None:
    normalized = room_name.replace(" ", "")
    if "水散粉" in normalized:
        return "水散粉"
    if "妆前乳" in normalized:
        return "妆前乳"
    if "散粉" in normalized:
        return "散粉"
    return None


def select_target(
    room_id: str,
    room_name: str,
    product_category: str | None,
    targets: Iterable[TargetCandidate],
) -> Decimal | None:
    candidates = tuple(targets)
    for candidate in candidates:
        if candidate.room_id == room_id:
            return candidate.target_value
    for candidate in candidates:
        if candidate.room_name == room_name:
            return candidate.target_value
    category = product_category or infer_product_category(room_name)
    if category is None:
        return None
    for candidate in candidates:
        if candidate.product_category == category:
            return candidate.target_value
    return None


def common_target(targets: Iterable[Decimal | None]) -> Decimal | None:
    values = tuple(targets)
    if not values or any(value is None for value in values):
        return None
    distinct = {value for value in values if value is not None}
    return next(iter(distinct)) if len(distinct) == 1 else None


def _target_metrics(
    current_roi: Decimal | None, target_roi: Decimal | None
) -> tuple[Decimal | None, Decimal | None, bool | None]:
    if current_roi is None or target_roi is None:
        return None, None, None
    gap = current_roi - target_roi
    attainment = current_roi / target_roi if target_roi != ZERO else None
    return gap, attainment, current_roi >= target_roi


def _unable_status(
    data: HourlyStatusInput,
    code: str,
    reason: str,
    *,
    roi_growth: Decimal | None,
    spend_growth: Decimal | None,
) -> HourlyStatus:
    gap, attainment, reached = _target_metrics(data.current_roi, data.target_roi)
    return HourlyStatus(
        code="unable_to_judge",
        name="无法完整判断",
        level="neutral",
        reasons=(reason,),
        reason_codes=(code,),
        should_push=False,
        roi_growth=roi_growth,
        spend_growth=spend_growth,
        roi_target_gap=gap,
        roi_target_attainment=attainment,
        roi_target_reached=reached,
    )


def evaluate_hourly_status(data: HourlyStatusInput) -> HourlyStatus:
    roi_comparison = compare_values(data.current_roi, data.baseline_roi)
    spend_comparison = compare_values(data.current_spend, data.baseline_spend)
    roi_growth = roi_comparison.growth_rate
    spend_growth = spend_comparison.growth_rate

    if not data.data_valid:
        return _unable_status(
            data,
            "invalid_data",
            "数据被标记为异常，不参与正式判断",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )
    if data.is_in_progress or not data.is_hour_complete:
        return _unable_status(
            data,
            "in_progress",
            "当前自然小时仍在进行中",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )
    if data.coverage_rate is None:
        return _unable_status(
            data,
            "no_schedule_baseline",
            "暂无可靠排班基准，无法计算完整率",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )
    if data.coverage_rate < data.minimum_coverage_rate:
        return _unable_status(
            data,
            "incomplete_data",
            "数据完整率低于规则门槛",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )
    if data.target_roi is None or data.target_roi == ZERO:
        return _unable_status(
            data,
            "target_not_configured",
            "当前直播间未配置有效 ROI 目标",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )
    if data.current_spend is None or data.current_spend < data.minimum_spend:
        return _unable_status(
            data,
            "insufficient_sample",
            "当前消耗未达到最小样本门槛",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )
    if data.minimum_orders > 0 and (
        data.current_orders is None or data.current_orders < Decimal(data.minimum_orders)
    ):
        return _unable_status(
            data,
            "insufficient_sample",
            "当前订单数未达到最小样本门槛",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )
    if (
        data.current_roi is None
        or data.current_spend is None
        or roi_growth is None
        or spend_growth is None
    ):
        return _unable_status(
            data,
            "no_comparable_baseline",
            "无有效可比基准",
            roi_growth=roi_growth,
            spend_growth=spend_growth,
        )

    target_gap, target_attainment, target_reached = _target_metrics(
        data.current_roi, data.target_roi
    )
    assert target_reached is not None
    reasons: list[str] = []
    reason_codes: list[str] = []

    def result(code: str, name: str, level: str, should_push: bool) -> HourlyStatus:
        return HourlyStatus(
            code=code,
            name=name,
            level=level,
            reasons=tuple(reasons),
            reason_codes=tuple(reason_codes),
            should_push=should_push,
            roi_growth=roi_growth,
            spend_growth=spend_growth,
            roi_target_gap=target_gap,
            roi_target_attainment=target_attainment,
            roi_target_reached=target_reached,
        )

    spend_up = spend_growth >= data.spend_increase_threshold
    spend_down = spend_growth <= data.spend_decrease_threshold
    roi_up = roi_growth >= data.roi_increase_threshold
    roi_down = roi_growth <= data.roi_decrease_threshold

    if spend_down:
        reasons.append("消耗下降达到阈值")
        reason_codes.append("spend_decrease")

    if spend_up and roi_growth < ZERO:
        reasons.extend(["消耗上涨达到阈值", "ROI 较基准下降"])
        reason_codes.extend(["spend_increase", "roi_decrease"])
        if not target_reached:
            reasons.append("ROI 低于目标")
            reason_codes.append("roi_below_target")
        return result("efficiency_deterioration", "消耗效率恶化", "critical", True)
    if roi_down:
        reasons.append("ROI 下降达到严重阈值")
        reason_codes.append("roi_severe_decrease")
        if not target_reached:
            reasons.append("ROI 低于目标")
            reason_codes.append("roi_below_target")
        return result(
            "roi_severe_drop",
            "ROI严重下降",
            "critical" if not target_reached else "warning",
            True,
        )
    if spend_up and not target_reached:
        reasons.extend(["消耗上涨达到阈值", "ROI 低于目标"])
        reason_codes.extend(["spend_increase", "roi_below_target"])
        return result("spend_anomaly", "消耗上涨但ROI未达标", "warning", True)
    if spend_up and roi_up and target_reached:
        reasons.extend(["消耗上涨达到阈值", "ROI 上涨达到阈值", "ROI 达到目标"])
        reason_codes.extend(["spend_increase", "roi_increase", "roi_target_reached"])
        return result("excellent_scaling", "优秀放量时段", "positive", True)
    if roi_up and target_reached:
        reasons.extend(["ROI 上涨达到阈值", "ROI 达到目标"])
        reason_codes.extend(["roi_increase", "roi_target_reached"])
        return result("roi_excellent_growth", "ROI优秀提升", "positive", True)
    if data.baseline_roi is not None and data.baseline_roi < data.target_roi and target_reached:
        reasons.extend(["上一周期 ROI 未达标", "当前周期 ROI 达到目标"])
        reason_codes.extend(["baseline_roi_below_target", "roi_target_reached"])
        return result(
            "roi_target_breakthrough",
            "ROI由未达标转为达标",
            "positive",
            True,
        )
    if spend_up and target_reached and ZERO <= roi_growth < data.roi_increase_threshold:
        reasons.extend(["消耗上涨达到阈值", "ROI 未下降且达到目标"])
        reason_codes.extend(["spend_increase", "roi_target_reached"])
        return result("scaling_normal", "放量正常", "positive", True)
    if roi_up and not target_reached:
        reasons.extend(["ROI 上涨达到阈值", "ROI 仍低于目标"])
        reason_codes.extend(["roi_increase", "roi_below_target"])
        return result("improving_below_target", "改善中但仍未达标", "warning", True)
    if target_reached:
        reasons.append("ROI 达到目标")
        reason_codes.append("roi_target_reached")
        return result("roi_target_reached", "ROI达标", "positive", True)
    reasons.append("ROI 低于目标")
    reason_codes.append("roi_below_target")
    return result("roi_below_target", "ROI未达标", "warning", True)
