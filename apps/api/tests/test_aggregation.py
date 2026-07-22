from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.aggregation import MetricObservation, aggregate_metric, safe_divide
from app.domain.metrics import MetricCatalog
from app.services.comparison_service import ComparisonService

ROOT = Path(__file__).resolve().parents[3]
CATALOG = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")


def observation(metric: str, value: str, hour: int, day: int = 8) -> MetricObservation:
    return MetricObservation("room", date(2026, 7, day), hour, metric, Decimal(value))


def test_roi_and_order_cost_use_ratio_of_sums() -> None:
    rows = [
        observation("period_overall_amount", "300", 8),
        observation("period_spend", "100", 8),
        observation("period_overall_orders", "10", 8),
        observation("period_overall_amount", "100", 9),
        observation("period_spend", "300", 9),
        observation("period_overall_orders", "20", 9),
    ]

    assert aggregate_metric("period_overall_roi", rows, CATALOG) == Decimal("1")
    assert aggregate_metric("period_overall_order_cost", rows, CATALOG) == Decimal("400") / Decimal(
        "30"
    )


def test_period_view_conversion_rate_uses_ratio_of_sums() -> None:
    rows = [
        observation("period_buyers", "1", 8),
        observation("period_viewers", "10", 8),
        observation("period_buyers", "9", 9),
        observation("period_viewers", "30", 9),
    ]

    assert aggregate_metric("period_view_conversion_rate", rows, CATALOG) == Decimal("0.25")


def test_cumulative_metric_uses_last_point_per_room_day() -> None:
    rows = [
        observation("room_gmv", "100", 8),
        observation("room_gmv", "180", 9),
        observation("room_gmv", "50", 8, day=9),
    ]

    assert aggregate_metric("room_gmv", rows, CATALOG) == Decimal("230")


def test_division_by_zero_returns_none() -> None:
    assert safe_divide(Decimal("3"), Decimal(0)) is None
    assert safe_divide(None, Decimal("1")) is None


def test_three_vs_one_point_five_comparison_copy_is_exact() -> None:
    result = ComparisonService().compare(Decimal("3.00"), Decimal("1.50"), metric_label="ROI")

    assert result.ratio_percent == Decimal("200")
    assert result.growth_percent == Decimal("100")
    assert result.explanation == "当前ROI是基准同小时的200%，较基准提升100%。"


def test_zero_baseline_is_not_comparable() -> None:
    result = ComparisonService().compare(Decimal("3"), Decimal(0), metric_label="ROI")
    assert result.ratio is None
    assert result.explanation == "无有效可比基准"
