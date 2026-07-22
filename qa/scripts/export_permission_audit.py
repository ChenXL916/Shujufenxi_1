from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AccessScope, get_access_scope
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import HourlyFact, HourlyMetric, Room

SHANGHAI = ZoneInfo("Asia/Shanghai")
AUTHORIZED_MARKER = "AUTHORIZED_EXPORT_MARKER"
VIEW_ONLY_MARKER = "VIEW_ONLY_NO_EXPORT_MARKER"


def add_fact(session: Session, room_id: object, anchor: str, hour: int) -> None:
    start = datetime(2026, 7, 15, hour, tzinfo=SHANGHAI)
    fact = HourlyFact(
        room_id=room_id,
        business_date=date(2026, 7, 15),
        year=2026,
        month=7,
        hour_slot=f"{hour:02d}-{hour + 1:02d}",
        hour_order=hour,
        hour_start_at=start,
        hour_end_at=start.replace(hour=hour + 1),
        latest_point_id=None,
        latest_observed_at=start,
        actual_anchor_canonical=anchor,
        actual_anchor_base_names=[anchor],
        actual_control_canonical="SYNTHETIC_CONTROL",
        planned_anchor_canonical=anchor,
        planned_anchor_base_names=[anchor],
        anchor_schedule_status="scheduled",
        anchor_match_status="matched",
        control_shift_name="synthetic",
        control_is_scheduled=True,
        control_is_rest=False,
        control_may_be_on_duty=True,
        data_status="complete",
    )
    session.add(fact)
    session.flush()
    values = {
        "period_overall_amount": Decimal("200"),
        "period_spend": Decimal("100"),
        "period_overall_roi": Decimal("2"),
        "period_order_count": Decimal("4"),
    }
    session.add_all(
        HourlyMetric(
            hourly_fact_id=fact.id,
            metric_key=key,
            numeric_value=value,
            value_source="synthetic_qa",
            quality_status="valid",
        )
        for key, value in values.items()
    )


def markers(response_bytes: bytes) -> list[str]:
    text = response_bytes.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    return sorted(row[0] for row in rows[1:] if row)


def main() -> int:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    user_id = uuid4()
    with Session(engine) as session:
        authorized = Room(
            name="SYNTHETIC_AUTHORIZED_ROOM",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        view_only = Room(
            name="SYNTHETIC_VIEW_ONLY_ROOM",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add_all([authorized, view_only])
        session.flush()
        add_fact(session, authorized.id, AUTHORIZED_MARKER, 8)
        add_fact(session, view_only.id, VIEW_ONLY_MARKER, 9)
        session.commit()
        authorized_id = authorized.id
        view_only_id = view_only.id

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    def mixed_access() -> AccessScope:
        return AccessScope(
            user_id=user_id,
            role="viewer",
            room_ids=frozenset({authorized_id, view_only_id}),
            can_export=True,
            export_room_ids=frozenset({authorized_id}),
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_scope] = mixed_access
    client = TestClient(app)
    try:
        all_response = client.post(
            "/api/v1/exports?file_format=csv&start_date=2026-07-15&end_date=2026-07-15"
        )
        blocked_response = client.post(
            "/api/v1/exports",
            params={
                "file_format": "csv",
                "start_date": "2026-07-15",
                "end_date": "2026-07-15",
                "room_ids": str(view_only_id),
            },
        )
        allowed_response = client.post(
            "/api/v1/exports",
            params={
                "file_format": "csv",
                "start_date": "2026-07-15",
                "end_date": "2026-07-15",
                "room_ids": str(authorized_id),
            },
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    result = {
        "safety": "in-memory SQLite; synthetic markers; no external services",
        "access": {
            "viewable_room_count": 2,
            "exportable_room_count": 1,
        },
        "all_rooms_request": {
            "status": all_response.status_code,
            "markers": markers(all_response.content) if all_response.status_code == 200 else [],
        },
        "explicit_view_only_request": {
            "status": blocked_response.status_code,
            "markers": (
                markers(blocked_response.content) if blocked_response.status_code == 200 else []
            ),
        },
        "explicit_authorized_request": {
            "status": allowed_response.status_code,
            "markers": (
                markers(allowed_response.content) if allowed_response.status_code == 200 else []
            ),
        },
    }
    leaked = (
        VIEW_ONLY_MARKER in result["all_rooms_request"]["markers"]
        or VIEW_ONLY_MARKER in result["explicit_view_only_request"]["markers"]
    )
    result["product_export_room_authorization"] = "FAIL" if leaked else "PASS"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(main())
