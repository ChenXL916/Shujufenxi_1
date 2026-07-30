from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from infra.scripts.backup import _backup_sqlite  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_sqlite_backup_uses_online_api_and_includes_wal_commits(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "snapshot.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO facts (value) VALUES (?)",
            [("first",), ("second",), ("third",)],
        )
        connection.commit()

        integrity = _backup_sqlite(source, target)

    assert integrity == "ok"
    with sqlite3.connect(target) as snapshot:
        assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert snapshot.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 3
    assert _sha256(target)


def test_sqlite_backup_manifest_shape_is_json_serializable(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "snapshot.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    integrity = _backup_sqlite(source, target)
    manifest = {
        "format": "sqlite3-online-backup",
        "snapshot": target.name,
        "sha256": _sha256(target),
        "integrity_check": integrity,
    }

    payload = json.loads(json.dumps(manifest))

    assert payload["format"] == "sqlite3-online-backup"
    assert len(payload["sha256"]) == 64
    assert payload["integrity_check"] == "ok"


def test_prepare_cloud_migration_reads_ignored_env_without_exposing_secrets(
    tmp_path: Path,
) -> None:
    source = tmp_path / "live.sqlite3"
    output = tmp_path / "migration"
    env_file = tmp_path / ".env.tunnel"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO facts (value) VALUES ('real')")
    env_file.write_text(
        "\n".join(
            [
                f"DATABASE_URL=sqlite+pysqlite:///{source.as_posix()}",
                "FEISHU_APP_SECRET=must-not-appear",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603 - trusted project script
        [
            sys.executable,
            str(ROOT / "infra" / "scripts" / "prepare_cloud_migration.py"),
            "--env-file",
            str(env_file),
            "--output-dir",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert "must-not-appear" not in result.stdout
    manifest = json.loads((output / "source.manifest.json").read_text("utf-8"))
    assert manifest["integrity_check"] == "ok"
    assert manifest["size_bytes"] == (output / "source.sqlite3").stat().st_size
    with sqlite3.connect(output / "source.sqlite3") as snapshot:
        assert snapshot.execute("SELECT value FROM facts").fetchone()[0] == "real"
