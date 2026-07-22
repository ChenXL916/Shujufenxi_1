import sqlite3
from pathlib import Path

from app.db.session import _configure_sqlite_connection


def test_sqlite_preview_uses_wal_and_waits_for_writers(tmp_path: Path) -> None:
    database = str(tmp_path / "preview.db")
    connection = sqlite3.connect(database)
    try:
        _configure_sqlite_connection(connection, None)
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()
