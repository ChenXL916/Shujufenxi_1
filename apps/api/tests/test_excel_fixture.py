import pytest

from app.integrations.excel.reader import iter_fixture_records, scan_workbook
from app.services.sync_service import InMemoryRawRecordStore, sync_fixture_records

pytestmark = pytest.mark.integration


def test_live_fixture_has_two_52_field_rooms(excel_fixture_set) -> None:  # type: ignore[no-untyped-def]
    scan = scan_workbook(excel_fixture_set.live)

    assert len(scan.sheets) == 2
    assert all(sheet.columns == 52 for sheet in scan.sheets)
    assert all(sheet.source_role == "live_actual" for sheet in scan.sheets)
    if excel_fixture_set.private:
        assert {sheet.name for sheet in scan.sheets} == {"柏瑞美-散粉", "柏瑞美-妆前乳"}
        assert {sheet.dimension for sheet in scan.sheets} == {"A1:AZ303", "A1:AZ304"}


def test_schedule_fixture_discovers_both_wide_table_roles(
    excel_fixture_set,  # type: ignore[no-untyped-def]
) -> None:
    scan = scan_workbook(excel_fixture_set.schedule)

    assert {sheet.source_role for sheet in scan.sheets} == {"anchor_schedule", "staff_schedule"}
    if excel_fixture_set.private:
        assert {sheet.dimension for sheet in scan.sheets} == {"A1:AI13", "A1:AH73"}


def test_fixture_payload_hash_makes_repeated_sync_idempotent(
    excel_fixture_set,  # type: ignore[no-untyped-def]
) -> None:
    records = iter_fixture_records(excel_fixture_set.live)
    store = InMemoryRawRecordStore()

    first = sync_fixture_records(records, store)
    second = sync_fixture_records(records, store)

    assert first.records_created == first.records_read == len(records)
    assert second.records_unchanged == second.records_read == len(records)
    assert second.records_created == 0
