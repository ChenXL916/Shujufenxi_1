from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import make_url

import app.models  # noqa: F401 - register all ORM tables
from app.core.config import Settings
from app.core.database_migration import migrate_tables, rotate_encrypted_payload
from app.core.secrets import SecretBox
from app.db.base import Base


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity(path: Path) -> str:
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def _decryptable_secret_count(
    engine: sa.Engine, old_box: SecretBox, new_box: SecretBox
) -> tuple[int, int]:
    table = Base.metadata.tables["system_settings"]
    encrypted_rows = 0
    decryptable_values = 0
    with engine.connect() as connection:
        statement = sa.select(table).where(table.c.encrypted.is_(True))
        for row in connection.execute(statement).mappings():
            encrypted_rows += 1
            _, count = rotate_encrypted_payload(row["value"], old_box=old_box, new_box=new_box)
            decryptable_values += count
    return encrypted_rows, decryptable_values


def main() -> int:
    parser = argparse.ArgumentParser(description="将直播驾驶舱 SQLite 快照迁移到 PostgreSQL")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-target-database", default="live_ops")
    parser.add_argument("--replace-target", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_file():
        parser.error(f"源数据库不存在：{source}")
    integrity = _sqlite_integrity(source)
    if integrity != "ok":
        raise RuntimeError(f"SQLite 完整性检查失败：{integrity}")

    target_url_text = os.environ.get("DATABASE_URL", "")
    if not target_url_text:
        raise RuntimeError("DATABASE_URL 未配置")
    target_url = make_url(target_url_text)
    if target_url.get_backend_name() != "postgresql":
        raise RuntimeError("目标必须是 PostgreSQL")
    if target_url.database != args.expected_target_database:
        raise RuntimeError(
            "目标数据库名不匹配："
            f"expected={args.expected_target_database}, actual={target_url.database}"
        )

    settings = Settings()
    old_settings = Settings(
        app_env="development",
        app_name=settings.app_name,
        field_encryption_key="",
    )
    old_box = SecretBox(old_settings)
    new_box = SecretBox(settings)
    source_engine = sa.create_engine(f"sqlite+pysqlite:///{source.as_posix()}")
    target_engine = sa.create_engine(target_url)
    try:
        encrypted_rows, decryptable_values = _decryptable_secret_count(
            source_engine, old_box, new_box
        )
        if encrypted_rows and not decryptable_values:
            raise RuntimeError(
                "源库含加密配置，但旧开发派生密钥无法解密；已拒绝写入目标库"
            )
        report = migrate_tables(
            source_engine=source_engine,
            target_engine=target_engine,
            metadata=Base.metadata,
            old_box=old_box,
            new_box=new_box,
            replace_target=args.replace_target,
        )
    finally:
        source_engine.dispose()
        target_engine.dispose()

    manifest: dict[str, Any] = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "path": str(source),
            "sha256": _sha256(source),
            "integrity_check": integrity,
        },
        "target": {
            "backend": "postgresql",
            "database": target_url.database,
        },
        "source_counts": report.source_counts,
        "target_counts": report.target_counts,
        "primary_key_digests": report.primary_key_digests,
        "encrypted_setting_rows": encrypted_rows,
        "rotated_secret_values": report.rotated_secret_values,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "tables": len(report.source_counts),
                "rows": sum(report.source_counts.values()),
                "rotated_secret_values": report.rotated_secret_values,
                "manifest": str(args.manifest),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
