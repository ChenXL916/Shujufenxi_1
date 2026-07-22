from datetime import date
from decimal import Decimal

import pytest

from app.domain.hourly_comparison import (
    DailyValue,
    HourlyStatusInput,
    TargetCandidate,
    build_business_kline,
    build_periods,
    common_target,
    compare_values,
    evaluate_hourly_status,
    hour_descriptors,
    infer_product_category,
    ratio_of_sums,
    select_target,
)


def test_period_presets_are_inclusive_and_use_previous_equal_length_period() -> None:
    expected = {
        1: (date(2026, 7, 15), date(2026, 7, 14), date(2026, 7, 14)),
        3: (date(2026, 7, 13), date(2026, 7, 10), date(2026, 7, 12)),
        5: (date(2026, 7, 11), date(2026, 7, 6), date(2026, 7, 10)),
        7: (date(2026, 7, 9), date(2026, 7, 2), date(2026, 7, 8)),
        15: (date(2026, 7, 1), date(2026, 6, 16), date(2026, 6, 30)),
        30: (date(2026, 6, 16), date(2026, 5, 17), date(2026, 6, 15)),
    }
    for days, (current_start, comparison_start, comparison_end) in expected.items():
        periods = build_periods(end_date=date(2026, 7, 15), period_days=days)
        assert periods.current.start == current_start
        assert periods.current.end == date(2026, 7, 15)
        assert periods.comparison is not None
        assert periods.comparison.start == comparison_start
        assert periods.comparison.end == comparison_end


def test_custom_period_handles_leap_day_and_comparison_can_be_disabled() -> None:
    periods = build_periods(
        end_date=date(2024, 3, 2),
        period_days=None,
        custom_start_date=date(2024, 2, 28),
    )
    assert periods.current.days == 4
    assert periods.current.start == date(2024, 2, 28)
    assert periods.comparison is not None
    assert periods.comparison.start == date(2024, 2, 24)
    assert periods.comparison.end == date(2024, 2, 27)
    assert build_periods(date(2026, 1, 2), 3, compare_enabled=False).comparison is None


def test_invalid_periods_are_rejected() -> None:
    with pytest.raises(ValueError, match="周期"):
        build_periods(date(2026, 7, 15), 2)
    with pytest.raises(ValueError, match="开始日期"):
        build_periods(date(2026, 7, 15), None, custom_start_date=date(2026, 7, 16))


def test_hour_descriptors_always_return_24_naturally_sorted_slots() -> None:
    hours = hour_descriptors()
    assert len(hours) == 24
    assert [(hours[0].key, hours[0].sort), (hours[-1].key, hours[-1].sort)] == [
        ("00-01", 0),
        ("23-24", 23),
    ]
    assert hours[-1].label == "23:00-24:00"


def test_ratio_of_sums_and_comparison_formula_do_not_average_roi() -> None:
    roi = ratio_of_sums(
        [Decimal("300"), Decimal("100")],
        [Decimal("100"), Decimal("100")],
    )
    assert roi == Decimal("2")
    comparison = compare_values(Decimal("3"), Decimal("1.5"))
    assert comparison.difference == Decimal("1.5")
    assert comparison.current_to_baseline_ratio == Decimal("2")
    assert comparison.current_to_baseline_percentage == Decimal("200")
    assert comparison.growth_rate == Decimal("1")
    assert comparison.growth_percentage == Decimal("100")


def test_zero_or_missing_denominator_returns_null_and_never_infinity() -> None:
    assert ratio_of_sums([Decimal("1")], [Decimal("0")]) is None
    result = compare_values(Decimal("3"), Decimal("0"))
    assert result.current_to_baseline_ratio is None
    assert result.growth_rate is None
    assert compare_values(None, Decimal("1")).difference is None


def test_business_kline_uses_earliest_latest_min_max_and_skips_missing_dates() -> None:
    kline = build_business_kline(
        [
            DailyValue(date(2026, 7, 9), Decimal("1.65")),
            DailyValue(date(2026, 7, 10), None),
            DailyValue(date(2026, 7, 11), Decimal("2.05")),
            DailyValue(date(2026, 7, 12), Decimal("1.51")),
            DailyValue(date(2026, 7, 15), Decimal("1.90")),
        ]
    )
    assert kline is not None
    assert (kline.open, kline.close, kline.high, kline.low) == (
        Decimal("1.65"),
        Decimal("1.90"),
        Decimal("2.05"),
        Decimal("1.51"),
    )
    assert kline.effective_days == 4
    assert kline.first_date == date(2026, 7, 9)
    assert kline.last_date == date(2026, 7, 15)
    assert kline.high_date == date(2026, 7, 11)
    assert kline.low_date == date(2026, 7, 12)
    assert kline.total == Decimal("7.11")


