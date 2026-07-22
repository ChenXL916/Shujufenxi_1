from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.domain.metrics import MetricCatalog
from app.integrations.excel.reader import iter_fixture_records
from app.integrations.feishu.client import FeishuError
from app.models.entities import HourlyFact, LivePoint, Room, SourceConfig, SyncRun
from app.services import feishu_sync_service as service
from app.services.feishu_sync_service import (
    configured_sources,
    discover_live_sources,
    discover_schedule_sources,
    sync_source,
)
from app.services.hourly_fact_service import HourlyFactService

ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def acquired_lock(_name: str):  # type: ignore[no-untyped-def]
    yield True


@pytest.mark.asyncio
async def test_all_sync_entrypoints_share_one_resource_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_names: list[str] = []

    @contextmanager
    def held_lock(name: str):  # type: ignore[no-untyped-def]
        lock_names.append(name)
        yield False

    def unexpected_database_access():  # type: ignore[no-untyped-def]
        raise AssertionError("锁未获取时不得访问数据库")

    monkeypatch.setattr(service, "distributed_lock", held_lock, raising=False)
    monkeypatch.setattr(service, "get_session_factory", unexpected_database_access)

    all_sources = await service.sync_configured_sources()
    one_source = await service.sync_configured_source(uuid4())

    assert all_sources == {"status": "skipped", "reason": "lock-held"}
    assert one_source == {"status": "skipped", "reason": "lock-held"}
    assert lock_names == ["source-sync", "source-sync"]


def test_live_source_can_sync_without_schedule_source() -> None:
    settings = Settings(
        app_env="test",
        feishu_live_app_token="live-app",  # noqa: S106
        feishu_live_table_id="live-table",
        feishu_live_view_id="live-view",
        feishu_schedule_app_token="",
        feishu_schedule_table_id="",
    )

    assert configured_sources(settings) == [
        {
            "name": "直播实绩",
            "app_token": "live-app",
            "table_id": "live-table",
            "view_id": "live-view",
            "role": "live_actual",
        }
    ]


@pytest.mark.asyncio
async def test_one_base_link_discovers_every_live_room_table() -> None:
    settings = Settings(
        app_env="test",
        feishu_live_app_token="live-app",  # noqa: S106
        feishu_live_table_id="first-table",
        feishu_live_view_id="first-view",
        feishu_schedule_app_token="",
        feishu_schedule_table_id="",
    )

    class Client:
        async def list_tables(self, _app_token: str) -> list[dict[str, str]]:
            return [
                {"table_id": "second-table", "name": "第二直播间"},
                {"table_id": "first-table", "name": "第一直播间"},
            ]

    sources = await discover_live_sources(
        Client(),  # type: ignore[arg-type]
        settings,
        configured_sources(settings),
    )
    assert [(item["table_id"], item["view_id"]) for item in sources] == [
        ("first-table", "first-view"),
        ("second-table", ""),
    ]


@pytest.mark.asyncio
async def test_one_schedule_base_discovers_anchor_and_staff_tables() -> None:
    sources = [
        {
            "name": "直播排班",
            "app_token": "schedule-app",
            "table_id": "anchor-table",
            "view_id": "anchor-view",
            "role": "anchor_schedule",
        }
    ]

    class Client:
        async def list_tables(self, _app_token: str) -> list[dict[str, str]]:
            return [
                {"table_id": "staff-table", "name": "直播部门排班表"},
                {"table_id": "anchor-table", "name": "主播直播排班表"},
                {"table_id": "other-table", "name": "说明"},
            ]

        async def list_fields(self, _app_token: str, table_id: str) -> list[dict[str, str]]:
            fields = {
                "anchor-table": ["直播间", "月份", "时段", "1日"],
                "staff-table": ["姓名", "岗位", "状态", "月份", "1日"],
                "other-table": ["说明"],
            }
            return [{"field_name": name} for name in fields[table_id]]

    discovered = await discover_schedule_sources(Client(), sources)  # type: ignore[arg-type]
    assert [(item["table_id"], item["role"], item["view_id"]) for item in discovered] == [
        ("anchor-table", "anchor_schedule", "anchor-view"),
        ("staff-table", "staff_schedule", ""),
    ]


