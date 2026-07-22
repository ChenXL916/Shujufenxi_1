from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.metrics import MetricCatalog
from app.models.entities import (
    AnchorSchedule,
    HourlyFact,
    HourlyMetric,
    LivePoint,
    LivePointMetric,
    RawSourceRecord,
    Room,
    SourceConfig,
)
from app.services.hourly_fact_service import HourlyFactService

ROOT = Path(__file__).resolve().parents[3]
CATALOG = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_rebuild_removes_stale_metrics_when_an_hour_becomes_missing() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        room = Room(
            name="事实重建测试直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        source = SourceConfig(
            name="测试排班源",
            source_type="fixture",
            source_role="anchor_schedule",
            app_token="fixture",  # noqa: S106
            table_id="anchor-schedule",
            view_id=None,
            default_room_name=None,
            schedule_year=2026,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        session.add_all([room, source])
        session.flush()
        schedule = AnchorSchedule(
            source_config_id=source.id,
            source_record_id="schedule-1",
            room_id=room.id,
            schedule_date=date(2026, 7, 8),
            year=2026,
            month=7,
            day=8,
            hour_slot="08-09",
            hour_order=8,
            planned_anchor_raw="Q-李昕",
            planned_anchor_canonical="Q-李昕",
            planned_anchor_base_names=["李昕"],
            schedule_status="scheduled",
            note=None,
        )
        fact = HourlyFact(
            room_id=room.id,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="08-09",
            hour_order=8,
            hour_start_at=datetime(2026, 7, 8, 8, tzinfo=SHANGHAI),
            hour_end_at=datetime(2026, 7, 8, 9, tzinfo=SHANGHAI),
            latest_point_id=None,
            latest_observed_at=datetime(2026, 7, 8, 8, 55, tzinfo=SHANGHAI),
            actual_anchor_canonical="Q-李昕",
            actual_anchor_base_names=["李昕"],
            actual_control_canonical="郑荣贵",
            planned_anchor_canonical="Q-李昕",
            planned_anchor_base_names=["李昕"],
            anchor_schedule_status="scheduled",
            anchor_match_status="matched",
            control_shift_name="早班",
            control_is_scheduled=True,
            control_is_rest=False,
            control_may_be_on_duty=True,
            data_status="complete",
        )
        session.add_all([schedule, fact])
        session.flush()
        session.add(
            HourlyMetric(
                hourly_fact_id=fact.id,
                metric_key="period_overall_roi",
                numeric_value=Decimal("3"),
                value_source="latest_point",
                quality_status="valid",
            )
        )
        session.commit()

        HourlyFactService(session, CATALOG).rebuild()

        rebuilt = session.get(HourlyFact, fact.id)
        assert rebuilt is not None
        assert rebuilt.data_status == "missing"
        assert rebuilt.latest_observed_at is None
        assert session.scalar(select(func.count()).select_from(HourlyMetric)) == 0


def test_rebuild_uses_source_modified_time_to_break_equal_observed_times() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        room = Room(
            name="重复采集点测试直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        source = SourceConfig(
            name="测试实绩源",
            source_type="feishu_bitable",
            source_role="live_actual",
            app_token="fixture-live",  # noqa: S106
            table_id="live-table",
            view_id=None,
            default_room_name=room.name,
            schedule_year=None,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        session.add_all([room, source])
        session.flush()
        later_modified = RawSourceRecord(
            source_config_id=source.id,
            source_record_id="record-later-modified",
            source_created_at=datetime(2026, 7, 8, 9, 0, tzinfo=SHANGHAI),
            source_modified_at=datetime(2026, 7, 8, 9, 10, tzinfo=SHANGHAI),
            raw_fields={},
            payload_hash="a" * 64,
            is_deleted=False,
        )
        earlier_modified = RawSourceRecord(
            source_config_id=source.id,
            source_record_id="record-earlier-modified",
            source_created_at=datetime(2026, 7, 8, 9, 0, tzinfo=SHANGHAI),
            source_modified_at=datetime(2026, 7, 8, 9, 5, tzinfo=SHANGHAI),
            raw_fields={},
            payload_hash="b" * 64,
            is_deleted=False,
        )
        session.add_all([later_modified, earlier_modified])
        session.flush()
        observed = datetime(2026, 7, 8, 8, 55, tzinfo=SHANGHAI)
        preferred = LivePoint(
            raw_source_record_id=later_modified.id,
            room_id=room.id,
            observed_at=observed,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="08-09",
            hour_order=8,
            anchor_raw="Q-李昕",
            anchor_canonical="Q-李昕",
            anchor_base_name="李昕",
            anchor_members=["李昕"],
            anchor_note=None,
            control_raw="郑荣贵",
            control_canonical="郑荣贵",
            control_base_name="郑荣贵",
            auto_check_status="正确",
            valid=True,
            invalid_reason=None,
            raw_payload={},
        )
        non_preferred = LivePoint(
            raw_source_record_id=earlier_modified.id,
            room_id=room.id,
            observed_at=observed,
            business_date=date(2026, 7, 8),
            year=2026,
            month=7,
            hour_slot="08-09",
            hour_order=8,
            anchor_raw="Q-旧记录",
            anchor_canonical="Q-旧记录",
            anchor_base_name="旧记录",
            anchor_members=["旧记录"],
            anchor_note=None,
            control_raw="旧场控",
            control_canonical="旧场控",
            control_base_name="旧场控",
            auto_check_status="正确",
            valid=True,
            invalid_reason=None,
            raw_payload={},
        )
        session.add_all([preferred, non_preferred])
        session.flush()
        session.add_all(
            [
                LivePointMetric(
                    live_point_id=preferred.id,
                    metric_key="period_overall_amount",
                    numeric_value=Decimal("200"),
                    raw_value="200",
                    parse_status="parsed",
                ),
                LivePointMetric(
                    live_point_id=non_preferred.id,
                    metric_key="period_overall_amount",
                    numeric_value=Decimal("100"),
                    raw_value="100",
                    parse_status="parsed",
                ),
            ]
        )
        session.commit()

        HourlyFactService(session, CATALOG).rebuild()

        fact = session.scalar(select(HourlyFact))
        assert fact is not None
        assert fact.latest_point_id == preferred.id
        assert fact.actual_anchor_canonical == "Q-李昕"
        amount = session.scalar(
            select(HourlyMetric.numeric_value).where(
                HourlyMetric.hourly_fact_id == fact.id,
                HourlyMetric.metric_key == "period_overall_amount",
            )
        )
        assert amount == Decimal("200")
