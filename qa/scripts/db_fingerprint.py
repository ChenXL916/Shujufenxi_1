from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def stable(value: Any) -> str:
    if value is None:
        return "<NULL>"
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Produce a privacy-safe SQLite logical fingerprint")
    parser.add_argument("database")
    parser.add_argument("output")
    args = parser.parse_args()
    database = Path(args.database).resolve()
    uri = f"file:{database.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    result: dict[str, Any] = {"database": database.name, "tables": {}}
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({quoted})")]
            digest = hashlib.sha256()
            count = 0
            query = f"SELECT * FROM {quoted} ORDER BY rowid"
            for row in connection.execute(query):
                count += 1
                digest.update("\x1f".join(stable(value) for value in row).encode("utf-8"))
                digest.update(b"\x1e")
            schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            result["tables"][table] = {
                "rows": count,
                "columns": columns,
                "content_sha256": digest.hexdigest(),
                "schema_sha256": hashlib.sha256(stable(schema[0] if schema else None).encode()).hexdigest(),
            }
    finally:
        connection.close()
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
