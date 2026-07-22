from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", ROOT / "backups"))


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
        shutil.copy2(source, target)
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
            [pg_dump, "--format=custom", "--file", str(target), safe_url], env=env, check=True
        )
    print(f"备份完成：{target}")


if __name__ == "__main__":
    main()