@pytest.mark.asyncio
async def test_api_sync_reuses_export_source_and_is_idempotent(
    excel_fixture_set,  # type: ignore[no-untyped-def]
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
    fixture = next(
        record
        for record in iter_fixture_records(excel_fixture_set.live)
        if record.source_role == "live_actual" and record.raw_fields.get("时段") != "0:00-0:00"
    )

    class Client:
        uses_user_access_token = True

        async def list_records(self, *_args: object) -> list[dict[str, Any]]:
            return [{"record_id": fixture.source_record_id, "fields": fixture.raw_fields}]

    with Session(engine) as session:
        source = SourceConfig(
            name="真实导出",
            source_type="feishu_base_export",
            source_role="live_actual",
            app_token="live-app",  # noqa: S106
            table_id="live-table",
            view_id="live-view",
            default_room_name=fixture.default_room_name,
            schedule_year=None,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        session.add(source)
        session.commit()
        first = await sync_source(
            Client(),  # type: ignore[arg-type]
            session,
            catalog,
            name="直播实绩",
            app_token="live-app",  # noqa: S106
            table_id="live-table",
            view_id="live-view",
            configured_role="live_actual",
        )
        HourlyFactService(session, catalog).rebuild()
        generic_room = session.scalar(select(Room).where(Room.name == "直播实绩"))
        assert generic_room is not None
        assert session.scalar(select(HourlyFact.id).where(HourlyFact.room_id == generic_room.id))
        second = await sync_source(
            Client(),  # type: ignore[arg-type]
            session,
            catalog,
            name=str(fixture.default_room_name),
            app_token="live-app",  # noqa: S106
            table_id="live-table",
            view_id="live-view",
            configured_role="live_actual",
        )
        HourlyFactService(session, catalog).rebuild()
        session.refresh(source)
        runs = list(session.scalars(select(SyncRun).order_by(SyncRun.started_at)))
        point = session.scalar(select(LivePoint))
        assert point is not None
        mapped_room = session.get(Room, point.room_id)
        mapped_room_name = mapped_room.name if mapped_room else None
        stale_fact = session.scalar(
            select(HourlyFact.id).where(HourlyFact.room_id == generic_room.id)
        )

    assert source.source_type == "feishu_bitable"
    assert first["records"] == 1
    assert first["reports"][0]["records_created"] == 1
    assert second["reports"][0]["records_unchanged"] == 1
    assert source.default_room_name == fixture.default_room_name
    assert mapped_room_name == fixture.default_room_name
    assert stale_fact is None
    assert [run.mode for run in runs] == ["feishu_user_api", "feishu_user_api"]


@pytest.mark.asyncio
async def test_configured_sync_supports_tenant_then_user_token_and_records_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",  # noqa: S106
        feishu_live_app_token="live-app",  # noqa: S106
        feishu_live_table_id="live-table",
        feishu_live_view_id="live-view",
    )

    class Client:
        def __init__(
            self, *_args: object, access_token: str | None = None, **_kwargs: object
        ) -> None:
            self.uses_user_access_token = access_token is not None

        async def list_records(self, *_args: object) -> list[dict[str, Any]]:
            return []

        async def list_tables(self, *_args: object) -> list[dict[str, str]]:
            return [
                {"table_id": "live-table", "name": "第一直播间"},
                {"table_id": "second-table", "name": "第二直播间"},
            ]

        async def close(self) -> None:
            return None

    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "load_runtime_settings", lambda _session: settings)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(service, "project_root", lambda: ROOT)
    monkeypatch.setattr(service, "FeishuBitableClient", Client)
    monkeypatch.setattr(service, "distributed_lock", acquired_lock)

    tenant = await service.sync_configured_sources("live_actual")
    assert tenant["status"] == "completed"
    assert tenant["auth_mode"] == "tenant_access_token"
    assert len(tenant["sources"]) == 2

    class Store:
        def __init__(self, _settings: Settings) -> None:
            pass

        def load(self, _session: Session) -> object:
            return object()

        async def valid_access_token(self, _session: Session) -> str:
            return "user-access"  # noqa: S105

    monkeypatch.setattr(service, "FeishuOAuthStore", Store)
    user = await service.sync_configured_sources("live_actual")
    assert user["auth_mode"] == "user_access_token"

    class FailingClient(Client):
        async def list_records(self, *_args: object) -> list[dict[str, Any]]:
            raise FeishuError("test failure")

    monkeypatch.setattr(service, "FeishuBitableClient", FailingClient)
    with pytest.raises(FeishuError, match="test failure"):
        await service.sync_configured_sources("live_actual")
    with factory() as session:
        source = session.scalar(select(SourceConfig))
        assert source is not None
        assert source.last_error == "test failure"


@pytest.mark.asyncio
async def test_single_source_sync_does_not_discover_or_sync_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",  # noqa: S106
    )
    with factory() as session:
        selected = SourceConfig(
            name="第一直播间/live_actual",
            source_type="feishu_bitable",
            source_role="live_actual",
            app_token="live-app",  # noqa: S106
            table_id="table-one",
            view_id="view-one",
            default_room_name="第一直播间",
            schedule_year=None,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        sibling = SourceConfig(
            name="第二直播间/live_actual",
            source_type="feishu_bitable",
            source_role="live_actual",
            app_token="live-app",  # noqa: S106
            table_id="table-two",
            view_id="view-two",
            default_room_name="第二直播间",
            schedule_year=None,
            field_mapping={},
            enabled=True,
            last_sync_at=None,
            last_success_at=None,
            last_error=None,
        )
        session.add_all([selected, sibling])
        session.commit()
        selected_id = selected.id

    requested_tables: list[str] = []

    class Client:
        uses_user_access_token = False

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def list_records(
            self, _app_token: str, table_id: str, _view_id: str | None
        ) -> list[dict[str, Any]]:
            requested_tables.append(table_id)
            return []

        async def list_tables(self, *_args: object) -> list[dict[str, str]]:
            raise AssertionError("单源同步不得发现或同步同 Base 的其他表")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(service, "project_root", lambda: ROOT)
    monkeypatch.setattr(service, "FeishuBitableClient", Client)
    monkeypatch.setattr(service, "distributed_lock", acquired_lock)

    sync_one = getattr(service, "sync_configured_source", None)
    assert sync_one is not None, "缺少按 source_id 精确同步入口"
    result = await sync_one(selected_id)

    assert requested_tables == ["table-one"]
    assert result["status"] == "completed"
    assert len(result["sources"]) == 1
