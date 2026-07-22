from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.metrics import MetricCatalog
from app.models.entities import Room
from app.services.fixture_import_service import FixtureImportService

ROOT = Path(__file__).resolve().parents[3]
CATALOG = MetricCatalog.from_yaml(ROOT / "config" / "metric_seed.yml")


def test_room_resolution_reuses_separator_variants_as_aliases() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        canonical = Room(
            name="Mistine-水散粉",
            brand="Mistine",
            category="水散粉",
            active=True,
            confirmed=True,
            source_aliases=["Mistine-水散粉"],
        )
        session.add(canonical)
        session.flush()
        importer = FixtureImportService(session, CATALOG, schedule_year=2026)

        spaced = importer._room("Mistine 水散粉")  # noqa: SLF001
        underscored = importer._room("MISTINE_水散粉")  # noqa: SLF001

        assert spaced.id == canonical.id
        assert underscored.id == canonical.id
        assert set(canonical.source_aliases) == {
            "Mistine-水散粉",
            "Mistine 水散粉",
            "MISTINE_水散粉",
        }
        assert session.scalar(select(func.count()).select_from(Room)) == 1
