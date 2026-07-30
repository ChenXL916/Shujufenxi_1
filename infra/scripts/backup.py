from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", ROOT / "backups"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_sqlite(source: Path, target: Path) -> str:
    source_uri = f"file:{source.as_posix()}?mode=ro"
    with (
        sqlite3.connect(source_uri, uri=True, timeout=30) as source_connection,
        sqlite3.connect(target, timeout=30) as target_connection,
    ):
        source_connection.backup(target_connection)
        integrity = str(target_connection.execute("PRAGMA integrity_check").fetchone()[0])
    if integrity != "ok":
        target.unlink(missing_ok=True)
        raise RuntimeError(f"SQLite 在线备份完整性检查失败：{integrity}")
    return integrity


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "sqlite+pysqlite:///./live_ops.db")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if database_url.startswith("sqlite"):
        source_text = database_url.split("///", 1)[-1]
        source = Path(source_text)
        if not source.is_absolute():
            source = (ROOT / "apps" / "api" / source).resolve()
        if not source.exists():
            raise RuntimeError(f"SQLite 数据库不存在：{source}")
        target = BACKUP_DIR / f"live_ops_{stamp}.sqlite3"
        integrity = _backup_sqlite(source, target)
        manifest = {
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "format": "sqlite3-online-backup",
            "snapshot": target.name,
            "sha256": _sha256(target),
            "integrity_check": integrity,
        }
        target.with_suffix(".manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        pg_dump = shutil.which("pg_dump")
        if not pg_dump:
            raise RuntimeError("未找到 pg_dump，请在 PostgreSQL 容器或安装客户端后运行")
        parsed = urlparse(database_url.replace("postgresql+psycopg", "postgresql", 1))
        target = BACKUP_DIR / f"live_ops_{stamp}.dump"
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password
        safe_url = parsed._replace(
            netloc=f"{parsed.username or ''}@{parsed.hostname or ''}:{parsed.port or 5432}"
        ).geturl()
        subprocess.run(  # noqa: S603
            [pg_dump, "--format=custom", "--file", str(target), safe_url],
            env=env,
            check=True,
        )
    print(f"备份完成：{target}")


if __name__ == "__main__":
    main()
