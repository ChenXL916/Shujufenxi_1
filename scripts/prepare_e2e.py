from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    HourlyFact,
    HourlyMetric,
    LivePoint,
    LivePointMetric,
    RawSourceRecord,
    Room,
    SourceConfig,
)
from app.services.fixture_import_service import FixtureImportService
from app.services.hourly_fact_service import HourlyFactService
from app.services.seed_service import seed_reference_data

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "e2e.db"
BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def ensure_anchor_trend_seed_facts(session: Session) -> list[Room]:
    rooms = list(session.scalars(select(Room).order_by(Room.name).limit(3)))
    while len(rooms) < 3:
        room = Room(
            name=f"E2E 测试直播间 {len(rooms) + 1}",
            brand="E2E",
            category="测试",
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add(room)
        session.flush()
        rooms.append(room)

    source = session.scalar(select(SourceConfig).limit(1))
    if source is None:
        source = SourceConfig(
            name="E2E 匿名测试数据源",
            source_type="excel_fixture",
            source_role="live_actual",
            app_token=secrets.token_urlsafe(12),
            table_id="synthetic-live",
            view_id=None,
            default_room_name=rooms[0].name,
            schedule_year=None,
            field_mapping={},
            enabled=True,
        )
        session.add(source)
        session.flush()

    seed_dates = [date(2026, 7, 8), *(date(2026, 7, 12) + timedelta(days=i) for i in range(6))]
    for room in rooms:
        for business_date in seed_dates:
            for hour_order in (8, 9):
                hour_slot = f"{hour_order:02d}-{hour_order + 1:02d}"
                fact = session.scalar(
                    select(HourlyFact).where(
                        HourlyFact.room_id == room.id,
                        HourlyFact.business_date == business_date,
                        HourlyFact.hour_slot == hour_slot,
                    )
                )
                if fact is not None:
                    continue
                hour_start = datetime.combine(
                    business_date,
                    time(hour_order),
                    tzinfo=BUSINESS_TIMEZONE,
                )
                session.add(
                    HourlyFact(
                        room_id=room.id,
                        business_date=business_date,
                        year=business_date.year,
                        month=business_date.month,
                        hour_slot=hour_slot,
                        hour_order=hour_order,
                        hour_start_at=hour_start,
                        hour_end_at=hour_start + timedelta(hours=1),
                        latest_point_id=None,
                        latest_observed_at=hour_start + timedelta(hours=1),
                        actual_anchor_canonical=None,
                        actual_anchor_base_names=[],
                        actual_control_canonical=None,
                        planned_anchor_canonical=None,
                        planned_anchor_base_names=[],
                        anchor_schedule_status=None,
                        anchor_match_status="no_schedule",
                        control_shift_name=None,
                        control_is_scheduled=None,
                        control_is_rest=None,
                        control_may_be_on_duty=None,
                        data_status="complete",
                    )
                )

    if (
        session.scalar(select(LivePoint.id).where(LivePoint.business_date == date(2026, 7, 8)))
        is None
    ):
        for room_index, room in enumerate(rooms, start=1):
            for hour_order in (8, 9):
                hour_slot = f"{hour_order:02d}-{hour_order + 1:02d}"
                observed_at = datetime.combine(
                    date(2026, 7, 8),
                    time(hour_order, 30),
                    tzinfo=BUSINESS_TIMEZONE,
                )
                raw = RawSourceRecord(
                    source_config_id=source.id,
                    source_record_id=f"synthetic:{room_index}:{hour_slot}",
                    source_created_at=None,
                    source_modified_at=None,
                    raw_fields={"时间": observed_at.isoformat(), "时段": hour_slot},
                    payload_hash=f"{room_index:02d}{hour_order:02d}".ljust(64, "0"),
                    is_deleted=False,
                )
                session.add(raw)
                session.flush()
                anchor_name = f"E2E主播{room_index}"
                point = LivePoint(
                    raw_source_record_id=raw.id,
                    room_id=room.id,
                    observed_at=observed_at,
                    business_date=observed_at.date(),
                    year=observed_at.year,
                    month=observed_at.month,
                    hour_slot=hour_slot,
                    hour_order=hour_order,
                    anchor_raw=anchor_name,
                    anchor_canonical=anchor_name,
                    anchor_base_name=anchor_name,
                    anchor_members=[anchor_name],
                    anchor_note=None,
                    control_raw="E2E场控",
                    control_canonical="E2E场控",
                    control_base_name="E2E场控",
                    auto_check_status="正确",
                    valid=True,
                    invalid_reason=None,
                    raw_payload={"时间": observed_at.isoformat(), "时段": hour_slot},
                )
                session.add(point)
                session.flush()
                for metric_key, value in (
                    ("period_spend", Decimal("100")),
                    ("period_overall_amount", Decimal("200")),
                    ("period_overall_roi", Decimal("2")),
                ):
                    session.add(
                        LivePointMetric(
                            live_point_id=point.id,
                            metric_key=metric_key,
                            numeric_value=value,
                            raw_value=str(value),
                            parse_status="parsed",
                        )
                    )
    session.flush()
    return rooms


def seed_anchor_trend_examples(session: Session) -> None:
    rooms = ensure_anchor_trend_seed_facts(session)

    period_end = date(2026, 7, 17)
    period_start = period_end - timedelta(days=5)
    examples = (
        (rooms[0], "E2E上涨主播", Decimal("1"), Decimal("2")),
        (rooms[1], "E2E下跌主播", Decimal("2"), Decimal("1")),
        (rooms[2], "E2E样本不足主播", None, Decimal("1")),
    )
    for room, anchor_name, baseline_roi, current_roi in examples:
        for business_date in [
            date(2026, 7, 8),
            *(period_start + timedelta(days=i) for i in range(6)),
        ]:
            is_current = business_date >= period_end - timedelta(days=2)
            if baseline_roi is None and not is_current:
                continue
            spend = Decimal("150") if is_current else Decimal("100")
            roi = current_roi if is_current else baseline_roi
            if roi is None:
                raise RuntimeError("E2E 主播趋势 ROI 样例缺失")
            for hour_slot in ("08-09", "09-10"):
                fact = session.scalar(
                    select(HourlyFact).where(
                        HourlyFact.room_id == room.id,
                        HourlyFact.business_date == business_date,
                        HourlyFact.hour_slot == hour_slot,
                    )
                )
                if fact is None:
                    raise RuntimeError(
                        f"E2E 小时事实不存在: {room.name} {business_date} {hour_slot}"
                    )
                fact.actual_anchor_canonical = anchor_name
                fact.actual_anchor_base_names = [anchor_name]
                fact.actual_control_canonical = "E2E场控"
                fact.latest_observed_at = fact.hour_end_at
                fact.data_status = "complete"
                session.query(HourlyMetric).filter(HourlyMetric.hourly_fact_id == fact.id).delete(
                    synchronize_session=False
                )
                revenue = spend * roi
                for metric_key, value in (
                    ("period_spend", spend),
                    ("period_overall_amount", revenue),
                    ("period_overall_roi", roi),
                    ("overall_order_count", Decimal("10")),
                ):
                    session.add(
                        HourlyMetric(
                            hourly_fact_id=fact.id,
                            metric_key=metric_key,
                            numeric_value=value,
                            value_source="e2e_anchor_trend_fixture",
                            quality_status="valid",
                        )
                    )


def main() -> None:
    if DATABASE.exists():
        DATABASE.unlink()
    engine = create_engine(f"sqlite+pysqlite:///{DATABASE.as_posix()}")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
    with Session(engine) as session:
        seed_reference_data(session, ROOT, "e2e@example.com")
        importer = FixtureImportService(session, catalog, schedule_year=2026)
        for path in sorted((ROOT / "fixtures").glob("*.xlsx")):
            importer.import_workbook(path)
        HourlyFactService(session, catalog).rebuild()
        seed_anchor_trend_examples(session)
        session.commit()
    print(f"E2E 数据库已准备: {DATABASE}")


if __name__ == "__main__":
    main()
