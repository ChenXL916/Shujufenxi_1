from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.aggregation import safe_divide


@dataclass(frozen=True)
class ComparisonResult:
    current_value: Decimal | None
    baseline_value: Decimal | None
    delta_value: Decimal | None
    ratio: Decimal | None
    ratio_percent: Decimal | None
    growth_percent: Decimal | None
    direction_status: str
    explanation: str


class ComparisonService:
    def compare(
        self,
        current: Decimal | None,
        baseline: Decimal | None,
        *,
        metric_label: str,
        baseline_label: str = "基准同小时",
    ) -> ComparisonResult:
        if current is None or baseline is None or baseline == Decimal(0):
            return ComparisonResult(
                current,
                baseline,
                None,
                None,
                None,
                None,
                "not_comparable",
                "无有效可比基准",
            )
        delta = current - baseline
        ratio = safe_divide(current, baseline)
        assert ratio is not None
        ratio_percent = ratio * Decimal(100)
        growth_percent = safe_divide(delta, baseline)
        assert growth_percent is not None
        growth_percent *= Decimal(100)
        status = "up" if delta > 0 else "down" if delta < 0 else "flat"
        verb = "提升" if delta >= 0 else "下降"
        explanation = (
            f"当前{metric_label}是{baseline_label}的{self._percent(ratio_percent)}，"
            f"较基准{verb}{self._percent(abs(growth_percent))}。"
        )
        return ComparisonResult(
            current,
            baseline,
            delta,
            ratio,
            ratio_percent,
            growth_percent,
            status,
            explanation,
        )

    @staticmethod
    def _percent(value: Decimal) -> str:
        quantized = value.quantize(Decimal("0.01"))
        return f"{format(quantized, 'f').rstrip('0').rstrip('.')}%"
