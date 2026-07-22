from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import get_engine
from app.domain.metrics import MetricCatalog
from app.services.fixture_import_service import FixtureImportService
from app.services.hourly_fact_service import HourlyFactService

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    catalog = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")
    report: list[dict[str, object]] = []
    with Session(engine) as session:
        importer = FixtureImportService(session, catalog, schedule_year=2026)
        for path in sorted((ROOT / "fixtures").glob("*.xlsx")):
            summary = importer.import_workbook(path)
            report.append({"file": path.name, "sync": summary.__dict__})
        hourly_facts = HourlyFactService(session, catalog).rebuild()
    report.append({"hourly_facts": hourly_facts})
    print(json.dumps(report, ensure_ascii=False, indent=2, default=list))


if __name__ == "__main__":
    main()
