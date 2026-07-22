from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.aggregation import hourly_value
from app.domain.cleaning import SHANGHAI
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    AnchorSchedule,
    HourlyFact,
    HourlyMetric,
    LivePoint,
    LivePointMetric,
    Person,
    RawSourceRecord,
    StaffSchedule,
)


class HourlyFactService:
    def __init__(self, session: Session, catalog: MetricCatalog) -> None:
        self.session = session
        self.catalog = catalog

    def rebuild(self, *, commit: bool = True) -> int:
        points = list(
            self.session.scalars(
                select(LivePoint)
                .join(
                    RawSourceRecord,
                    RawSourceRecord.id == LivePoint.raw_source_record_id,
                )
                .where(
                    LivePoint.valid.is_(True),
                    LivePoint.hour_slot.is_not(None),
                    RawSourceRecord.is_deleted.is_(False),
                )
            )
        )
        raw_records = {
            record.id: record
            for record in self.session.scalars(
                select(RawSourceRecord).where(
                    RawSourceRecord.id.in_({point.raw_source_record_id for point in points})
                )
            )
        }
        metrics = list(self.session.scalars(select(LivePointMetric)))
        metrics_by_point: dict[Any, dict[str, Decimal | None]] = defaultdict(dict)
        for metric in metrics:
            metrics_by_point[metric.live_point_id][metric.metric_key] = metric.numeric_value
        schedules = list(self.session.scalars(select(AnchorSchedule)))
        schedule_map = {
            (schedule.room_id, schedule.schedule_date, schedule.hour_slot): schedule
            for schedule in schedules
        }
        staff_map = self._staff_map()
        groups: dict[tuple[Any, Any, str], list[LivePoint]] = defaultdict(list)
        for point in points:
            if point.hour_slot is not None:
                groups[(point.room_id, point.business_date, point.hour_slot)].append(point)

        count = 0
        actual_keys: set[tuple[Any, Any, str]] = set()
        for key, group in groups.items():
            actual_keys.add(key)
            group.sort(key=lambda point: self._point_recency_key(point, raw_records))
            latest = group[-1]
            schedule = schedule_map.get(key)
            fact = self._upsert_fact(latest, schedule, staff_map)
            self._replace_metrics(fact, latest, metrics_by_point)
            count += 1

        for key, schedule in schedule_map.items():
            if key in actual_keys:
                continue
            missing_fact = self.session.scalar(
                select(HourlyFact).where(
                    HourlyFact.room_id == schedule.room_id,
                    HourlyFact.business_date == schedule.schedule_date,
                    HourlyFact.hour_slot == schedule.hour_slot,
                )
            )
            start = datetime.combine(
                schedule.schedule_date,
                datetime.min.time(),
                tzinfo=SHANGHAI,
            ) + timedelta(hours=schedule.hour_order)
            status = "off_air" if schedule.schedule_status == "off_air" else "scheduled_but_missing"
            values: dict[str, Any] = {
                "year": schedule.schedule_date.year,
                "month": schedule.schedule_date.month,
                "hour_order": schedule.hour_order,
                "hour_start_at": start,
                "hour_end_at": start + timedelta(hours=1),
                "latest_point_id": None,
                "latest_observed_at": None,
                "actual_anchor_canonical": None,
                "actual_anchor_base_names": [],
                "actual_control_canonical": None,
                "planned_anchor_canonical": schedule.planned_anchor_canonical,
                "planned_anchor_base_names": schedule.planned_anchor_base_names,
                "anchor_schedule_status": schedule.schedule_status,
                "anchor_match_status": status,
                "control_shift_name": None,
                "control_is_scheduled": None,
                "control_is_rest": None,
                "control_may_be_on_duty": None,
                "data_status": "missing",
            }
            if missing_fact is None:
                missing_fact = HourlyFact(
                    room_id=schedule.room_id,
                    business_date=schedule.schedule_date,
                    hour_slot=schedule.hour_slot,
                    **values,
                )
                self.session.add(missing_fact)
                self.session.flush()
            else:
                for field, value in values.items():
                    setattr(missing_fact, field, value)
            self.session.execute(
                delete(HourlyMetric).where(HourlyMetric.hourly_fact_id == missing_fact.id)
            )
            count += 1

        active_keys = actual_keys | set(schedule_map)
        for fact in list(self.session.scalars(select(HourlyFact))):
            key = (fact.room_id, fact.business_date, fact.hour_slot)
            if key in active_keys:
                continue
            self.session.execute(delete(HourlyMetric).where(HourlyMetric.hourly_fact_id == fact.id))
            self.session.delete(fact)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return count

    def _upsert_fact(
        self,
        point: LivePoint,
        schedule: AnchorSchedule | None,
        staff_map: dict[tuple[str, Any], StaffSchedule],
    ) -> HourlyFact:
        assert point.hour_slot is not None and point.hour_order is not None
        fact = self.session.scalar(
            select(HourlyFact).where(
                HourlyFact.room_id == point.room_id,
                HourlyFact.business_date == point.business_date,
                HourlyFact.hour_slot == point.hour_slot,
            )
        )
        start = datetime.combine(
            point.business_date, datetime.min.time(), tzinfo=SHANGHAI
        ) + timedelta(hours=point.hour_order)
        staff = staff_map.get((point.control_base_name or "", point.business_date))
        values: dict[str, Any] = {
            "year": point.year,
            "month": point.month,
            "hour_order": point.hour_order,
            "hour_start_at": start,
            "hour_end_at": start + timedelta(hours=1),
            "latest_point_id": point.id,
            "latest_observed_at": point.observed_at,
            "actual_anchor_canonical": point.anchor_canonical,
            "actual_anchor_base_names": point.anchor_members,
            "actual_control_canonical": point.control_canonical,
            "planned_anchor_canonical": schedule.planned_anchor_canonical if schedule else None,
            "planned_anchor_base_names": schedule.planned_anchor_base_names if schedule else [],
            "anchor_schedule_status": schedule.schedule_status if schedule else None,
            "anchor_match_status": self._anchor_match(point, schedule),
            "control_shift_name": staff.shift_name if staff else None,
            "control_is_scheduled": staff is not None,
            "control_is_rest": staff.is_rest if staff else None,
            "control_may_be_on_duty": self._may_be_on_duty(staff, point.hour_order),
            "data_status": "complete",
        }
        if fact is None:
            fact = HourlyFact(
                room_id=point.room_id,
                business_date=point.business_date,
                hour_slot=point.hour_slot,
                **values,
            )
            self.session.add(fact)
            self.session.flush()
        else:
            for field, value in values.items():
                setattr(fact, field, value)
        return fact

    def _replace_metrics(
        self,
        fact: HourlyFact,
        point: LivePoint,
        metrics_by_point: dict[Any, dict[str, Decimal | None]],
    ) -> None:
        self.session.execute(delete(HourlyMetric).where(HourlyMetric.hourly_fact_id == fact.id))
        latest_values = metrics_by_point[point.id]
        for spec in self.catalog.specs:
            value, source = hourly_value(spec, latest_values)
            self.session.add(
                HourlyMetric(
                    hourly_fact_id=fact.id,
                    metric_key=spec.key,
                    numeric_value=value,
                    value_source=source,
                    quality_status="valid" if value is not None else "missing",
                )
            )

    def _staff_map(self) -> dict[tuple[str, Any], StaffSchedule]:
        people = {person.id: person for person in self.session.scalars(select(Person))}
        result: dict[tuple[str, Any], StaffSchedule] = {}
        for schedule in self.session.scalars(select(StaffSchedule)):
            person = people.get(schedule.person_id)
            if person:
                result[(person.base_name, schedule.schedule_date)] = schedule
        return result

    @staticmethod
    def _point_recency_key(
        point: LivePoint, raw_records: dict[Any, RawSourceRecord]
    ) -> tuple[str, str, str]:
        record = raw_records.get(point.raw_source_record_id)
        source_timestamp = (
            record.source_modified_at or record.source_created_at or record.first_seen_at
            if record
            else None
        )
        return (
            point.observed_at.isoformat(),
            source_timestamp.isoformat() if source_timestamp else "",
            str(point.id),
        )

    @staticmethod
    def _anchor_match(point: LivePoint, schedule: AnchorSchedule | None) -> str:
        if schedule is None:
            return "no_schedule"
        if schedule.schedule_status == "off_air":
            return "off_air_but_live"
        return (
            "matched"
            if sorted(point.anchor_members) == sorted(schedule.planned_anchor_base_names)
            else "mismatched"
        )

    @staticmethod
    def _may_be_on_duty(schedule: StaffSchedule | None, hour: int) -> bool | None:
        if schedule is None or schedule.is_rest:
            return False if schedule and schedule.is_rest else None
        if (
            not schedule.time_configured
            or schedule.shift_start is None
            or schedule.shift_end is None
        ):
            return None
        start, end = schedule.shift_start.hour, schedule.shift_end.hour
        return hour >= start or hour < end if schedule.crosses_midnight else start <= hour < end
