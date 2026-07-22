from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.metrics import MetricCatalog, MetricSpec


@dataclass(frozen=True)
class MetricObservation:
    room_id: str
    business_date: date
    hour_order: int
    metric_key: str
    value: Decimal | None


def safe_divide(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == Decimal(0):
        return None
    return numerator / denominator


def aggregate_metric(
    metric_key: str,
    observations: list[MetricObservation],
    catalog: MetricCatalog,
) -> Decimal | None:
    spec = catalog.by_key[metric_key]
    if spec.aggregation == "RATIO_OF_SUMS":
        if not spec.numerator or not spec.denominator:
            return None
        return safe_divide(
            aggregate_metric(spec.numerator, observations, catalog),
            aggregate_metric(spec.denominator, observations, catalog),
        )
    relevant = [
        item for item in observations if item.metric_key == metric_key and item.value is not None
    ]
    if not relevant:
        return None
    if spec.aggregation == "SUM":
        return sum((item.value for item in relevant if item.value is not None), Decimal(0))
    if spec.aggregation == "LAST_PER_ROOM_DAY":
        latest: dict[tuple[str, date], MetricObservation] = {}
        for item in relevant:
            key = (item.room_id, item.business_date)
            if key not in latest or item.hour_order > latest[key].hour_order:
                latest[key] = item
        return sum((item.value for item in latest.values() if item.value is not None), Decimal(0))
    if spec.aggregation in {"LAST", "MAX", "AVG"}:
        ordered = sorted(relevant, key=lambda item: (item.business_date, item.hour_order))
        if spec.aggregation == "LAST":
            return ordered[-1].value
        values = [item.value for item in ordered if item.value is not None]
        if spec.aggregation == "MAX":
            return max(values)
        return safe_divide(sum(values, Decimal(0)), Decimal(len(values)))
    return None


def hourly_value(
    spec: MetricSpec, latest_values: dict[str, Decimal | None]
) -> tuple[Decimal | None, str]:
    if spec.aggregation == "RATIO_OF_SUMS" and spec.numerator and spec.denominator:
        return (
            safe_divide(latest_values.get(spec.numerator), latest_values.get(spec.denominator)),
            "computed",
        )
    return latest_values.get(spec.key), "latest_point"
