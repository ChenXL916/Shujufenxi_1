from decimal import Decimal

from app.services.analysis_service import AnalysisService


def test_hourly_average_amount_uses_decimal_and_valid_hours() -> None:
    assert AnalysisService._hourly_average_amount(Decimal("1000.50"), 3) == Decimal("333.50")


def test_hourly_average_amount_is_empty_without_amount_or_valid_hours() -> None:
    assert AnalysisService._hourly_average_amount(None, 3) is None
    assert AnalysisService._hourly_average_amount(Decimal("100"), 0) is None
