from app.domain.data_freshness import fact_counts_toward_completeness, schedule_expects_data


def test_schedule_expectation_excludes_unassigned_off_air_and_unknown() -> None:
    assert schedule_expects_data("scheduled") is True
    assert schedule_expects_data("unassigned") is False
    assert schedule_expects_data("off_air") is False
    assert schedule_expects_data(None) is False


def test_complete_fact_counts_even_without_schedule() -> None:
    assert fact_counts_toward_completeness("complete", "unassigned") is True
    assert fact_counts_toward_completeness("missing", "scheduled") is True
    assert fact_counts_toward_completeness("missing", "unassigned") is False
