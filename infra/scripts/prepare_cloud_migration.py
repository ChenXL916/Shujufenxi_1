from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from backup import _backup_sqlite


def _read_env_value(path: Path, key: str) -> str:
    for raw_line in path.read_text("utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip("\"'")
    raise RuntimeError(f"{path} 中未配置 {key}")


def _sqlite_path(database_url: str, *, env_file: Path) -> Path:
    prefix = "sqlite+pysqlite:///"
    if not database_url.startswith(prefix):
        raise RuntimeError("云迁移快照来源必须是 SQLite DATABASE_URL")
    path = Path(database_url.removeprefix(prefix))
    if not path.is_absolute():
        path = (env_file.parent / path).resolve()
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成不停止正式服务的云迁移 SQLite 快照")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    env_file = args.env_file.resolve()
    output = args.output_dir.resolve()
    if not env_file.is_file():
        parser.error(f"环境文件不存在：{env_file}")
    output.mkdir(parents=True, exist_ok=True)
    snapshot = output / "source.sqlite3"
    manifest_path = output / "source.manifest.json"
    if snapshot.exists() or manifest_path.exists():
        raise RuntimeError(f"迁移快照目录已包含输出文件，拒绝覆盖：{output}")

    source = _sqlite_path(_read_env_value(env_file, "DATABASE_URL"), env_file=env_file)
    if not source.is_file():
        raise RuntimeError(f"正式 SQLite 数据库不存在：{source}")
    integrity = _backup_sqlite(source, snapshot)
    manifest = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "format": "sqlite3-online-backup",
        "snapshot": snapshot.name,
        "size_bytes": snapshot.stat().st_size,
        "sha256": _sha256(snapshot),
        "integrity_check": integrity,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "snapshot": str(snapshot),
                "manifest": str(manifest_path),
                "size_bytes": manifest["size_bytes"],
                "integrity_check": integrity,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
