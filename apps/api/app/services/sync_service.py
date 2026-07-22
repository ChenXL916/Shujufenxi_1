from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.excel.reader import FixtureRecord


class RawRecordStore(Protocol):
    def upsert(self, source_record_id: str, payload_hash: str) -> str: ...


class InMemoryRawRecordStore:
    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def upsert(self, source_record_id: str, payload_hash: str) -> str:
        existing = self.items.get(source_record_id)
        self.items[source_record_id] = payload_hash
        if existing is None:
            return "created"
        return "unchanged" if existing == payload_hash else "updated"


@dataclass(frozen=True)
class SyncSummary:
    records_read: int
    records_created: int
    records_updated: int
    records_unchanged: int


def sync_fixture_records(records: list[FixtureRecord], store: RawRecordStore) -> SyncSummary:
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for record in records:
        result = store.upsert(record.source_record_id, record.payload_hash)
        counts[result] += 1
    return SyncSummary(
        records_read=len(records),
        records_created=counts["created"],
        records_updated=counts["updated"],
        records_unchanged=counts["unchanged"],
    )
