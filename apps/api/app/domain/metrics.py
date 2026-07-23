from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MetricSpec:
    key: str
    field: str
    category: str
    unit: str
    precision: int
    scope: str
    aggregation: str
    direction: str
    numerator: str | None = None
    denominator: str | None = None
    default: bool = False
    analysis_default: bool = False
    supports_hourly_trend: bool = False
    supports_kline: bool = False
    alertable: bool = False
    is_cumulative: bool = False


class MetricCatalog:
    def __init__(self, specs: tuple[MetricSpec, ...], dimensions: tuple[str, ...]) -> None:
        self.specs = specs
        self.dimensions = dimensions
        self.by_key = {spec.key: spec for spec in specs}
        self.by_field = {spec.field: spec for spec in specs}

    @classmethod
    def from_yaml(cls, path: Path) -> MetricCatalog:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        specs = tuple(cls._spec(item) for item in payload["metrics"])
        return cls(specs, tuple(payload["dimensions"]))

    @staticmethod
    def _spec(item: dict[str, Any]) -> MetricSpec:
        scope = str(item["scope"])
        aggregation = str(item["aggregation"])
        default_hourly_support = scope in {"period", "derived"} and aggregation != "NONE"
        return MetricSpec(
            key=str(item["key"]),
            field=str(item["field"]),
            category=str(item["category"]),
            unit=str(item["unit"]),
            precision=int(item["precision"]),
            scope=scope,
            aggregation=aggregation,
            direction=str(item["direction"]),
            numerator=str(item["numerator"]) if item.get("numerator") else None,
            denominator=str(item["denominator"]) if item.get("denominator") else None,
            default=bool(item.get("default", False)),
            analysis_default=bool(item.get("analysis_default", False)),
            supports_hourly_trend=bool(item.get("supports_hourly_trend", default_hourly_support)),
            supports_kline=bool(item.get("supports_kline", default_hourly_support)),
            alertable=bool(item.get("alertable", False)),
            is_cumulative=scope == "cumulative",
        )
