from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.distributed_lock import distributed_lock
from app.core.paths import project_root
from app.core.runtime_settings import load_runtime_settings
from app.db.base import utc_now
from app.db.session import get_session_factory
from app.domain.metrics import MetricCatalog
from app.integrations.excel.reader import FixtureRecord, detect_source_role
from app.integrations.feishu.client import FeishuBitableClient
from app.integrations.feishu.oauth_store import FeishuOAuthStore
from app.models.entities import SourceConfig
from app.services.fixture_import_service import FixtureImportService
from app.services.hourly_fact_service import HourlyFactService

SourceRole = Literal["live_actual", "anchor_schedule", "staff_schedule"]


def payload_hash(fields: dict[str, Any]) -> str:
    encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def configured_sources(settings: Settings) -> list[dict[str, Any]]:
    candidates = [
        {
            "name": "直播实绩",
            "app_token": settings.feishu_live_app_token,
            "table_id": settings.feishu_live_table_id,
            "view_id": settings.feishu_live_view_id,
            "role": "live_actual",
        },
        {
            "name": "直播排班",
            "app_token": settings.feishu_schedule_app_token,
            "table_id": settings.feishu_schedule_table_id,
            "view_id": settings.feishu_schedule_view_id,
            "role": "anchor_schedule",
        },
    ]
    return [item for item in candidates if item["app_token"] and item["table_id"]]