def test_one_day_kline_has_identical_ohlc_without_fabricated_volatility() -> None:
    kline = build_business_kline([DailyValue(date(2026, 7, 15), Decimal("2"))])
    assert kline is not None
    assert {kline.open, kline.close, kline.high, kline.low, kline.average, kline.median} == {
        Decimal("2")
    }
    assert build_business_kline([DailyValue(date(2026, 7, 15), None)]) is None


def test_roi_target_matching_priority_and_water_powder_category() -> None:
    targets = [
        TargetCandidate(None, None, "散粉", Decimal("1.81")),
        TargetCandidate(None, None, "水散粉", Decimal("2.00")),
        TargetCandidate(None, "柏瑞美-妆前乳", None, Decimal("1.82")),
        TargetCandidate("room-1", None, None, Decimal("1.91")),
    ]
    assert select_target("room-1", "柏瑞美-散粉", "散粉", targets) == Decimal("1.91")
    assert select_target("room-2", "柏瑞美-妆前乳", "妆前乳", targets) == Decimal("1.82")
    assert select_target("room-3", "Mistine-水散粉", None, targets) == Decimal("2.00")
    assert infer_product_category("Mistine-水散粉") == "水散粉"
    assert select_target("room-4", "未知产品", None, targets) is None


def test_different_room_targets_are_never_simple_averaged() -> None:
    assert common_target([Decimal("1.81"), Decimal("1.81")]) == Decimal("1.81")
    assert common_target([Decimal("1.81"), Decimal("1.82")]) is None
    assert common_target([None, Decimal("1.81")]) is None


def status_input(**overrides: object) -> HourlyStatusInput:
    values: dict[str, object] = {
        "current_roi": Decimal("1.9"),
        "baseline_roi": Decimal("1.4"),
        "current_spend": Decimal("130"),
        "baseline_spend": Decimal("100"),
        "target_roi": Decimal("1.81"),
        "coverage_rate": Decimal("1"),
        "minimum_coverage_rate": Decimal("0.80"),
        "minimum_spend": Decimal("10"),
        "current_orders": Decimal("10"),
        "minimum_orders": 1,
        "is_hour_complete": True,
        "is_in_progress": False,
        "data_valid": True,
    }
    values.update(overrides)
    return HourlyStatusInput(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "code", "level"),
    [
        (
            {
                "current_roi": Decimal("1.5"),
                "baseline_roi": Decimal("2"),
                "current_spend": Decimal("130"),
            },
            "efficiency_deterioration",
            "critical",
        ),
        (
            {
                "current_roi": Decimal("1.3"),
                "baseline_roi": Decimal("2"),
                "current_spend": Decimal("100"),
            },
            "roi_severe_drop",
            "critical",
        ),
        (
            {
                "current_roi": Decimal("1.7"),
                "baseline_roi": Decimal("1.7"),
                "current_spend": Decimal("130"),
            },
            "spend_anomaly",
            "warning",
        ),
        ({}, "excellent_scaling", "positive"),
        ({"current_spend": Decimal("100")}, "roi_excellent_growth", "positive"),
        (
            {
                "current_roi": Decimal("1.85"),
                "baseline_roi": Decimal("1.8"),
                "current_spend": Decimal("100"),
            },
            "roi_target_breakthrough",
            "positive",
        ),
        (
            {
                "current_roi": Decimal("1.7"),
                "baseline_roi": Decimal("1.2"),
                "current_spend": Decimal("100"),
            },
            "improving_below_target",
            "warning",
        ),
    ],
)
def test_status_rules_follow_priority(overrides: dict[str, object], code: str, level: str) -> None:
    status = evaluate_hourly_status(status_input(**overrides))
    assert status.code == code
    assert status.level == level
    assert status.reasons


