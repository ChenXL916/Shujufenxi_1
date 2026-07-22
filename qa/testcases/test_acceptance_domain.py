from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.domain.data_freshness import data_is_due, submission_deadline
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

D = Decimal


def status_input(**overrides: object) -> HourlyStatusInput:
    values: dict[str, object] = {
        "current_roi": D("1.90"),
        "baseline_roi": D("1.40"),
        "current_spend": D("13000"),
        "baseline_spend": D("10000"),
        "target_roi": D("1.81"),
        "coverage_rate": D("1"),
        "minimum_coverage_rate": D("0.80"),
        "minimum_spend": D("0"),
        "current_orders": D("1"),
        "minimum_orders": 0,
        "is_hour_complete": True,
        "is_in_progress": False,
        "data_valid": True,
    }
    values.update(overrides)
    return HourlyStatusInput(**values)  # type: ignore[arg-type]


def test_fixed_24_hours_are_numeric_and_ordered() -> None:
    hours = hour_descriptors()
    assert len(hours) == 24
    assert [item.sort for item in hours] == list(range(24))
    assert hours[0].key == "00-01"
    assert hours[-1].key == "23-24"
    assert len({item.key for item in hours}) == 24


@pytest.mark.parametrize("days", [1, 3, 5, 7, 15, 30])
def test_period_formula_for_all_presets(days: int) -> None:
    periods = build_periods(date(2026, 7, 15), days)
    assert periods.current.days == days
    assert periods.current.end == date(2026, 7, 15)
    assert periods.comparison is not None
    assert periods.comparison.days == days
    assert periods.comparison.end == periods.current.start.replace() - __import__("datetime").timedelta(days=1)


@pytest.mark.parametrize(
    ("end", "days", "expected_start", "expected_comparison_end"),
    [
        (date(2026, 3, 1), 3, date(2026, 2, 27), date(2026, 2, 26)),
        (date(2026, 1, 2), 5, date(2025, 12, 29), date(2025, 12, 28)),
        (date(2024, 3, 1), 3, date(2024, 2, 28), date(2024, 2, 27)),
        (date(2024, 2, 29), 1, date(2024, 2, 29), date(2024, 2, 28)),
    ],
)
def test_period_month_year_and_leap_boundaries(
    end: date, days: int, expected_start: date, expected_comparison_end: date
) -> None:
    periods = build_periods(end, days)
    assert periods.current.start == expected_start
    assert periods.comparison is not None
    assert periods.comparison.end == expected_comparison_end


def test_custom_period_and_compare_off() -> None:
    periods = build_periods(
        date(2026, 7, 10), None, custom_start_date=date(2026, 6, 29), compare_enabled=False
    )
    assert periods.current.start == date(2026, 6, 29)
    assert periods.current.end == date(2026, 7, 10)
    assert periods.comparison is None


def test_invalid_custom_period_is_rejected() -> None:
    with pytest.raises(ValueError, match="开始日期"):
        build_periods(date(2026, 7, 1), None, custom_start_date=date(2026, 7, 2))


@pytest.mark.parametrize("days", [0, 2, 4, 6, 8, 31])
def test_invalid_period_presets_are_rejected(days: int) -> None:
    with pytest.raises(ValueError, match="周期"):
        build_periods(date(2026, 7, 15), days)


def test_ratio_of_sums_and_zero_denominator() -> None:
    assert ratio_of_sums([D("150"), D("300")], [D("100"), D("200")]) == D("1.5")
    assert ratio_of_sums([D("0")], [D("10")]) == D("0")
    assert ratio_of_sums([D("1")], [D("0")]) is None
    assert ratio_of_sums([None], [D("1")]) is None
    assert ratio_of_sums([D("1")], [None]) is None


def test_comparison_300_vs_150_has_two_distinct_percentages() -> None:
    result = compare_values(D("3.00"), D("1.50"))
    assert result.difference == D("1.50")
    assert result.current_to_baseline_ratio == D("2")
    assert result.current_to_baseline_percentage == D("200")
    assert result.growth_rate == D("1")
    assert result.growth_percentage == D("100")


@pytest.mark.parametrize(
    ("current", "baseline", "difference", "growth"),
    [
        (D("1"), D("1"), D("0"), D("0")),
        (D("0"), D("1"), D("-1"), D("-1")),
        (D("1"), D("0"), D("1"), None),
        (None, D("1"), None, None),
        (D("1"), None, None, None),
        (D("-1"), D("1"), D("-2"), D("-2")),
        (D("1E+30"), D("1E-30"), D("1E+30") - D("1E-30"), D("1E+60") - D("1")),
    ],
)
def test_comparison_edge_cases(
    current: Decimal | None,
    baseline: Decimal | None,
    difference: Decimal | None,
    growth: Decimal | None,
) -> None:
    result = compare_values(current, baseline)
    assert result.difference == difference
    assert result.growth_rate == growth


def test_roi_business_kline_fixed_example() -> None:
    values = [D("1.50"), D("1.90"), D("1.20"), D("2.10"), D("1.80")]
    result = build_business_kline(
        DailyValue(date(2026, 7, index + 1), value) for index, value in enumerate(values)
    )
    assert result is not None
    assert (result.open, result.close, result.high, result.low) == (
        D("1.50"), D("1.80"), D("2.10"), D("1.20")
    )
    assert result.effective_days == 5
    assert result.first_date == date(2026, 7, 1)
    assert result.last_date == date(2026, 7, 5)
    assert result.high_date == date(2026, 7, 4)
    assert result.low_date == date(2026, 7, 3)


