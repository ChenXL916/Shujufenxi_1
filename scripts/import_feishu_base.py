from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine
from app.domain.metrics import MetricCatalog
from app.integrations.feishu.base_export import read_base_export
from app.models.entities import SourceConfig
from app.services.fixture_import_service import FixtureImportService
from app.services.hourly_fact_service import HourlyFactService

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入飞书多维表格 .base 离线快照")
    parser.add_argument("path", type=Path, help="飞书导出的 .base 文件")
    parser.add_argument(
        "--table-id",
        action="append",
        dest="table_ids",
        help="只导入指定数据表；可重复传入，默认导入所有可识别数据表",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = read_base_export(args.path.resolve())
    selected = [
        table
        for table in snapshot.tables
        if not args.table_ids or table.table_id in set(args.table_ids)
    ]
    if not selected:
        raise RuntimeError(".base 文件中没有匹配的数据表")

    engine = get_engine()
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
    reports: list[dict[str, object]] = []
    with Session(engine) as session:
        importer = FixtureImportService(
            session, catalog, schedule_year=get_settings().feishu_schedule_year or 2026
        )
        for table in selected:
            source = session.scalar(
                select(SourceConfig).where(
                    SourceConfig.source_type == "feishu_base_export",
                    SourceConfig.app_token == snapshot.base_token,
                    SourceConfig.table_id == table.table_id,
                    SourceConfig.source_role == table.source_role,
                )
            )
            if source is None:
                source = SourceConfig(
                    name=f"{snapshot.filename}/{table.name}",
                    source_type="feishu_base_export",
                    source_role=table.source_role,
                    app_token=snapshot.base_token or snapshot.filename,
                    table_id=table.table_id,
                    view_id=None,
                    default_room_name=table.name if table.source_role == "live_actual" else None,
                    schedule_year=(
                        get_settings().feishu_schedule_year
                        if table.source_role != "live_actual"
                        else None
                    ),
                    field_mapping={},
                    enabled=True,
                )
                session.add(source)
                session.flush()
            summary = importer.import_records(
                source,
                list(table.records),
                mode="feishu_base_export",
                triggered_by="base-export-import",
            )
            reports.append(
                {
                    "table_id": table.table_id,
                    "table_name": table.name,
                    "source_role": table.source_role,
                    "declared_records": table.declared_records,
                    "field_count": len(table.field_names),
                    "sync": summary.__dict__,
                }
            )
        hourly_facts = HourlyFactService(session, catalog).rebuild()
    print(
        json.dumps(
            {
                "file": snapshot.filename,
                "base_name": snapshot.base_name,
                "tables": reports,
                "hourly_facts": hourly_facts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