async def discover_live_sources(
    client: FeishuBitableClient,
    settings: Settings,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expand one Base link to every table in that Base for true multi-room sync."""
    live_seed = next((item for item in sources if item["role"] == "live_actual"), None)
    if live_seed is None:
        return sources
    tables = await client.list_tables(str(live_seed["app_token"]))
    discovered: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered = sorted(
        tables,
        key=lambda item: str(item.get("table_id")) != str(live_seed["table_id"]),
    )
    for table in ordered:
        table_id = table.get("table_id")
        if not isinstance(table_id, str) or not table_id or table_id in seen:
            continue
        seen.add(table_id)
        discovered.append(
            {
                "name": str(table.get("name") or table_id),
                "app_token": live_seed["app_token"],
                "table_id": table_id,
                "view_id": (live_seed["view_id"] if table_id == live_seed["table_id"] else ""),
                "role": "live_actual",
            }
        )
    non_live = [item for item in sources if item["role"] != "live_actual"]
    return [*(discovered or [live_seed]), *non_live]


async def discover_schedule_sources(
    client: FeishuBitableClient,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expand one schedule Base into its anchor and staff schedule tables."""
    schedule_seed = next(
        (item for item in sources if item["role"] in {"anchor_schedule", "staff_schedule"}),
        None,
    )
    if schedule_seed is None:
        return sources
    tables = await client.list_tables(str(schedule_seed["app_token"]))
    discovered: list[dict[str, Any]] = []
    ordered = sorted(
        tables,
        key=lambda item: str(item.get("table_id")) != str(schedule_seed["table_id"]),
    )
    for table in ordered:
        table_id = table.get("table_id")
        if not isinstance(table_id, str) or not table_id:
            continue
        fields = await client.list_fields(str(schedule_seed["app_token"]), table_id)
        field_names = {str(field.get("field_name") or field.get("name") or "") for field in fields}
        detected = detect_source_role(field_names)
        if detected not in {"anchor_schedule", "staff_schedule"}:
            continue
        discovered.append(
            {
                "name": str(table.get("name") or table_id),
                "app_token": schedule_seed["app_token"],
                "table_id": table_id,
                "view_id": (
                    schedule_seed["view_id"] if table_id == schedule_seed["table_id"] else ""
                ),
                "role": detected,
            }
        )
    non_schedule = [
        item for item in sources if item["role"] not in {"anchor_schedule", "staff_schedule"}
    ]
    return [*non_schedule, *(discovered or [schedule_seed])]


async def sync_source(
    client: FeishuBitableClient,
    session: Session,
    catalog: MetricCatalog,
    *,
    name: str,
    app_token: str,
    table_id: str,
    view_id: str,
    configured_role: SourceRole,
) -> dict[str, Any]:
    api_records = await client.list_records(app_token, table_id, view_id or None)
    grouped: dict[str, list[FixtureRecord]] = {configured_role: []}
    for item in api_records:
        source_record_id = item.get("record_id") or item.get("id")
        if not isinstance(source_record_id, str) or not source_record_id.strip():
            raise ValueError(f"飞书记录缺少有效 record_id: {table_id}")
        item_fields = item.get("fields")
        fields = cast(dict[str, Any], item_fields) if isinstance(item_fields, dict) else {}
        role = configured_role
        detected = detect_source_role(set(str(key) for key in fields))
        if detected != "unknown":
            role = detected
        record = FixtureRecord(
            source_record_id=source_record_id.strip(),
            source_role=role,
            # A discovered live table represents one room. Prefer its table name over a
            # row field so stale generic values such as "直播实绩" cannot create a room.
            default_room_name=name if role == "live_actual" else None,
            raw_fields=fields,
            payload_hash=payload_hash(fields),
        )
        grouped.setdefault(role, []).append(record)

    reports: list[dict[str, Any]] = []
    settings = get_settings()
    importer = FixtureImportService(
        session,
        catalog,
        schedule_year=settings.feishu_schedule_year or 2026,
    )
    for group_role, records in grouped.items():
        source = _find_source(session, app_token, table_id, group_role)
        if source is None:
            source = SourceConfig(
                name=f"{name}/{group_role}",
                source_type="feishu_bitable",
                source_role=group_role,
                app_token=app_token,
                table_id=table_id,
                view_id=view_id or None,
                default_room_name=name if group_role == "live_actual" else None,
                schedule_year=settings.feishu_schedule_year,
                field_mapping={},
                enabled=True,
                last_sync_at=None,
                last_success_at=None,
                last_error=None,
            )
            session.add(source)
            session.flush()
        else:
            # Reuse the offline export source so the same record IDs are updated in-place.
            source.source_type = "feishu_bitable"
            source.view_id = view_id or source.view_id
            source.name = f"{name}/{group_role}"
            source.default_room_name = name if group_role == "live_actual" else None
            source.enabled = True
        report = importer.import_records(
            source,
            records,
            mode="feishu_user_api" if client.uses_user_access_token else "feishu_api",
            triggered_by="scheduled-sync",
            commit=False,
        )
        source.last_error = None
        reports.append({"role": group_role, **asdict(report)})
    return {"name": name, "records": len(api_records), "reports": reports}


async def sync_configured_sources(role: str | None = None) -> dict[str, Any]:
    with distributed_lock("source-sync") as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "lock-held"}
        with distributed_lock("facts-rebuild") as facts_acquired:
            if not facts_acquired:
                return {"status": "skipped", "reason": "facts-lock-held"}
            return await _sync_configured_sources(
                role,
                assert_locks_owned=lambda: _assert_leases_owned(acquired, facts_acquired),
            )


async def _sync_configured_sources(
    role: str | None = None,
    *,
    assert_locks_owned: Callable[[], None] = lambda: None,
) -> dict[str, Any]:
    catalog = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")
    reports: list[dict[str, Any]] = []
    auth_mode = "tenant_access_token"
    with get_session_factory()() as session:
        settings = load_runtime_settings(session)
        if not settings.feishu_credentials_configured:
            return {"status": "skipped", "reason": "feishu-credentials-not-configured"}
        sources = [
            item for item in configured_sources(settings) if role is None or item["role"] == role
        ]
        if not sources:
            return {"status": "skipped", "reason": f"source-not-configured:{role or 'all'}"}
        credential = FeishuOAuthStore(settings).load(session)
        access_token: str | None = None
        if credential is not None:
            access_token = await FeishuOAuthStore(settings).valid_access_token(session)
            auth_mode = "user_access_token"
        client = FeishuBitableClient(
            settings.feishu_app_id,
            settings.feishu_app_secret,
            access_token=access_token,
        )
        try:
            sources = await discover_live_sources(client, settings, sources)
            sources = await discover_schedule_sources(client, sources)
            for source in sources:
                try:
                    reports.append(
                        await sync_source(
                            client,
                            session,
                            catalog,
                            name=str(source["name"]),
                            app_token=str(source["app_token"]),
                            table_id=str(source["table_id"]),
                            view_id=str(source["view_id"] or ""),
                            configured_role=source["role"],
                        )
                    )
                except Exception as exc:
                    session.rollback()
                    _record_source_error(
                        session,
                        str(source["app_token"]),
                        str(source["table_id"]),
                        str(source["role"]),
                        str(exc),
                    )
                    raise
            facts = HourlyFactService(session, catalog).rebuild(commit=False)
            assert_locks_owned()
            session.commit()
        finally:
            await client.close()
    return {
        "status": "completed",
        "auth_mode": auth_mode,
        "sources": reports,
        "hourly_facts": facts,
    }