def test_spend_business_kline_fixed_example() -> None:
    values = [D("10000"), D("13000"), D("9000"), D("14500"), D("11000")]
    result = build_business_kline(
        DailyValue(date(2026, 7, index + 1), value) for index, value in enumerate(values)
    )
    assert result is not None
    assert (result.open, result.close, result.high, result.low) == (
        D("10000"), D("11000"), D("14500"), D("9000")
    )


def test_kline_missing_boundaries_and_real_zero() -> None:
    result = build_business_kline(
        [
            DailyValue(date(2026, 7, 1), None),
            DailyValue(date(2026, 7, 2), D("0")),
            DailyValue(date(2026, 7, 3), D("2")),
            DailyValue(date(2026, 7, 4), None),
        ]
    )
    assert result is not None
    assert result.open == D("0")
    assert result.close == D("2")
    assert result.low == D("0")
    assert result.effective_days == 2
    assert build_business_kline([DailyValue(date(2026, 7, 1), None)]) is None


def test_target_name_matching_and_precedence() -> None:
    assert infer_product_category("Mistine-水散粉") == "水散粉"
    assert infer_product_category("柏瑞美-散粉") == "散粉"
    targets = [
        TargetCandidate(None, None, "散粉", D("1.81")),
        TargetCandidate(None, None, "水散粉", D("2.00")),
        TargetCandidate("room-1", None, None, D("1.95")),
    ]
    assert select_target("room-1", "柏瑞美-散粉", None, targets) == D("1.95")
    assert select_target("room-2", "Mistine-水散粉", None, targets) == D("2.00")
    assert select_target("room-3", "未配置", None, targets) is None
    assert common_target([D("1.81"), D("1.81")]) == D("1.81")
    assert common_target([D("1.81"), D("2.00")]) is None
    assert common_target([D("1.81"), None]) is None


def test_case_a_excellent_scaling() -> None:
    result = evaluate_hourly_status(status_input())
    assert result.code == "excellent_scaling"
    assert result.roi_target_reached is True
    assert result.roi_target_gap == D("0.09")
    assert result.should_push is True


def test_case_b_efficiency_deterioration_has_priority() -> None:
    result = evaluate_hourly_status(
        status_input(
            current_spend=D("13500"), baseline_spend=D("10000"),
            current_roi=D("1.65"), baseline_roi=D("1.70")
        )
    )
    assert result.code == "efficiency_deterioration"
    assert "roi_below_target" in result.reason_codes
    assert result.level == "critical"


def test_case_c_improving_below_target() -> None:
    result = evaluate_hourly_status(
        status_input(current_roi=D("1.50"), baseline_roi=D("1.10"), current_spend=D("10000"))
    )
    assert result.code == "improving_below_target"
    assert result.roi_growth == D("1.50") / D("1.10") - D("1")
    assert result.should_push is False


def test_case_d_severe_roi_drop_at_exact_boundary() -> None:
    result = evaluate_hourly_status(
        status_input(current_roi=D("1.40"), baseline_roi=D("2.00"), current_spend=D("10000"))
    )
    assert result.roi_growth == D("-0.30")
    assert result.code == "roi_severe_drop"
    assert result.level == "critical"


def test_case_e_zero_baseline_is_not_comparable() -> None:
    result = evaluate_hourly_status(status_input(baseline_roi=D("0")))
    assert result.code == "unable_to_judge"
    assert result.reason_codes == ("no_comparable_baseline",)
    assert result.roi_growth is None
    assert result.should_push is False


def test_case_f_incomplete_data_suppresses_alert() -> None:
    result = evaluate_hourly_status(status_input(coverage_rate=D("0.70")))
    assert result.code == "unable_to_judge"
    assert result.reason_codes == ("incomplete_data",)
    assert result.should_push is False


@pytest.mark.parametrize(
    ("growth_current", "expected"),
    [(D("1.29999"), "roi_target_reached"), (D("1.30000"), "roi_excellent_growth")],
)
def test_positive_30_percent_raw_boundary(growth_current: Decimal, expected: str) -> None:
    result = evaluate_hourly_status(
        status_input(
            current_roi=growth_current, baseline_roi=D("1"), target_roi=D("1"),
            current_spend=D("100"), baseline_spend=D("100")
        )
    )
    assert result.code == expected


@pytest.mark.parametrize(
    ("current", "expected"),
    [(D("0.70001"), "roi_below_target"), (D("0.70000"), "roi_severe_drop")],
)
def test_negative_30_percent_raw_boundary(current: Decimal, expected: str) -> None:
    result = evaluate_hourly_status(
        status_input(
            current_roi=current, baseline_roi=D("1"), target_roi=D("0.8"),
            current_spend=D("100"), baseline_spend=D("100")
        )
    )
    assert result.code == expected


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"is_in_progress": True}, "in_progress"),
        ({"is_hour_complete": False}, "in_progress"),
        ({"data_valid": False}, "invalid_data"),
        ({"coverage_rate": None}, "no_schedule_baseline"),
        ({"target_roi": None}, "target_not_configured"),
        ({"target_roi": D("0")}, "target_not_configured"),
        ({"current_spend": None}, "insufficient_sample"),
    ],
)
def test_unable_to_judge_guardrails(overrides: dict[str, object], reason: str) -> None:
    result = evaluate_hourly_status(status_input(**overrides))
    assert result.code == "unable_to_judge"
    assert result.reason_codes == (reason,)
    assert result.should_push is False


def test_t_plus_one_deadline_asia_shanghai_boundary() -> None:
    business_date = date(2026, 7, 15)
    assert submission_deadline(business_date, 8) == datetime(2026, 7, 16, 8, 0)
    before = datetime(2026, 7, 16, 7, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    at = datetime(2026, 7, 16, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert data_is_due(business_date, before, 8) is False
    assert data_is_due(business_date, at, 8) is True