@pytest.mark.parametrize(
    ("current_roi", "target_roi", "expected_code", "expected_level", "expected_gap"),
    [
        ("1.80", "1.81", "roi_below_target", "warning", "-0.01"),
        ("1.81", "1.81", "roi_target_reached", "positive", "0.00"),
        ("1.81", "1.82", "roi_below_target", "warning", "-0.01"),
        ("1.82", "1.82", "roi_target_reached", "positive", "0.00"),
        ("1.99", "2.00", "roi_below_target", "warning", "-0.01"),
        ("2.00", "2.00", "roi_target_reached", "positive", "0.00"),
    ],
)
def test_roi_target_boundaries_create_red_or_green_push_decisions(
    current_roi: str,
    target_roi: str,
    expected_code: str,
    expected_level: str,
    expected_gap: str,
) -> None:
    status = evaluate_hourly_status(
        status_input(
            current_roi=Decimal(current_roi),
            baseline_roi=Decimal(current_roi),
            current_spend=Decimal("100"),
            baseline_spend=Decimal("100"),
            target_roi=Decimal(target_roi),
        )
    )

    assert status.code == expected_code
    assert status.level == expected_level
    assert status.roi_target_gap == Decimal(expected_gap)
    assert status.should_push is True


def test_exact_thirty_percent_growth_uses_unrounded_decimal_values() -> None:
    spend = compare_values(Decimal("13000"), Decimal("10000"))
    roi = compare_values(Decimal("1.95"), Decimal("1.50"))

    assert spend.growth_rate == Decimal("0.30")
    assert spend.growth_percentage == Decimal("30.00")
    assert roi.growth_rate == Decimal("0.30")
    assert roi.growth_percentage == Decimal("30.00")


@pytest.mark.parametrize(
    ("overrides", "code", "name", "level"),
    [
        (
            {
                "current_spend": Decimal("13000"),
                "baseline_spend": Decimal("10000"),
                "current_roi": Decimal("1.90"),
                "baseline_roi": Decimal("1.40"),
            },
            "excellent_scaling",
            "优秀放量时段",
            "positive",
        ),
        (
            {
                "current_spend": Decimal("10000"),
                "baseline_spend": Decimal("10000"),
                "current_roi": Decimal("1.50"),
                "baseline_roi": Decimal("1.10"),
            },
            "improving_below_target",
            "改善中但仍未达标",
            "warning",
        ),
        (
            {
                "current_spend": Decimal("13500"),
                "baseline_spend": Decimal("10000"),
                "current_roi": Decimal("1.65"),
                "baseline_roi": Decimal("1.70"),
            },
            "efficiency_deterioration",
            "消耗效率恶化",
            "critical",
        ),
        (
            {
                "current_spend": Decimal("10000"),
                "baseline_spend": Decimal("10000"),
                "current_roi": Decimal("1.40"),
                "baseline_roi": Decimal("2.00"),
            },
            "roi_severe_drop",
            "ROI严重下降",
            "critical",
        ),
        (
            {
                "current_spend": Decimal("10000"),
                "baseline_spend": Decimal("10000"),
                "current_roi": Decimal("1.81"),
                "baseline_roi": Decimal("1.80"),
            },
            "roi_target_breakthrough",
            "ROI由未达标转为达标",
            "positive",
        ),
    ],
)
def test_anchor_spend_roi_status_examples_follow_required_priority(
    overrides: dict[str, object], code: str, name: str, level: str
) -> None:
    status = evaluate_hourly_status(status_input(**overrides))

    assert status.code == code
    assert status.name == name
    assert status.level == level
    assert status.should_push is True


def test_zero_baseline_and_incomplete_data_never_create_wave_pushes() -> None:
    no_baseline = evaluate_hourly_status(
        status_input(baseline_roi=Decimal("0"), baseline_spend=Decimal("0"))
    )
    incomplete = evaluate_hourly_status(status_input(coverage_rate=Decimal("0.70")))

    assert no_baseline.code == "unable_to_judge"
    assert no_baseline.reason_codes == ("no_comparable_baseline",)
    assert no_baseline.roi_growth is None
    assert no_baseline.spend_growth is None
    assert no_baseline.should_push is False
    assert incomplete.code == "unable_to_judge"
    assert incomplete.reason_codes == ("incomplete_data",)
    assert incomplete.should_push is False


def test_status_preconditions_suppress_percentage_alerts() -> None:
    cases = [
        ({"baseline_roi": Decimal("0")}, "no_comparable_baseline"),
        ({"coverage_rate": Decimal("0.79")}, "incomplete_data"),
        ({"is_in_progress": True, "is_hour_complete": False}, "in_progress"),
        ({"target_roi": None}, "target_not_configured"),
        ({"current_spend": Decimal("1")}, "insufficient_sample"),
        ({"data_valid": False}, "invalid_data"),
    ]
    for overrides, reason in cases:
        status = evaluate_hourly_status(status_input(**overrides))
        assert status.code == "unable_to_judge"
        assert status.level == "neutral"
        assert reason in status.reason_codes
        assert status.should_push is False
