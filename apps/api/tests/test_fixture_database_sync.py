from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.metrics import MetricCatalog
from app.integrations.excel.reader import FixtureRecord, iter_fixture_records
from app.models.entities import HourlyFact, LivePoint, RawSourceRecord, Room, SourceConfig
from app.services.fixture_import_service import FixtureImportService
from app.services.hourly_fact_service import HourlyFactService

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration


def test_real_fixtures_persist_idempotently_and_build_hourly_facts(
    excel_fixture_set,  # type: ignore[no-untyped-def]
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
    paths = list(excel_fixture_set.paths)
    expected_records = sum(len(iter_fixture_records(path)) for path in paths)

    with Session(engine) as session:
        importer = FixtureImportService(session, catalog, schedule_year=2026)
        first = [importer.import_workbook(path) for path in paths]
        second = [importer.import_workbook(path) for path in paths]
        fact_count = HourlyFactService(session, catalog).rebuild()

        assert sum(report.records_read for report in first) == expected_records
        assert sum(report.records_created for report in first) == expected_records
        assert sum(report.records_unchanged for report in second) == expected_records
        assert session.scalar(select(func.count()).select_from(RawSourceRecord)) == expected_records
        assert 0 < session.scalar(select(func.count()).select_from(LivePoint)) <= expected_records
        assert sum(report.records_invalid for report in first) > 0
        assert session.scalar(select(func.count()).select_from(Room)) >= 2
        assert fact_count == session.scalar(select(func.count()).select_from(HourlyFact))
        assert fact_count > 0

        live_record = next(
            record
            for path in paths
            for record in iter_fixture_records(path)
            if record.source_role == "live_actual"
        )
        api_source = SourceConfig(
            name="Mock Feishu API",
            source_type="feishu_bitable",
            source_role="live_actual",
            app_token="app-token",  # noqa: S106
            table_id="table-id",
            view_id=None,
            default_room_name="API 测试直播间",
            schedule_year=None,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        session.add(api_source)
        session.flush()
        created = importer.import_records(api_source, [live_record])
        unchanged = importer.import_records(api_source, [live_record])
        assert created.records_created == 1
        assert unchanged.records_unchanged == 1


def test_api_snapshot_marks_missing_live_records_deleted_and_removes_facts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")

    with Session(engine) as session:
        source = SourceConfig(
            name="快照删除测试/live_actual",
            source_type="feishu_bitable",
            source_role="live_actual",
            app_token="snapshot-app",  # noqa: S106
            table_id="snapshot-table",
            view_id=None,
            default_room_name="快照删除测试直播间",
            schedule_year=None,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        session.add(source)
        session.flush()
        record = FixtureRecord(
            source_record_id="record-1",
            source_role="live_actual",
            default_room_name="快照删除测试直播间",
            raw_fields={
                "主播": "测试主播",
                "场控": "测试场控",
                "自动检查": "正确",
                "时间": "2026-07-08 08:30:00",
                "时段": "08-09",
                "时段成交金额": "100",
            },
            payload_hash="a" * 64,
        )
        importer = FixtureImportService(session, catalog, schedule_year=2026)

        importer.import_records(source, [record])
        assert HourlyFactService(session, catalog).rebuild() == 1

        importer.import_records(source, [])
        raw = session.scalar(
            select(RawSourceRecord).where(RawSourceRecord.source_config_id == source.id)
        )
        assert raw is not None and raw.is_deleted is True
        assert HourlyFactService(session, catalog).rebuild() == 0