async def sync_configured_source(source_id: uuid.UUID) -> dict[str, Any]:
    with distributed_lock("source-sync") as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "lock-held"}
        with distributed_lock("facts-rebuild") as facts_acquired:
            if not facts_acquired:
                return {"status": "skipped", "reason": "facts-lock-held"}
            return await _sync_configured_source(
                source_id,
                assert_locks_owned=lambda: _assert_leases_owned(acquired, facts_acquired),
            )


async def _sync_configured_source(
    source_id: uuid.UUID,
    *,
    assert_locks_owned: Callable[[], None] = lambda: None,
) -> dict[str, Any]:
    """Synchronize exactly one persisted source without discovering sibling tables."""
    settings = get_settings()
    if not settings.feishu_credentials_configured:
        return {"status": "skipped", "reason": "feishu-credentials-not-configured"}

    catalog = MetricCatalog.from_yaml(project_root() / "config" / "metric_seed.yml")
    auth_mode = "tenant_access_token"
    with get_session_factory()() as session:
        source = session.get(SourceConfig, source_id)
        if source is None:
            raise LookupError("数据源不存在")
        if not source.enabled:
            raise ValueError("数据源已停用")
        if source.source_role not in {"live_actual", "anchor_schedule", "staff_schedule"}:
            raise ValueError(f"不支持的数据源角色: {source.source_role}")

        credential = FeishuOAuthStore(settings).load(session)
        access_token: str | None = None
        if credential is not None:
            access_token = await FeishuOAuthStore(settings).valid_access_token(session)
            auth_mode = "user_access_token"
        client = FeishuBitableClient(
            settings.feishu_app_id,
            settings.feishu_app_secret,
            access_token=access_token,
        )
        try:
            report = await sync_source(
                client,
                session,
                catalog,
                name=source.default_room_name or source.name.rsplit("/", 1)[0],
                app_token=source.app_token,
                table_id=source.table_id,
                view_id=source.view_id or "",
                configured_role=cast(SourceRole, source.source_role),
            )
            facts = HourlyFactService(session, catalog).rebuild(commit=False)
            assert_locks_owned()
            session.commit()
        except Exception as exc:
            session.rollback()
            _record_source_error(
                session,
                source.app_token,
                source.table_id,
                source.source_role,
                str(exc),
            )
            raise
        finally:
            await client.close()
    return {
        "status": "completed",
        "auth_mode": auth_mode,
        "sources": [report],
        "hourly_facts": facts,
    }


def _assert_leases_owned(*leases: object) -> None:
    for lease in leases:
        assert_owned = getattr(lease, "assert_owned", None)
        if callable(assert_owned):
            assert_owned()


def _find_source(session: Session, app_token: str, table_id: str, role: str) -> SourceConfig | None:
    for source_type in ("feishu_bitable", "feishu_base_export"):
        source = session.scalar(
            select(SourceConfig).where(
                SourceConfig.source_type == source_type,
                SourceConfig.app_token == app_token,
                SourceConfig.table_id == table_id,
                SourceConfig.source_role == role,
            )
        )
        if source is not None:
            return source
    return None


def _record_source_error(
    session: Session,
    app_token: str,
    table_id: str,
    role: str,
    error: str,
) -> None:
    source = _find_source(session, app_token, table_id, role)
    if source is not None:
        source.last_sync_at = utc_now()
        source.last_error = error[:2000]
        session.commit()
