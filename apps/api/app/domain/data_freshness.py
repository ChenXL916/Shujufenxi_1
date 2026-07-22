from __future__ import annotations

from datetime import date, datetime, time, timedelta

NO_DATA_EXPECTED_STATUSES = frozenset({None, "unassigned", "off_air"})


def schedule_expects_data(anchor_schedule_status: str | None) -> bool:
    """Whether a schedule status represents an hour that requires actual data."""
    return anchor_schedule_status not in NO_DATA_EXPECTED_STATUSES


def fact_counts_toward_completeness(data_status: str, anchor_schedule_status: str | None) -> bool:
    """Include actual complete data or a scheduled hour that should have data."""
    return data_status == "complete" or schedule_expects_data(anchor_schedule_status)


def submission_deadline(business_date: date, deadline_hour: int) -> datetime:
    """Return the local, naive T+1 submission deadline for a business date."""
    return datetime.combine(business_date + timedelta(days=1), time(hour=deadline_hour))


def data_is_due(business_date: date, now: datetime, deadline_hour: int) -> bool:
    """Whether T+1 data is old enough to be judged as complete or missing."""
    local_now = now.replace(tzinfo=None) if now.tzinfo is not None else now
    return local_now >= submission_deadline(business_date, deadline_hour)
