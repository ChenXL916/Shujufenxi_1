from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.domain.cleaning import (
    invalid_live_record_reason,
    normalize_hour_slot,
    normalize_person_name,
    parse_business_datetime,
    parse_decimal,
    plain_text_value,
    unpivot_anchor_schedule,
    unpivot_staff_schedule,
)
from app.domain.metrics import MetricCatalog
from app.integrations.excel.reader import FixtureRecord, iter_fixture_records
from app.models.entities import (
    AnchorSchedule,
    LivePoint,
    LivePointMetric,
    Person,
    RawSourceRecord,
    Room,
    SourceConfig,
    StaffSchedule,
    SyncRun,
)


@dataclass(frozen=True)
class DatabaseImportReport:
    records_read: int
    records_created: int
    records_updated: int
    records_unchanged: int
    records_invalid: int


class FixtureImportService:
    def __init__(self, session: Session, catalog: MetricCatalog, schedule_year: int) -> None:
        self.session = session
        self.catalog = catalog
        self.schedule_year = schedule_year

    def import_workbook(self, path: Path) -> DatabaseImportReport:
        grouped: dict[tuple[str, str], list[FixtureRecord]] = defaultdict(list)
        for record in iter_fixture_records(path):
            sheet_name = record.source_record_id.rsplit(":", 1)[0]
            grouped[(record.source_role, sheet_name)].append(record)

        totals = {"created": 0, "updated": 0, "unchanged": 0, "invalid": 0}
        for (role, sheet_name), records in grouped.items():
            source = self._source(path.name, sheet_name, role, records[0].default_room_name)
            run_counts = {"created": 0, "updated": 0, "unchanged": 0, "invalid": 0}
            run = SyncRun(
                source_config_id=source.id,
                mode="fixture",
                status="running",
                triggered_by="fixture-import",
            )
            self.session.add(run)
            for record in records:
                status, raw = self._upsert_raw(source, record)
                totals[status] += 1
                run_counts[status] += 1
                if status == "unchanged":
                    if role == "live_actual" and self._live_point_needs_refresh(raw, record):
                        invalid = int(self._normalize_live(raw, record))
                        totals["invalid"] += invalid
                        run_counts["invalid"] += invalid
                    elif role == "anchor_schedule":
                        self._normalize_anchor_schedule(source, record)
                    elif role == "staff_schedule":
                        self._normalize_staff_schedule(source, record)
                    continue
                if role == "live_actual":
                    invalid = int(self._normalize_live(raw, record))
                    totals["invalid"] += invalid
                    run_counts["invalid"] += invalid
                elif role == "anchor_schedule":
                    self._normalize_anchor_schedule(source, record)
                elif role == "staff_schedule":
                    self._normalize_staff_schedule(source, record)
            run.status = "success"
            run.finished_at = utc_now()
            run.records_read = len(records)
            run.records_created = run_counts["created"]
            run.records_updated = run_counts["updated"]
            run.records_unchanged = run_counts["unchanged"]
            run.records_invalid = run_counts["invalid"]
            source.last_sync_at = run.finished_at
            source.last_success_at = run.finished_at
        self.session.commit()
        return DatabaseImportReport(
            records_read=sum(len(records) for records in grouped.values()),
            records_created=totals["created"],
            records_updated=totals["updated"],
            records_unchanged=totals["unchanged"],
            records_invalid=totals["invalid"],
        )

    def import_records(
        self,
        source: SourceConfig,
        records: list[FixtureRecord],
        mode: str = "feishu_api",
        triggered_by: str = "scheduled-sync",
        *,
        commit: bool = True,
    ) -> DatabaseImportReport:
        """Normalize API-shaped records through the same audited pipeline as fixtures."""
        counts = {"created": 0, "updated": 0, "unchanged": 0, "invalid": 0}
        run = SyncRun(
            source_config_id=source.id,
            mode=mode,
            status="running",
            triggered_by=triggered_by,
        )
        self.session.add(run)
        for record in records:
            status, raw = self._upsert_raw(source, record)
            counts[status] += 1
            if status == "unchanged":
                if record.source_role == "live_actual" and self._live_point_needs_refresh(
                    raw, record
                ):
                    counts["invalid"] += int(self._normalize_live(raw, record))
                elif record.source_role == "anchor_schedule":
                    self._normalize_anchor_schedule(source, record)
                elif record.source_role == "staff_schedule":
                    self._normalize_staff_schedule(source, record)
                continue
            if record.source_role == "live_actual":
                counts["invalid"] += int(self._normalize_live(raw, record))
            elif record.source_role == "anchor_schedule":
                self._normalize_anchor_schedule(source, record)
            elif record.source_role == "staff_schedule":
                self._normalize_staff_schedule(source, record)
        self._reconcile_snapshot(source, {record.source_record_id for record in records})
        run.status = "success"
        run.finished_at = utc_now()
        run.records_read = len(records)
        run.records_created = counts["created"]
        run.records_updated = counts["updated"]
        run.records_unchanged = counts["unchanged"]
        run.records_invalid = counts["invalid"]
        source.last_sync_at = run.finished_at
        source.last_success_at = run.finished_at
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return DatabaseImportReport(
            records_read=len(records),
            records_created=counts["created"],
            records_updated=counts["updated"],
            records_unchanged=counts["unchanged"],
            records_invalid=counts["invalid"],
        )

    def _source(
        self,
        filename: str,
        sheet_name: str,
        role: str,
        default_room_name: str | None,
    ) -> SourceConfig:
        source = self.session.scalar(
            select(SourceConfig).where(
                SourceConfig.source_type == "excel_fixture",
                SourceConfig.app_token == filename,
                SourceConfig.table_id == sheet_name,
                SourceConfig.source_role == role,
            )
        )
        if source is None:
            source = SourceConfig(
                name=f"{filename}/{sheet_name}",
                source_type="excel_fixture",
                source_role=role,
                app_token=filename,
                table_id=sheet_name,
                view_id=None,
                default_room_name=default_room_name,
                schedule_year=self.schedule_year if role != "live_actual" else None,
                field_mapping={},
            )
            self.session.add(source)
            self.session.flush()
        return source

    def _upsert_raw(
        self, source: SourceConfig, record: FixtureRecord
    ) -> tuple[str, RawSourceRecord]:
        raw = self.session.scalar(
            select(RawSourceRecord).where(
                RawSourceRecord.source_config_id == source.id,
                RawSourceRecord.source_record_id == record.source_record_id,
            )
        )
        now = utc_now()
        if raw is None:
            raw = RawSourceRecord(
                source_config_id=source.id,
                source_record_id=record.source_record_id,
                source_created_at=None,
                source_modified_at=None,
                raw_fields=record.raw_fields,
                payload_hash=record.payload_hash,
                is_deleted=False,
                first_seen_at=now,
                last_seen_at=now,
            )
            self.session.add(raw)
            self.session.flush()
            return "created", raw
        if raw.payload_hash == record.payload_hash and not raw.is_deleted:
            raw.last_seen_at = now
            return "unchanged", raw
        raw.raw_fields = record.raw_fields
        raw.payload_hash = record.payload_hash
        raw.last_seen_at = now
        raw.is_deleted = False
        return "updated", raw

    def _reconcile_snapshot(self, source: SourceConfig, seen_record_ids: set[str]) -> None:
        missing = list(
            self.session.scalars(
                select(RawSourceRecord).where(
                    RawSourceRecord.source_config_id == source.id,
                    RawSourceRecord.source_record_id.not_in(seen_record_ids),
                    RawSourceRecord.is_deleted.is_(False),
                )
            )
        )
        if not missing:
            return
        missing_ids = {record.source_record_id for record in missing}
        for record in missing:
            record.is_deleted = True
        if source.source_role == "live_actual":
            raw_ids = {record.id for record in missing}
            for point in self.session.scalars(
                select(LivePoint).where(LivePoint.raw_source_record_id.in_(raw_ids))
            ):
                point.valid = False
                point.invalid_reason = "source_deleted"
        elif source.source_role == "anchor_schedule":
            self.session.execute(
                delete(AnchorSchedule).where(
                    AnchorSchedule.source_config_id == source.id,
                    AnchorSchedule.source_record_id.in_(missing_ids),
                )
            )
        elif source.source_role == "staff_schedule":
            self.session.execute(
                delete(StaffSchedule).where(
                    StaffSchedule.source_config_id == source.id,
                    StaffSchedule.source_record_id.in_(missing_ids),
                )
            )

    def _room(self, name: str) -> Room:
        normalized_name = self._room_key(name)
        room = next(
            (
                candidate
                for candidate in self.session.scalars(select(Room))
                if normalized_name
                in {
                    self._room_key(candidate.name),
                    *(self._room_key(alias) for alias in candidate.source_aliases),
                }
            ),
            None,
        )
        if room is None:
            room = Room(
                name=name,
                brand=name.split("-", 1)[0] if "-" in name else None,
                category=name.split("-", 1)[1] if "-" in name else None,
                active=True,
                confirmed=False,
                source_aliases=[name],
            )
            self.session.add(room)
            self.session.flush()
        elif name not in room.source_aliases:
            room.source_aliases = [*room.source_aliases, name]
        return room

    @staticmethod
    def _room_key(name: str) -> str:
        normalized = unicodedata.normalize("NFKC", name).casefold().strip()
        return re.sub(r"[\s_\-‐‑‒–—]+", "", normalized)

    def _person(self, raw_name: str, role: str, status: str | None = None) -> Person:
        normalized = normalize_person_name(raw_name)
        base_name = normalized.base_name if normalized else raw_name
        person = self.session.scalar(select(Person).where(Person.base_name == base_name))
        if person is None:
            person = Person(
                display_name=normalized.canonical if normalized else raw_name,
                base_name=base_name,
                prefix=normalized.prefix if normalized else None,
                primary_role=role,
                employment_status=status,
                active=True,
                notes=None,
            )
            self.session.add(person)
            self.session.flush()
        return person

    def _normalize_live(self, raw: RawSourceRecord, record: FixtureRecord) -> bool:
        fields = record.raw_fields
        reason = invalid_live_record_reason(fields)
        try:
            observed_at = parse_business_datetime(fields.get("时间"))
        except ValueError:
            return True
        room_name = str(
            record.default_room_name or plain_text_value(fields.get("直播间")) or "待确认直播间"
        )
        room = self._room(room_name)
        try:
            slot = normalize_hour_slot(fields.get("时段"), observed_at.date())
        except ValueError:
            slot = None
        anchor_text = plain_text_value(fields.get("主播"))
        control_text = plain_text_value(fields.get("场控"))
        auto_check = plain_text_value(fields.get("自动检查"))
        anchor = normalize_person_name(anchor_text)
        control = normalize_person_name(control_text)
        point = self.session.scalar(
            select(LivePoint).where(LivePoint.raw_source_record_id == raw.id)
        )
        values: dict[str, Any] = {
            "room_id": room.id,
            "observed_at": observed_at,
            "business_date": observed_at.date(),
            "year": observed_at.year,
            "month": observed_at.month,
            "hour_slot": slot.label if slot else None,
            "hour_order": slot.order if slot else None,
            "anchor_raw": anchor_text or None,
            "anchor_canonical": anchor.canonical if anchor else None,
            "anchor_base_name": anchor.base_name if anchor else None,
            "anchor_members": list(anchor.members) if anchor else [],
            "anchor_note": anchor.note if anchor else None,
            "control_raw": control_text or None,
            "control_canonical": control.canonical if control else None,
            "control_base_name": control.base_name if control else None,
            "auto_check_status": auto_check or None,
            "valid": reason is None,
            "invalid_reason": reason,
            "raw_payload": fields,
        }
        if point is None:
            point = LivePoint(raw_source_record_id=raw.id, **values)
            self.session.add(point)
            self.session.flush()
        else:
            for key, value in values.items():
                setattr(point, key, value)
            self.session.query(LivePointMetric).filter(
                LivePointMetric.live_point_id == point.id
            ).delete()
        if reason is None:
            for spec in self.catalog.specs:
                value = fields.get(spec.field)
                try:
                    parsed = parse_decimal(value)
                    status = "parsed" if parsed is not None else "empty"
                except ValueError:
                    parsed = None
                    status = "invalid"
                self.session.add(
                    LivePointMetric(
                        live_point_id=point.id,
                        metric_key=spec.key,
                        numeric_value=parsed,
                        raw_value=str(value) if value is not None else None,
                        parse_status=status,
                    )
                )
        return reason is not None

    def _live_point_needs_refresh(self, raw: RawSourceRecord, record: FixtureRecord) -> bool:
        expected_name = str(
            record.default_room_name
            or plain_text_value(record.raw_fields.get("直播间"))
            or "待确认直播间"
        )
        expected_room = self.session.scalar(select(Room).where(Room.name == expected_name))
        point = self.session.scalar(
            select(LivePoint).where(LivePoint.raw_source_record_id == raw.id)
        )
        expected_reason = invalid_live_record_reason(record.raw_fields)
        expected_auto_check = plain_text_value(record.raw_fields.get("自动检查")) or None
        return (
            point is None
            or expected_room is None
            or point.room_id != expected_room.id
            or point.invalid_reason != expected_reason
            or point.auto_check_status != expected_auto_check
        )

    def _normalize_anchor_schedule(self, source: SourceConfig, record: FixtureRecord) -> None:
        self.session.execute(
            delete(AnchorSchedule).where(
                AnchorSchedule.source_config_id == source.id,
                AnchorSchedule.source_record_id == record.source_record_id,
            )
        )
        for row in unpivot_anchor_schedule(record.raw_fields, self.schedule_year):
            room = self._room(row.room_name)
            schedule = self.session.scalar(
                select(AnchorSchedule).where(
                    AnchorSchedule.room_id == room.id,
                    AnchorSchedule.schedule_date == row.schedule_date,
                    AnchorSchedule.hour_slot == row.hour_slot,
                )
            )
            values: dict[str, Any] = {
                "source_config_id": source.id,
                "source_record_id": record.source_record_id,
                "year": row.schedule_date.year,
                "month": row.schedule_date.month,
                "day": row.schedule_date.day,
                "hour_order": row.hour_order,
                "planned_anchor_raw": row.planned_anchor_raw,
                "planned_anchor_canonical": row.planned_anchor_canonical,
                "planned_anchor_base_names": list(row.planned_anchor_base_names),
                "schedule_status": row.schedule_status,
                "note": None,
            }
            if schedule is None:
                self.session.add(
                    AnchorSchedule(
                        room_id=room.id,
                        schedule_date=row.schedule_date,
                        hour_slot=row.hour_slot,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(schedule, key, value)

    def _normalize_staff_schedule(self, source: SourceConfig, record: FixtureRecord) -> None:
        self.session.execute(
            delete(StaffSchedule).where(
                StaffSchedule.source_config_id == source.id,
                StaffSchedule.source_record_id == record.source_record_id,
            )
        )
        for row in unpivot_staff_schedule(record.raw_fields, self.schedule_year):
            person = self._person(row.person_name, row.role, row.employment_status)
            schedule = self.session.scalar(
                select(StaffSchedule).where(
                    StaffSchedule.person_id == person.id,
                    StaffSchedule.schedule_date == row.schedule_date,
                )
            )
            values: dict[str, Any] = {
                "source_config_id": source.id,
                "source_record_id": record.source_record_id,
                "role": row.role,
                "employment_status": row.employment_status,
                "shift_raw": row.shift.name,
                "shift_name": row.shift.name,
                "shift_start": row.shift.start,
                "shift_end": row.shift.end,
                "crosses_midnight": row.shift.crosses_midnight,
                "is_rest": row.shift.is_rest,
                "time_configured": row.shift.time_configured,
            }
            if schedule is None:
                self.session.add(
                    StaffSchedule(
                        person_id=person.id,
                        schedule_date=row.schedule_date,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(schedule, key, value)
